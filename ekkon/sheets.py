"""Cliente de Google Sheets con cuenta de servicio.

La clave JSON se guarda solo en la PC del administrador (carpeta de datos del
programa); nunca va dentro del .exe ni en Firestore.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote

from . import local, settings
from .planilla import Hoja, Plan, letra_columna

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
BASE = "https://sheets.googleapis.com/v4/spreadsheets"


class SheetsError(Exception):
    pass


# ---------------------------------------------------------------- clave local

def archivo_clave() -> Path:
    return local.carpeta_datos() / "cuenta_servicio.json"


def guardar_clave(origen: str) -> str:
    """Valida y copia la clave JSON; devuelve el email de la cuenta de servicio."""
    try:
        info = json.loads(Path(origen).read_text("utf-8"))
    except (OSError, ValueError) as e:
        raise SheetsError("El archivo no es un JSON válido.") from e
    if info.get("type") != "service_account" or "private_key" not in info:
        raise SheetsError("El archivo no es una clave de cuenta de servicio de Google.")
    shutil.copyfile(origen, archivo_clave())
    return info.get("client_email", "")


def leer_clave() -> dict | None:
    try:
        return json.loads(archivo_clave().read_text("utf-8"))
    except (OSError, ValueError):
        return None


def borrar_clave() -> None:
    try:
        archivo_clave().unlink()
    except OSError:
        pass


def id_de_link(link: str) -> str:
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", link or "")
    if m:
        return m.group(1)
    texto = (link or "").strip()
    return texto if re.fullmatch(r"[a-zA-Z0-9_-]{25,}", texto) else ""


# ---------------------------------------------------------------- cliente

class Planilla:
    def __init__(self, spreadsheet_id: str, info: dict | None = None, hoja: str | None = None, sesion=None):
        if not spreadsheet_id:
            raise SheetsError("Falta el link de la planilla en Ajustes.")
        self.id = spreadsheet_id
        self.hoja = hoja or settings.HOJA_PLANILLA
        if sesion is None:
            info = info or leer_clave()
            if not info:
                raise SheetsError("Falta cargar la clave de la cuenta de servicio en Ajustes.")
            from google.auth.transport.requests import AuthorizedSession
            from google.oauth2 import service_account
            cred = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
            sesion = AuthorizedSession(cred)
        self.sesion = sesion
        self._gid: int | None = None

    def _rango(self, a1: str) -> str:
        nombre = self.hoja.replace("'", "''")
        return f"'{nombre}'!{a1}"

    def _req(self, metodo: str, ruta: str, **kw) -> dict:
        try:
            r = self.sesion.request(metodo, f"{BASE}/{self.id}{ruta}", timeout=60, **kw)
        except Exception as e:  # noqa: BLE001 - errores de red o de token
            raise SheetsError(f"No se pudo conectar con Google: {e}") from e
        if r.status_code >= 400:
            try:
                msg = r.json().get("error", {}).get("message", r.text)
            except ValueError:
                msg = r.text
            if r.status_code == 403:
                msg = ("La cuenta de servicio no tiene permiso. Comparta la planilla como Editor con "
                       f"el email de la cuenta de servicio. ({msg})")
            elif r.status_code == 404:
                msg = "No se encontró la planilla. Revise el link en Ajustes."
            raise SheetsError(msg)
        return r.json() if r.content else {}

    def gid(self) -> int:
        if self._gid is None:
            d = self._req("GET", "", params={"fields": "sheets.properties(sheetId,title)"})
            for s in d.get("sheets", []):
                if s["properties"]["title"].strip().lower() == self.hoja.strip().lower():
                    self._gid = s["properties"]["sheetId"]
                    break
            else:
                nombres = ", ".join(s["properties"]["title"] for s in d.get("sheets", []))
                raise SheetsError(f"No existe la hoja \"{self.hoja}\". Hojas encontradas: {nombres}.")
        return self._gid

    def leer(self) -> Hoja:
        self.gid()
        d = self._req("GET", f"/values/{quote(self._rango('A1:AZ'), safe='')}",
                      params={"valueRenderOption": "UNFORMATTED_VALUE",
                              "dateTimeRenderOption": "SERIAL_NUMBER"})
        return Hoja(d.get("values", []))

    # ------------------------------------------------------------ estructura de la hoja

    def info(self) -> dict:
        """sheetId, filas de la grilla, locale y la tabla (si la hoja tiene una tabla de Sheets)."""
        gid = self.gid()
        try:
            d = self._req("GET", "", params={"fields": "properties.locale,sheets(properties(sheetId,gridProperties),"
                                                       "tables(tableId,name,range))"})
        except SheetsError:   # API sin soporte de tablas
            d = self._req("GET", "", params={"fields": "properties.locale,sheets.properties(sheetId,gridProperties)"})
        salida = {"gid": gid, "filas": 0, "locale": d.get("properties", {}).get("locale", ""), "tabla": None}
        for sh in d.get("sheets", []):
            if sh["properties"]["sheetId"] != gid:
                continue
            salida["filas"] = sh["properties"].get("gridProperties", {}).get("rowCount", 0)
            tablas = sh.get("tables") or []
            # La tabla de devoluciones es la que empieza en la fila de encabezados (fila 1)
            tablas.sort(key=lambda t: t.get("range", {}).get("startRowIndex", 0))
            if tablas:
                salida["tabla"] = tablas[0]
        return salida

    @staticmethod
    def formato_fecha(locale: str):
        mes_primero = (locale or "").lower().startswith(("en_us", "en-us", "en_ph", "en_ca"))

        def fmt(v):
            if isinstance(v, dt.date):
                return f"{v.month}/{v.day}/{v.year}" if mes_primero else f"{v.day:02d}/{v.month:02d}/{v.year}"
            return v
        return fmt

    def escribir(self, celdas: list[tuple[str, object]], fmt=None) -> None:
        if not celdas:
            return
        fmt = fmt or self.formato_fecha(self.info()["locale"])
        data = [{"range": self._rango(a1), "values": [[fmt(v)]]} for a1, v in celdas]
        for i in range(0, len(data), 500):
            self._req("POST", "/values:batchUpdate",
                      json={"valueInputOption": "USER_ENTERED", "data": data[i:i + 500]})

    def aplicar(self, plan: Plan, hoja: Hoja) -> None:
        info = self.info()
        fmt = self.formato_fecha(info["locale"])
        tabla = info["tabla"]
        pedidos: list[dict] = []
        ultima_fila = hoja.numero_fila(hoja.ultima_con_venta())
        if plan.filas_nuevas:
            desde, hasta = plan.filas_nuevas[0][0], plan.filas_nuevas[-1][0]
            ultima_fila = max(ultima_fila, hasta)
            if hasta > info["filas"]:
                pedidos.append({"appendDimension": {"sheetId": info["gid"], "dimension": "ROWS",
                                                    "length": hasta - info["filas"] + 50}})
            if not tabla and plan.fila_modelo:
                # Sin tabla: se copian formato y listas desplegables de la fila anterior
                ancho = len(hoja.encabezados)
                origen = {"sheetId": info["gid"], "startRowIndex": plan.fila_modelo - 1,
                          "endRowIndex": plan.fila_modelo, "startColumnIndex": 0, "endColumnIndex": ancho}
                destino = {"sheetId": info["gid"], "startRowIndex": desde - 1, "endRowIndex": hasta,
                           "startColumnIndex": 0, "endColumnIndex": ancho}
                pedidos += [{"copyPaste": {"source": origen, "destination": destino, "pasteType": t}}
                            for t in ("PASTE_FORMAT", "PASTE_DATA_VALIDATION")]
        if tabla:
            rango = dict(tabla["range"])
            if ultima_fila > rango.get("endRowIndex", 0):
                # Se agranda la tabla para que las filas nuevas (y las que quedaron afuera) sean parte de ella
                rango["endRowIndex"] = ultima_fila
                pedidos.append({"updateTable": {"table": {"tableId": tabla["tableId"], "range": rango},
                                                "fields": "range"}})
        if pedidos:
            self._req("POST", ":batchUpdate", json={"requests": pedidos})
        if plan.filas_nuevas:
            fin = letra_columna(len(hoja.encabezados) - 1)
            data = [{"range": self._rango(f"A{n}:{fin}{n}"),
                     "values": [["" if v is None else fmt(v) for v in vals]]}
                    for n, vals in plan.filas_nuevas]
            self._req("POST", "/values:batchUpdate", json={"valueInputOption": "USER_ENTERED", "data": data})
        self.escribir(plan.celdas, fmt)

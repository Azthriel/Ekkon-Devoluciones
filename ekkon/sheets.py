"""Cliente de Google Sheets con cuenta de servicio.

La clave JSON se guarda solo en la PC del administrador (carpeta de datos del
programa); nunca va dentro del .exe ni en Firestore.
"""
from __future__ import annotations

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

    def escribir(self, celdas: list[tuple[str, object]]) -> None:
        if not celdas:
            return
        data = [{"range": self._rango(a1), "values": [[v]]} for a1, v in celdas]
        for i in range(0, len(data), 500):
            self._req("POST", "/values:batchUpdate",
                      json={"valueInputOption": "USER_ENTERED", "data": data[i:i + 500]})

    def preparar_filas(self, modelo: int, desde: int, hasta: int, ancho: int) -> None:
        """Copia formato y listas desplegables de la fila modelo a las filas nuevas."""
        gid = self.gid()
        origen = {"sheetId": gid, "startRowIndex": modelo - 1, "endRowIndex": modelo,
                  "startColumnIndex": 0, "endColumnIndex": ancho}
        destino = {"sheetId": gid, "startRowIndex": desde - 1, "endRowIndex": hasta,
                   "startColumnIndex": 0, "endColumnIndex": ancho}
        pedidos = [{"copyPaste": {"source": origen, "destination": destino, "pasteType": t}}
                   for t in ("PASTE_FORMAT", "PASTE_DATA_VALIDATION")]
        # Asegura que existan filas suficientes en la hoja
        d = self._req("GET", "", params={"fields": "sheets.properties(sheetId,gridProperties)"})
        for s in d.get("sheets", []):
            if s["properties"]["sheetId"] == gid:
                filas = s["properties"]["gridProperties"]["rowCount"]
                if hasta > filas:
                    pedidos.insert(0, {"appendDimension": {"sheetId": gid, "dimension": "ROWS",
                                                           "length": hasta - filas + 50}})
        self._req("POST", ":batchUpdate", json={"requests": pedidos})

    def aplicar(self, plan: Plan, hoja: Hoja) -> None:
        if plan.filas_nuevas:
            desde = plan.filas_nuevas[0][0]
            hasta = plan.filas_nuevas[-1][0]
            if plan.fila_modelo:
                self.preparar_filas(plan.fila_modelo, desde, hasta, len(hoja.encabezados))
            fin = letra_columna(len(hoja.encabezados) - 1)
            data = [{"range": self._rango(f"A{n}:{fin}{n}"), "values": [["" if v is None else v for v in vals]]}
                    for n, vals in plan.filas_nuevas]
            self._req("POST", "/values:batchUpdate", json={"valueInputOption": "USER_ENTERED", "data": data})
        self.escribir(plan.celdas)

"""Informe "Devoluciones para APP" de Virtual Seller: relaciona el N° de envío de la etiqueta con la venta.

Algunas etiquetas de devolución de ML traen solo el código de barras del envío. Con este informe, al escanearlo
se sabe a qué venta (y producto) corresponde. Se guarda en un solo documento de Firestore comprimido, como el
informe de OS (una búsqueda = una lectura).
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import unicodedata
import zlib

DOC = "envios_idx/todo"
RETENCION_DIAS = 180


def solo_digitos(texto) -> str:
    if isinstance(texto, float) and texto.is_integer():
        texto = int(texto)
    return re.sub(r"\D", "", str(texto or ""))


def es_envio(texto) -> bool:
    """Los N° de envío de ML tienen 11 dígitos (el Venta # y el ID Carrito tienen 16)."""
    return 10 <= len(solo_digitos(texto)) <= 13


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().lower()


def _columna(encabezado: str) -> str | None:
    h = _norm(encabezado)
    base = h.split(":")[-1].strip()
    if base == "id devolucion":
        return "devolucion"
    if base == "id envio":
        return "envio"
    if base.startswith("id venta"):
        return "venta"
    if base == "id reclamo":
        return "reclamo"
    if base.startswith("titulo"):
        return "producto"
    if base.startswith("codigo de producto") or base == "sku":
        return "sku"
    if base.startswith("cantidad"):
        return "cantidad"
    if base.startswith("fecha de creacion"):
        return "fecha"
    if base.startswith("estado devolucion"):
        return "estado"
    if base == "costo envio vendedor":
        return "costo_envio"
    return None


def _fecha(texto: str) -> str:
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", texto or "")
    if not m:
        return ""
    try:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return ""


def _numero(texto: str) -> float | None:
    t = re.sub(r"[^\d,.\-]", "", texto or "")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def leer_csv(contenido: bytes) -> dict[str, dict]:
    """{N° de envío: {envio, devolucion, venta, reclamo, producto, sku, cantidad, fecha, estado, costo_envio}}."""
    texto = None
    for cod in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            texto = contenido.decode(cod)
            break
        except UnicodeDecodeError:
            continue
    primera = texto.splitlines()[0] if texto else ""
    sep = ";" if primera.count(";") > primera.count(",") else ","
    filas = list(csv.reader(io.StringIO(texto), delimiter=sep))
    if not filas:
        raise ValueError("El archivo está vacío.")
    pos: dict[str, int] = {}
    for i, h in enumerate(filas[0]):
        c = _columna(h)
        if c:
            pos.setdefault(c, i)
    if "envio" not in pos or "venta" not in pos:
        raise ValueError("El archivo no parece el informe \"Devoluciones para APP\": faltan las columnas "
                         "ID Envio e ID Venta/Carrito.")
    salida: dict[str, dict] = {}
    for f in filas[1:]:
        if len(f) < len(filas[0]):
            continue

        def col(c, f=f):
            return f[pos[c]].strip() if c in pos else ""

        envio = solo_digitos(col("envio"))
        if not envio:
            continue
        cantidad = _numero(col("cantidad"))
        salida[envio] = {"envio": envio, "devolucion": col("devolucion"), "venta": solo_digitos(col("venta")),
                         "reclamo": solo_digitos(col("reclamo")), "producto": col("producto"), "sku": col("sku"),
                         "cantidad": int(cantidad) if cantidad else 1, "fecha": _fecha(col("fecha")),
                         "estado": col("estado"), "costo_envio": _numero(col("costo_envio"))}
    if not salida:
        raise ValueError("No encontré devoluciones en el archivo.")
    return salida


class IndiceEnvios:
    def __init__(self, fs):
        self.fs = fs
        self._datos: dict | None = None
        self._por: dict[str, dict[str, list]] = {}

    def _cargar(self) -> dict:
        if self._datos is None:
            doc = self.fs.obtener(DOC)
            blob = doc.get("datos") if doc else None
            self._datos = json.loads(zlib.decompress(blob).decode()) if blob else {}
            self._por = {"venta": {}, "reclamo": {}, "devolucion": {}}
            for e in self._datos.values():
                for campo in self._por:
                    k = e.get(campo) if campo != "devolucion" else (e.get(campo) or "").upper()
                    if k:
                        self._por[campo].setdefault(k, []).append(e)
        return self._datos

    def buscar(self, texto) -> list[dict]:
        """Devoluciones del informe por N° de envío, Venta #/ID Carrito, ID Reclamo o ID Devolución (DEV-…)."""
        datos = self._cargar()
        t = str(texto or "").strip()
        if t.upper().startswith("DEV-"):
            return list(self._por["devolucion"].get(t.upper(), []))
        n = solo_digitos(t)
        if not n:
            return []
        if n in datos:
            return [datos[n]]
        return list(self._por["venta"].get(n, [])) or list(self._por["reclamo"].get(n, []))

    def meta(self) -> dict:
        doc = self.fs.obtener(DOC) or {}
        return {k: v for k, v in doc.items() if k not in ("datos", "_id")}

    def importar(self, nuevas: dict, usuario: str, hoy: dt.date | None = None) -> dict:
        self._datos = None
        todas = dict(self._cargar())
        todas.update(nuevas)
        limite = ((hoy or dt.date.today()) - dt.timedelta(days=RETENCION_DIAS)).isoformat()
        todas = {k: v for k, v in todas.items() if not v.get("fecha") or v["fecha"] >= limite}
        blob = zlib.compress(json.dumps(todas, ensure_ascii=False, separators=(",", ":")).encode(), 9)
        meta = {"importado_en": dt.datetime.now(dt.timezone.utc), "importado_por": usuario,
                "envios_informe": len(nuevas), "envios_total": len(todas)}
        self.fs.guardar(DOC, {"datos": blob, **meta})
        self._datos = None
        return meta

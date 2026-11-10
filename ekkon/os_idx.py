"""Informe "OS para APP" de Virtual Seller (órdenes de servicio).

Se guarda en un solo documento de Firestore comprimido: son pocas filas y así una búsqueda
es una sola lectura (plan gratuito).
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import zlib

DOC = "os_idx/todo"


def clave_os(texto) -> str:
    """'000463', '463 ', 463.0 -> '463'. Las OS se comparan sin ceros adelante."""
    if isinstance(texto, float) and texto.is_integer():
        texto = int(texto)
    digitos = re.sub(r"\D", "", str(texto or ""))
    if not digitos:
        return ""
    return digitos.lstrip("0") or "0"


def _norm(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().lower()


def _columna(encabezado: str) -> str | None:
    h = _norm(encabezado)
    base = h.split(":")[-1].strip()
    if h.startswith("orden de servicio"):
        return "os"
    if "denominacion" in base or base == "producto":
        return "producto"
    if "sku" in base or base.startswith("codigo"):
        return "sku"
    if base.startswith("fecha ingreso"):
        return "fecha"
    if base.startswith("descripcion del cliente"):
        return "cliente"
    if base.startswith("informe tecnico"):
        return "informe"
    if base.startswith("observaciones"):
        return "observaciones"
    if base.startswith("tipo de servicio"):
        return "tipo"
    return None


def _fecha(texto: str) -> str:
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", texto or "")
    if not m:
        return ""
    try:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return ""


def leer_csv(contenido: bytes) -> dict[str, dict]:
    """Devuelve {clave_os: {producto, sku, fecha, cliente, informe, observaciones, tipo, os}}."""
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
    if "os" not in pos or "producto" not in pos:
        raise ValueError("El archivo no parece el informe de OS: faltan las columnas Orden y Denominación.")
    salida: dict[str, dict] = {}
    for f in filas[1:]:
        if len(f) < len(filas[0]):
            continue
        clave = clave_os(f[pos["os"]])
        if not clave:
            continue

        def col(c, f=f):
            return f[pos[c]].strip() if c in pos else ""

        salida[clave] = {"os": col("os"), "producto": col("producto"), "sku": col("sku"),
                         "fecha": _fecha(col("fecha")), "cliente": col("cliente"), "informe": col("informe"),
                         "observaciones": col("observaciones"), "tipo": col("tipo")}
    if not salida:
        raise ValueError("No encontré órdenes de servicio en el archivo.")
    return salida


class IndiceOS:
    def __init__(self, fs):
        self.fs = fs
        self._datos: dict | None = None

    def _cargar(self) -> dict:
        if self._datos is None:
            doc = self.fs.obtener(DOC)
            blob = doc.get("datos") if doc else None
            self._datos = json.loads(zlib.decompress(blob).decode()) if blob else {}
        return self._datos

    def buscar(self, numero) -> dict | None:
        return self._cargar().get(clave_os(numero))

    def todas(self) -> dict:
        return self._cargar()

    def meta(self) -> dict:
        doc = self.fs.obtener(DOC) or {}
        return {k: v for k, v in doc.items() if k not in ("datos", "_id")}

    def importar(self, nuevas: dict, usuario: str) -> dict:
        self._datos = None
        todas = dict(self._cargar())
        todas.update(nuevas)
        blob = zlib.compress(json.dumps(todas, ensure_ascii=False, separators=(",", ":")).encode(), 9)
        meta = {"importado_en": dt.datetime.now(dt.timezone.utc), "importado_por": usuario,
                "os_informe": len(nuevas), "os_total": len(todas)}
        self.fs.guardar(DOC, {"datos": blob, **meta})
        self._datos = todas
        return meta

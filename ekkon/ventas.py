"""Informe "Ventas ML para APP" de Virtual Seller.

Se importa el CSV exportado ("Exportar detalles") y se guarda en Firestore como un
índice repartido en 100 documentos según los dos últimos dígitos del número. Así
buscar una venta o un carrito lee un solo documento, y todo entra en el plan gratuito.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import zlib
from collections import defaultdict
from dataclasses import dataclass

COL_INDICE = "ventas_idx"
DOC_META = "config/ventas"
PARTES = 100
DIAS_A_CONSERVAR = 180

# Sucursal de Virtual Seller -> "Deposito origen" de la planilla
DEPOSITO_POR_SUCURSAL = {"podesta": "Podesta", "fulfillment": "Full", "boedo": "LP"}


def _norm(t: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().lower()


def deposito_de_sucursal(sucursal: str) -> str:
    return DEPOSITO_POR_SUCURSAL.get(_norm(sucursal), (sucursal or "").strip())


@dataclass
class Venta:
    venta: str
    carrito: str
    pedido: str
    fecha: dt.date | None
    codigo: str
    producto: str
    sucursal: str
    cantidad: int
    precio: float | None

    @property
    def deposito(self) -> str:
        return deposito_de_sucursal(self.sucursal)

    def a_lista(self) -> list:
        return [self.pedido, self.carrito, self.fecha.isoformat() if self.fecha else "", self.codigo,
                self.producto, self.sucursal, self.cantidad, self.precio]

    @classmethod
    def de_lista(cls, venta: str, x: list) -> "Venta":
        fecha = dt.date.fromisoformat(x[2]) if x[2] else None
        return cls(venta, x[1], x[0], fecha, x[3], x[4], x[5], int(x[6] or 1), x[7])


# ---------------------------------------------------------------- lectura del CSV

OBLIGATORIAS = {"venta": "Venta #", "fecha": "Fecha/Hora Venta", "codigo": "Codigo de Producto"}


def _clave_columna(encabezado: str) -> str | None:
    h = _norm(encabezado)
    base = h.split(":")[-1].strip()          # "venta ml#: venta #" -> "venta #"
    if h.startswith("pedido"):
        return "pedido"
    if base.replace(" ", "") == "venta#":
        return "venta"
    if "carrito" in base:
        return "carrito"
    if base.startswith("fecha") and "venta" in base:
        return "fecha"
    if "codigo de producto" in base:
        return "codigo"
    if base == "producto":
        return "producto"
    if base == "sucursal":
        return "sucursal"
    if base == "cantidad":
        return "cantidad"
    if "precio unitario" in base:
        return "precio"
    return None


def _ubicar_columnas(encabezados: list[str]) -> dict[str, int]:
    pos: dict[str, int] = {}
    for i, h in enumerate(encabezados):
        clave = _clave_columna(h)
        if clave:
            pos.setdefault(clave, i)
    faltan = [n for c, n in OBLIGATORIAS.items() if c not in pos]
    if faltan:
        raise ValueError("Al informe le faltan las columnas: " + ", ".join(faltan) + ".")
    return pos


def _fecha(texto: str) -> dt.date | None:
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})/(\d{4})", texto or "")
    if not m:
        return None
    try:
        return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _numero(texto: str) -> float | None:
    t = (texto or "").strip().replace("$", "").replace(" ", "")
    if not t:
        return None
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def leer_csv(contenido: bytes) -> list[Venta]:
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
    pos = _ubicar_columnas(filas[0])
    ancho = len(filas[0])
    ventas = []
    for f in filas[1:]:
        if len(f) < ancho:
            continue  # líneas finales de Salesforce (nombre del informe, copyright, etc.)
        venta = re.sub(r"\D", "", f[pos["venta"]])
        if not venta:
            continue

        def col(c, f=f):
            return f[pos[c]].strip() if c in pos else ""

        cant = _numero(col("cantidad"))
        ventas.append(Venta(venta=venta, carrito=re.sub(r"\D", "", col("carrito")), pedido=col("pedido"),
                            fecha=_fecha(col("fecha")), codigo=col("codigo"), producto=col("producto"),
                            sucursal=col("sucursal"), cantidad=int(cant) if cant else 1,
                            precio=_numero(col("precio"))))
    if not ventas:
        raise ValueError("No encontré ventas en el archivo.")
    return ventas


# ---------------------------------------------------------------- índice repartido

def parte(numero: str) -> str:
    return f"p{(numero or '00')[-2:].zfill(2)}"


def codificar(datos: dict) -> bytes:
    return zlib.compress(json.dumps(datos, ensure_ascii=False, separators=(",", ":")).encode(), 9)


def decodificar(blob: bytes | None) -> dict:
    if not blob:
        return {"v": {}, "c": {}}
    return json.loads(zlib.decompress(blob).decode())


def armar_partes(ventas: dict[str, Venta]) -> dict[str, dict]:
    partes: dict[str, dict] = {f"p{i:02d}": {"v": {}, "c": {}} for i in range(PARTES)}
    for v in ventas.values():
        partes[parte(v.venta)]["v"][v.venta] = v.a_lista()
        if v.carrito:
            partes[parte(v.carrito)]["c"].setdefault(v.carrito, []).append([v.venta, v.codigo, v.producto])
    return partes


def combinar(existentes: dict[str, Venta], nuevas: list[Venta], hoy: dt.date | None = None) -> dict[str, Venta]:
    limite = (hoy or dt.date.today()) - dt.timedelta(days=DIAS_A_CONSERVAR)
    todas = dict(existentes)
    for v in nuevas:
        todas[v.venta] = v
    return {k: v for k, v in todas.items() if v.fecha is None or v.fecha >= limite}


@dataclass
class Resultado:
    tipo: str               # "venta" | "carrito" | "no_encontrado"
    venta: Venta | None = None
    opciones: list | None = None   # para carrito: [[venta, codigo, producto], ...]


class Indice:
    """Acceso al índice en Firestore (con caché por sesión)."""

    def __init__(self, fs):
        self.fs = fs
        self._cache: dict[str, dict] = {}

    def _parte(self, nombre: str) -> dict:
        if nombre not in self._cache:
            doc = self.fs.obtener(f"{COL_INDICE}/{nombre}")
            self._cache[nombre] = decodificar(doc.get("datos") if doc else None)
        return self._cache[nombre]

    def venta(self, numero: str) -> Venta | None:
        x = self._parte(parte(numero))["v"].get(numero)
        return Venta.de_lista(numero, x) if x else None

    def buscar(self, numero: str) -> Resultado:
        v = self.venta(numero)
        if v:
            return Resultado("venta", v)
        opciones = self._parte(parte(numero))["c"].get(numero)
        if opciones:
            if len(opciones) == 1:
                return Resultado("carrito", self.venta(opciones[0][0]), opciones)
            return Resultado("carrito", None, opciones)
        return Resultado("no_encontrado")

    def todas(self) -> dict[str, Venta]:
        nombres = [f"p{i:02d}" for i in range(PARTES)]
        faltan = [n for n in nombres if n not in self._cache]
        if faltan:
            docs = self.fs.obtener_varios([f"{COL_INDICE}/{n}" for n in faltan])
            for n, doc in zip(faltan, docs):
                self._cache[n] = decodificar(doc.get("datos") if doc else None)
        salida: dict[str, Venta] = {}
        for n in nombres:
            for k, x in self._cache[n]["v"].items():
                salida[k] = Venta.de_lista(k, x)
        return salida

    def meta(self) -> dict:
        return self.fs.obtener(DOC_META) or {}

    def importar(self, nuevas: list[Venta], usuario: str) -> dict:
        self._cache.clear()
        todas = combinar(self.todas(), nuevas)
        partes = armar_partes(todas)
        ahora = dt.datetime.now(dt.timezone.utc)
        self.fs.guardar_varios([(f"{COL_INDICE}/{n}", {"datos": codificar(d), "actualizado_en": ahora})
                                for n, d in partes.items()])
        fechas = [v.fecha for v in nuevas if v.fecha]
        meta = {"importado_en": ahora, "importado_por": usuario, "ventas_informe": len(nuevas),
                "ventas_total": len(todas),
                "desde": min(fechas).isoformat() if fechas else "", "hasta": max(fechas).isoformat() if fechas else ""}
        self.fs.guardar(DOC_META, meta)
        self._cache = {n: d for n, d in partes.items()}
        return meta


def prefijos(ventas: dict[str, Venta]) -> dict[str, str | None]:
    """15 primeros dígitos -> venta (None si hay más de una). Para celdas que perdieron el último dígito."""
    salida: dict[str, str | None] = {}
    for k in ventas:
        p = k[:15]
        salida[p] = None if p in salida else k
    return salida


def carritos(ventas: dict[str, Venta]) -> dict[str, list[str]]:
    salida: dict[str, list[str]] = defaultdict(list)
    for v in ventas.values():
        if v.carrito:
            salida[v.carrito].append(v.venta)
    return dict(salida)

"""Lógica de la planilla "Devoluciones nuevo" (sin red, para poder probarla).

Regla de oro: el programa solo completa celdas VACÍAS y agrega ventas que no están.
Nunca pisa lo que se escribió a mano. Única excepción: las columnas de estado de
reclamo, donde reemplaza "Pendiente" por el resultado final.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass, field

from . import settings

# Encabezados tal como están en la fila 1 de la planilla
C_FECHA_REV = "Fecha revisión"
C_FECHA_COMPRA = "Fecha compra"
C_ARTICULO = "Articulo"
C_SKU = "SKU"
C_VENTA = "N° Venta"
C_VENTA_COPIAR = "N° Venta para copiar"
C_DEP_ORIGEN = "Deposito origen"
C_NDC = "NdC"
C_TRANSF = "Transferencia"
C_DEP_FINAL = "Deposito final"
C_MOTIVO = "Motivo"
C_CONDICION = "Condicion"
C_CLASIF = "Clasificacion"
C_RECLAMO = "Reclamo"
C_MEDIACION = "N° Mediación"
C_ESTADO1 = "Estado (1er reclamo)"
C_MONTO = "Monto Reintegrado"
C_MOVIMIENTO = "N° Movimiento"

REEMPLAZABLES = {C_ESTADO1: {"pendiente"}}

ESTADO_A_PLANILLA = {
    "reclamado": "Pendiente",
    "pendiente": "Pendiente",
    "cobertura": "Cobertura",
    "sin_cobertura": "NO cobertura",
}

EMAIL_ENVIADO = "Email enviado"


def normalizar(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t).strip().lower()


def vacia(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip())


def venta_de_celda(v) -> str:
    """Devuelve el número de venta como texto de dígitos (acepta texto, número o fórmula)."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return ""
    if isinstance(v, float):
        return str(int(v)) if v.is_integer() else ""
    if isinstance(v, int):
        return str(v)
    return re.sub(r"\D", "", str(v))


def coincide_venta(celda: str, venta: str) -> bool:
    """Las celdas guardadas como número pierden el último dígito (15 cifras de precisión)."""
    if not celda or not venta:
        return False
    if celda == venta:
        return True
    return len(celda) == len(venta) and celda[:15] == venta[:15] and celda.endswith("0")


def serial(fecha: dt.date) -> int:
    """Fecha como número de serie de Sheets (días desde 30/12/1899)."""
    return (fecha - dt.date(1899, 12, 30)).days


def fecha_de_serial(v) -> dt.date | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool) and 20000 < v < 80000:
        return dt.date(1899, 12, 30) + dt.timedelta(days=int(v))
    if isinstance(v, str):
        m = re.match(r"^\s*(\d{1,2})/(\d{1,2})/+(\d{4})", v)
        if m:
            try:
                return dt.date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                return None
    return None


def letra_columna(indice0: int) -> str:
    n, letras = indice0 + 1, ""
    while n:
        n, r = divmod(n - 1, 26)
        letras = chr(65 + r) + letras
    return letras


# ---------------------------------------------------------------- estructura

class Hoja:
    def __init__(self, filas: list[list]):
        if not filas:
            raise ValueError("La hoja está vacía.")
        self.encabezados = [str(x or "").strip() for x in filas[0]]
        self.filas = filas[1:]
        self.col = {normalizar(h): i for i, h in enumerate(self.encabezados) if h}
        faltan = [c for c in (C_VENTA, C_FECHA_REV) if normalizar(c) not in self.col]
        if faltan:
            raise ValueError("No encuentro las columnas: " + ", ".join(faltan) +
                             ". Revise que la primera fila tenga los encabezados.")

    def indice(self, columna: str) -> int | None:
        return self.col.get(normalizar(columna))

    def valor(self, fila0: int, columna: str):
        i = self.indice(columna)
        if i is None or fila0 >= len(self.filas):
            return None
        fila = self.filas[fila0]
        return fila[i] if i < len(fila) else None

    def numero_fila(self, fila0: int) -> int:
        """Número de fila en la planilla (1 = encabezados)."""
        return fila0 + 2

    def ultima_con_venta(self) -> int:
        """Índice 0-based de la última fila con número de venta (-1 si no hay)."""
        for i in range(len(self.filas) - 1, -1, -1):
            if venta_de_celda(self.valor(i, C_VENTA)):
                return i
        return -1

    def buscar(self, venta: str) -> int | None:
        for i in range(len(self.filas)):
            if coincide_venta(venta_de_celda(self.valor(i, C_VENTA)), venta):
                return i
        return None


# ---------------------------------------------------------------- devolución -> valores

def valores_de(dev: dict) -> dict:
    """Valores de la planilla que el programa conoce para una devolución."""
    v: dict = {}
    cargado = dev.get("cargado_en")
    if isinstance(cargado, dt.datetime):
        v[C_FECHA_REV] = serial(cargado.astimezone().date())
    if dev.get("codigo_producto"):
        v[C_SKU] = dev["codigo_producto"]
    v[C_VENTA] = dev["numero_venta"]
    for clave, col in (("deposito_origen", C_DEP_ORIGEN), ("motivo", C_MOTIVO),
                       ("condicion", C_CONDICION), ("clasificacion", C_CLASIF)):
        if dev.get(clave):
            v[col] = dev[clave]
    final = settings.DEPOSITO_FINAL.get(dev.get("clasificacion", ""))
    if final:
        v[C_DEP_FINAL] = final
    if dev.get("nc_realizada"):
        v[C_NDC] = "Si"
    if "reclamo" in dev:
        v[C_RECLAMO] = "si" if dev.get("reclamo") else "no"
    if dev.get("numero_mediacion"):
        v[C_MEDIACION] = dev["numero_mediacion"]
    estado = ESTADO_A_PLANILLA.get(dev.get("estado", ""))
    if estado:
        v[C_ESTADO1] = estado
    if dev.get("estado") == "cobertura":
        if dev.get("monto_reintegrado") not in (None, ""):
            v[C_MONTO] = dev["monto_reintegrado"]
        if dev.get("numero_movimiento"):
            v[C_MOVIMIENTO] = dev["numero_movimiento"]
    return v


def para_escribir(columna: str, valor):
    """Valor tal como se envía con USER_ENTERED."""
    if columna == C_VENTA:
        return "'" + str(valor)  # texto: evita que Sheets lo convierta en número y pierda dígitos
    if columna in (C_MEDIACION, C_MOVIMIENTO) and isinstance(valor, str) and valor.isdigit() and len(valor) > 15:
        return "'" + valor
    return valor


def iguales(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(float(a) - float(b)) < 0.005
    if isinstance(b, (int, float)) and isinstance(a, str):
        try:
            return abs(float(a.replace(",", ".")) - float(b)) < 0.005
        except ValueError:
            return False
    return normalizar(a) == normalizar(b)


# ---------------------------------------------------------------- plan de sincronización

@dataclass
class Plan:
    celdas: list[tuple[str, object]] = field(default_factory=list)  # (A1, valor)
    filas_nuevas: list[tuple[int, list]] = field(default_factory=list)  # (número de fila, valores)
    fila_modelo: int | None = None
    actualizadas: set = field(default_factory=set)
    conflictos: list[tuple[str, str, object, object]] = field(default_factory=list)  # venta, col, hoja, app
    sin_columna: set = field(default_factory=set)

    @property
    def vacio(self) -> bool:
        return not self.celdas and not self.filas_nuevas


def planificar(hoja: Hoja, devoluciones: list[dict]) -> Plan:
    plan = Plan()
    ultima = hoja.ultima_con_venta()
    plan.fila_modelo = hoja.numero_fila(ultima) if ultima >= 0 else None
    siguiente = hoja.numero_fila(ultima + 1)
    ancho = len(hoja.encabezados)
    ordenadas = sorted(devoluciones, key=lambda d: d.get("cargado_en") or dt.datetime.min.replace(
        tzinfo=dt.timezone.utc))
    for dev in ordenadas:
        venta = dev.get("numero_venta")
        if not venta:
            continue
        valores = valores_de(dev)
        fila0 = hoja.buscar(venta)
        if fila0 is None:
            nueva = [None] * ancho
            for col, val in valores.items():
                i = hoja.indice(col)
                if i is None:
                    plan.sin_columna.add(col)
                    continue
                nueva[i] = para_escribir(col, val)
            i_copiar = hoja.indice(C_VENTA_COPIAR)
            i_venta = hoja.indice(C_VENTA)
            if i_copiar is not None:
                nueva[i_copiar] = f"=\"'\"&{letra_columna(i_venta)}{siguiente}"
            plan.filas_nuevas.append((siguiente, nueva))
            siguiente += 1
            continue
        numero = hoja.numero_fila(fila0)
        for col, val in valores.items():
            i = hoja.indice(col)
            if i is None:
                plan.sin_columna.add(col)
                continue
            actual = hoja.valor(fila0, col)
            if col == C_VENTA or iguales(actual, val):
                continue
            if vacia(actual) or normalizar(actual) in REEMPLAZABLES.get(col, ()):
                plan.celdas.append((f"{letra_columna(i)}{numero}", para_escribir(col, val)))
                plan.actualizadas.add(venta)
            else:
                plan.conflictos.append((venta, col, actual, val))
    return plan


# ---------------------------------------------------------------- emails

MODELO = re.compile(r"\b(?:KB|UP)-[A-Z0-9][A-Z0-9.\-]*", re.IGNORECASE)


def modelo(articulo) -> str:
    """Extrae el modelo (ej. KB-MH52D) del título del artículo; si no hay, devuelve el título."""
    texto = str(articulo or "").strip()
    encontrados = MODELO.findall(texto)
    if encontrados:
        return encontrados[-1].upper().rstrip(".-")
    return texto


@dataclass
class ItemEmail:
    fila: int
    venta: str
    sku: str
    producto: str
    clasificacion: str
    destino: str
    fecha: dt.date | None
    editado: bool = False


ESPERA_MOVIMIENTO = "a la espera de movimiento"


def pendientes(hoja: Hoja, modelos: dict | None = None) -> list[ItemEmail]:
    """Filas con Transferencia = "A la espera de movimiento".

    modelos: SKU -> modelo guardado (ej. "RLA-0045" -> "KB-VC60LG"), para títulos sin modelo.
    """
    modelos = modelos or {}
    salida = []
    for i in range(len(hoja.filas)):
        venta = venta_de_celda(hoja.valor(i, C_VENTA))
        if not venta or normalizar(hoja.valor(i, C_TRANSF)) != ESPERA_MOVIMIENTO:
            continue
        clasif = str(hoja.valor(i, C_CLASIF) or "").strip()
        sku = str(hoja.valor(i, C_SKU) or "").strip()
        destino = str(hoja.valor(i, C_DEP_FINAL) or "").strip() or settings.DEPOSITO_FINAL.get(clasif, "")
        salida.append(ItemEmail(
            fila=hoja.numero_fila(i), venta=venta, sku=sku,
            producto=modelos.get(sku) or modelo(hoja.valor(i, C_ARTICULO)), clasificacion=clasif,
            destino=destino, fecha=fecha_de_serial(hoja.valor(i, C_FECHA_REV))))
    return salida


def _agrupar(items: list[ItemEmail], clave) -> list[tuple[ItemEmail, int]]:
    grupos: dict = {}
    for it in items:
        k = clave(it)
        if k in grupos:
            grupos[k] = (grupos[k][0], grupos[k][1] + 1)
        else:
            grupos[k] = (it, 1)
    return list(grupos.values())


def email_transferencia(items: list[ItemEmail]) -> tuple[str, str]:
    """Email de transferencia. Origen siempre Service Podestá; un bloque por cada destino."""
    origen = settings.ORIGEN_TRANSFERENCIA
    destinos: dict[str, list[ItemEmail]] = {}
    for it in items:
        destinos.setdefault(it.destino or "(completar destino)", []).append(it)
    if len(destinos) == 1:
        asunto = f"Solicitud de transferencia - {origen} a {next(iter(destinos))}"
    else:
        asunto = f"Solicitud de transferencia - {origen}"
    bloques: list[str] = []
    for destino, grupo in destinos.items():
        bloques += [f"Origen: {origen}", f"Destino: {destino}", "", "SKU | Producto | Cant."]
        bloques += [f"{it.sku or '(sin SKU)'} | {it.producto} | {cant}"
                    for it, cant in _agrupar(grupo, lambda x: (x.sku, x.producto))]
        bloques.append("")
    cuerpo = "\n".join([
        "Buenos días,",
        "",
        "Solicito realizar la siguiente transferencia de mercadería de notas de crédito:",
        "",
        *bloques,
        "Quedo atento a la confirmación de la transferencia.",
        "",
        "Saludos.",
    ])
    return asunto, cuerpo

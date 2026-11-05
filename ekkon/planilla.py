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
C_COSTO = "Costo del producto"
# Columna opcional: si la planilla tiene una columna con alguno de estos nombres, se completa el pedido
C_PEDIDO = "N° Pedido"
ALIAS = {C_PEDIDO: ("N° Pedido", "Pedido", "Nro Pedido", "N° de Pedido", "Nro. Pedido")}

# Datos que salen del informe de ventas: solo completan celdas vacías y nunca se reportan como diferencia
COLUMNAS_INFORME = (C_FECHA_COMPRA, C_ARTICULO, C_SKU, C_DEP_ORIGEN, C_COSTO, C_PEDIDO)

# Valores de la planilla que el programa puede reemplazar aunque la celda no esté vacía
REEMPLAZABLES = {C_ESTADO1: {"pendiente"}, C_CLASIF: {"service interno"}, C_CONDICION: {"service interno"}}

# Columnas donde el valor del programa es solo el inicial: si después cambia en la planilla
# (Email enviado, Realizada) no es una diferencia para reportar
SOLO_INICIAL = {C_TRANSF}

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
        for nombre in ALIAS.get(columna, (columna,)):
            i = self.col.get(normalizar(nombre))
            if i is not None:
                return i
        return None

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

def valores_de(dev: dict, hoy: dt.date | None = None) -> dict:
    """Valores de la planilla que el programa conoce para una devolución.

    Fecha revisión = el día en que la devolución se escribe en la planilla (queda guardado en "planilla_en").
    """
    v: dict = {}
    if dev.get("planilla_en"):
        v[C_FECHA_REV] = dt.date.fromisoformat(dev["planilla_en"])
    else:
        v[C_FECHA_REV] = hoy or dt.date.today()
    if dev.get("codigo_producto"):
        v[C_SKU] = dev["codigo_producto"]
    v[C_VENTA] = dev["numero_venta"]
    for clave, col in (("deposito_origen", C_DEP_ORIGEN), ("motivo", C_MOTIVO),
                       ("condicion", C_CONDICION), ("clasificacion", C_CLASIF)):
        if dev.get(clave):
            v[col] = dev[clave]
    final = dev.get("deposito_final") or settings.DEPOSITO_FINAL.get(dev.get("clasificacion", ""))
    if final:
        v[C_DEP_FINAL] = final
    if dev.get("nc_realizada"):
        v[C_NDC] = "Si"
        if dev.get("transferencia"):
            v[C_TRANSF] = dev["transferencia"]
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


def valores_de_informe(info) -> dict:
    """Valores de la planilla que salen del informe de ventas (objeto ventas.Venta)."""
    if info is None:
        return {}
    v: dict = {}
    if info.fecha:
        v[C_FECHA_COMPRA] = info.fecha
    if info.producto:
        v[C_ARTICULO] = info.producto
    if info.codigo:
        v[C_SKU] = info.codigo
    if info.deposito:
        v[C_DEP_ORIGEN] = info.deposito
    if info.precio is not None:
        v[C_COSTO] = info.precio
    if info.pedido:
        v[C_PEDIDO] = info.pedido
    return v


def para_escribir(columna: str, valor):
    """Valor tal como se envía con USER_ENTERED."""
    if columna == C_VENTA:
        return "'" + str(valor)  # texto: evita que Sheets lo convierta en número y pierda dígitos
    if columna in (C_MEDIACION, C_MOVIMIENTO) and isinstance(valor, str) and valor.isdigit() and len(valor) > 15:
        return "'" + valor
    return valor


def iguales(a, b) -> bool:
    if isinstance(b, dt.date):
        if isinstance(a, dt.date):
            return a == b
        return fecha_de_serial(a) == b
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
    completadas_informe: set = field(default_factory=set)   # filas que solo se completan con el informe
    # Filas donde en "N° Venta" hay un ID Carrito: (A1, carrito, [ventas])
    carritos: list[tuple[str, str, list[str]]] = field(default_factory=list)
    # Devoluciones (id del documento) que se escriben por primera vez: se les guarda la fecha
    planilla_en: list[str] = field(default_factory=list)
    # La misma venta cargada dos veces en el programa: (venta, doc que se usa, doc repetido)
    duplicadas: list[tuple[str, str, str]] = field(default_factory=list)
    # La misma venta en varias filas de la planilla: (venta, [filas])
    repetidas_en_planilla: list[tuple[str, list[int]]] = field(default_factory=list)

    @property
    def vacio(self) -> bool:
        return not self.celdas and not self.filas_nuevas

    def correcciones(self) -> list[tuple[str, str]]:
        """Reemplazos de ID Carrito por Venta # cuando el carrito tiene una sola venta."""
        return [(a1, "'" + ventas[0]) for a1, _c, ventas in self.carritos if len(ventas) == 1]


def _completar_fila(plan: Plan, hoja: Hoja, fila0: int, valores: dict, venta: str, reportar: bool,
                    pisar: dict | None = None) -> None:
    numero = hoja.numero_fila(fila0)
    for col, val in valores.items():
        i = hoja.indice(col)
        if i is None:
            if col != C_PEDIDO:
                plan.sin_columna.add(col)
            continue
        actual = hoja.valor(fila0, col)
        if col == C_VENTA or iguales(actual, val):
            continue
        se_pisa = any(iguales(actual, x) for x in (pisar or {}).get(col, ()))
        if vacia(actual) or normalizar(actual) in REEMPLAZABLES.get(col, ()) or se_pisa:
            plan.celdas.append((f"{letra_columna(i)}{numero}", para_escribir(col, val)))
            plan.actualizadas.add(venta)
        elif reportar and col not in SOLO_INICIAL:
            plan.conflictos.append((venta, col, actual, val))


def planificar(hoja: Hoja, devoluciones: list[dict], ventas: dict | None = None,
               hoy: dt.date | None = None) -> Plan:
    """ventas: índice del informe {Venta #: ventas.Venta} (opcional)."""
    from .ventas import carritos as _carritos
    ventas = ventas or {}
    hoy = hoy or dt.date.today()
    por_carrito = _carritos(ventas) if ventas else {}
    plan = Plan()
    ultima = hoja.ultima_con_venta()
    plan.fila_modelo = hoja.numero_fila(ultima) if ultima >= 0 else None
    siguiente = hoja.numero_fila(ultima + 1)
    ancho = len(hoja.encabezados)
    i_venta = hoja.indice(C_VENTA)
    def resolver(dev):
        venta = dev.get("numero_venta") or ""
        if venta and venta not in ventas and len(por_carrito.get(venta, [])) == 1:
            # Devolución vieja cargada con el ID Carrito: en la planilla va el Venta #
            return venta, por_carrito[venta][0]
        return "", venta

    minimo = dt.datetime.min.replace(tzinfo=dt.timezone.utc)
    # Primero las que ya están guardadas con el Venta #: si la misma venta está dos veces, gana esa
    ordenadas = sorted(devoluciones, key=lambda d: (bool(resolver(d)[0]), d.get("cargado_en") or minimo))
    tocadas: set[int] = set()
    vistas: dict[str, str] = {}
    for dev in ordenadas:
        carrito, venta = resolver(dev)
        if not venta:
            continue
        doc_id = dev.get("_id") or dev.get("numero_venta")
        if venta in vistas:
            plan.duplicadas.append((venta, vistas[venta], doc_id))
            continue
        vistas[venta] = doc_id
        valores = valores_de(dev, hoy)
        valores[C_VENTA] = venta
        info = ventas.get(venta)
        carrito = carrito or (info.carrito if info else "")
        if info and info.deposito:
            valores.pop(C_DEP_ORIGEN, None)   # la Sucursal del informe manda sobre lo cargado a mano
        informe = {k: v for k, v in valores_de_informe(info).items() if k not in valores}
        # Las filas escritas antes con la fecha de carga pasan a tener la fecha en que entran a la planilla
        pisar = {}
        cargado = dev.get("cargado_en")
        if not dev.get("planilla_en") and isinstance(cargado, dt.datetime):
            pisar[C_FECHA_REV] = {cargado.astimezone().date()}
        fila0 = hoja.buscar(venta)
        if fila0 is None and carrito:
            fila0 = hoja.buscar(carrito)
            if fila0 is not None:
                plan.carritos.append((f"{letra_columna(i_venta)}{hoja.numero_fila(fila0)}", carrito, [venta]))
        if not dev.get("planilla_en"):
            plan.planilla_en.append(doc_id)
        if fila0 is None:
            nueva = [None] * ancho
            for col, val in (valores | informe).items():
                i = hoja.indice(col)
                if i is None:
                    if col != C_PEDIDO:
                        plan.sin_columna.add(col)
                    continue
                nueva[i] = para_escribir(col, val)
            i_copiar = hoja.indice(C_VENTA_COPIAR)
            if i_copiar is not None:
                nueva[i_copiar] = f"=\"'\"&{letra_columna(i_venta)}{siguiente}"
            plan.filas_nuevas.append((siguiente, nueva))
            siguiente += 1
            continue
        tocadas.add(fila0)
        _completar_fila(plan, hoja, fila0, valores, venta, reportar=True, pisar=pisar)
        _completar_fila(plan, hoja, fila0, informe, venta, reportar=False)

    filas_por_venta: dict[str, list[int]] = {}
    for fila0 in range(len(hoja.filas)):
        numero = venta_de_celda(hoja.valor(fila0, C_VENTA))
        if numero:
            filas_por_venta.setdefault(numero, []).append(hoja.numero_fila(fila0))
    plan.repetidas_en_planilla = [(v, f) for v, f in filas_por_venta.items() if len(f) > 1]

    if ventas:
        # Filas cargadas a mano: se completan con el informe y se detectan los ID Carrito
        from .ventas import prefijos as _prefijos
        por_prefijo = _prefijos(ventas)
        for fila0 in range(len(hoja.filas)):
            if fila0 in tocadas:
                continue
            celda = hoja.valor(fila0, C_VENTA)
            numero = venta_de_celda(celda)
            if not numero:
                continue
            info = ventas.get(numero)
            if info is None and isinstance(celda, float):
                encontrada = por_prefijo.get(numero[:15])
                info = ventas.get(encontrada) if encontrada else None
            if info is None and numero in por_carrito:
                plan.carritos.append((f"{letra_columna(i_venta)}{hoja.numero_fila(fila0)}", numero,
                                      por_carrito[numero]))
                continue
            if info is None:
                continue
            antes = len(plan.celdas)
            # En las filas viejas no se toca el costo: él lo completa junto con el costo de envío
            datos = {k: v for k, v in valores_de_informe(info).items() if k != C_COSTO}
            _completar_fila(plan, hoja, fila0, datos, info.venta, reportar=False)
            if len(plan.celdas) > antes:
                plan.completadas_informe.add(info.venta)
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
DESTINOS_TRANSFERENCIA = {"podesta", "scrap"}


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


def enviados(hoja: Hoja, modelos: dict | None = None) -> list[ItemEmail]:
    """Filas con Transferencia = "Email enviado" y destino Podestá o Scrap, más recientes primero.

    Son las transferencias pedidas que falta llevar y marcar como Realizada.
    """
    modelos = modelos or {}
    salida = []
    for i in range(len(hoja.filas)):
        venta = venta_de_celda(hoja.valor(i, C_VENTA))
        if not venta or normalizar(hoja.valor(i, C_TRANSF)) != normalizar(EMAIL_ENVIADO):
            continue
        destino = str(hoja.valor(i, C_DEP_FINAL) or "").strip()
        if normalizar(destino) not in DESTINOS_TRANSFERENCIA:
            continue
        sku = str(hoja.valor(i, C_SKU) or "").strip()
        salida.append(ItemEmail(
            fila=hoja.numero_fila(i), venta=venta, sku=sku,
            producto=modelos.get(sku) or modelo(hoja.valor(i, C_ARTICULO)),
            clasificacion=str(hoja.valor(i, C_CLASIF) or "").strip(), destino=destino,
            fecha=fecha_de_serial(hoja.valor(i, C_FECHA_REV))))
    salida.sort(key=lambda it: (it.fecha or dt.date.min, it.fila), reverse=True)
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

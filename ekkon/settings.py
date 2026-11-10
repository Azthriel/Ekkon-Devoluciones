"""Configuración fija de la aplicación.

La API key web de Firebase no es un secreto: identifica el proyecto y la
seguridad real la dan las reglas de Firestore (ver firestore.rules).
"""

APP_NAME = "Ekkon Devoluciones"

FIREBASE_PROJECT_ID = "ekkon-bf945"
# Firebase > Configuración del proyecto > General > Tus apps > App web > apiKey
FIREBASE_API_KEY = "AIzaSyBE5V980bOknc4WJghz4W0b0tBCxfWzsiE"

# Límite de caracteres que acepta Mercado Libre en el mensaje de reclamo
LIMITE_MENSAJE = 320

# Fotos: se comprimen y se guardan dentro de Firestore (plan gratuito, sin Storage)
FOTOS_MAX_POR_DEVOLUCION = 8
FOTO_LADO_MAXIMO = 1600
FOTO_BYTES_MAXIMOS = 850_000

URL_ML_VENCEN_HOY = ("https://vendedores.mercadolibre.com.ar/post-purchase/post-sales"
                     "?main.filter=returns&temporal.filter=urgent#from=seller-menu")

# Detalle de la venta en Mercado Libre. Si la venta es parte de un carrito, ML usa el ID Carrito.
URL_VENTA_ML = "https://vendedores.mercadolibre.com.ar/ventas/{id}/detalle"


def link_venta(numero_venta: str, carrito: str = "") -> str:
    return URL_VENTA_ML.format(id=carrito or numero_venta) if (carrito or numero_venta) else ""


# Los códigos coinciden con las listas desplegables de la planilla "Devoluciones nuevo"
CLASIFICACIONES = [
    ("N", "N — Nuevo, vuelve a stock de venta"),
    ("A", "A — Outlet"),
    ("B", "B — Outlet"),
    ("C", "C — Outlet"),
    ("D", "D — Service (se repara acá)"),
    ("E", "E — Service (se repara acá)"),
    ("Service", "Service — Se repara acá"),
    ("Scrap", "Scrap — Irreparable / descarte"),
]

# "Service Interno" ya no se usa: el service externo cerró y todo el service se hace acá
CONDICIONES = ["buena", "caja rota", "Con uso", "Service", "Extraviado", "Irreparable", "Objeto distinto"]

# Condición que se sugiere al elegir la clasificación (Alan puede cambiarla)
CONDICION_SUGERIDA = {
    "N": "buena", "A": "caja rota", "B": "Con uso", "C": "Con uso", "D": "Service", "E": "Service",
    "Service": "Service", "Scrap": "Irreparable",
}

MOTIVOS = ["no lo quiere", "cancelado", "no funciona", "Roto", "Extraviado",
           "No cumple con las caracteristicas de la publicación", "Recibio otra cosa",
           "Faltan partes o accesorios", "No se pudo entregar"]

DEPOSITOS_ORIGEN = ["Podesta", "Full", "LP"]

# Depósito final que se escribe en la planilla según la clasificación
DEPOSITO_FINAL = {
    "N": "Podestá", "A": "Service Podesta", "B": "Service Podesta", "C": "Service Podesta",
    "D": "Service Podesta", "E": "Service Podesta", "Service": "Service Podesta", "Scrap": "Scrap",
}

# Al hacer la NC la unidad entra en Service Podestá: es siempre el origen de las transferencias
ORIGEN_TRANSFERENCIA = "Service Podestá"

# Columna "Transferencia" al marcar la NC: N y Scrap se transfieren; el resto queda en Service Podesta
TRANSF_ESPERA = "A la espera de movimiento"
TRANSF_REALIZADA = "Realizada"
TRANSFERENCIA_AL_HACER_NC = {"N": TRANSF_ESPERA, "Scrap": TRANSF_ESPERA}


def transferencia_al_hacer_nc(clasificacion: str) -> str:
    return TRANSFERENCIA_AL_HACER_NC.get(clasificacion or "", TRANSF_REALIZADA)

# Planilla de Google Sheets
HOJA_PLANILLA = "Devoluciones"

ESTADOS = {
    "cargada": "Cargada",
    "reclamo_armado": "Reclamo por enviar",
    "sin_reclamo": "Sin reclamo",
    "reclamado": "Reclamo enviado",
    "pendiente": "Pendiente de ML",
    "cobertura": "Con cobertura",
    "sin_cobertura": "Sin cobertura",
    "cancelacion": "Cancelación",
}

# Cancelaciones: vuelven como N a Podestá. Con o sin NC, se validan con el remito interno.
TRANSF_ESPERA_REMITO = "A la espera de remito"
EMAIL_CANCELACIONES_ASUNTO = "Devoluciones Procourrier"
EMAIL_CANCELACIONES_INTRO = ("Buenas Caro, te comparto los siguientes pedidos que volvieron como "
                             "cancelaciones de Procourrier:")


def necesita_nc(d: dict) -> bool:
    """Las devoluciones siempre llevan NC; las cancelaciones solo si se marcó que la llevan."""
    return d.get("tipo") != "cancelacion" or bool(d.get("lleva_nc"))

# Estados que el perfil de carga todavía puede modificar
ESTADOS_EDITABLES_CARGA = ("cargada", "reclamo_armado", "sin_reclamo")

ROLES = {
    "admin": "Administrador",
    "carga": "Carga",
    "service": "Service",
}

# Reparaciones (planilla "Reparaciones"): mismas listas que los desplegables de la planilla
REP_ESTADOS = ["Para revisar", "Revisada", "Esperando repuesto", "Esperando cotización", "Presupuesto abonado",
               "Para reparar", "Reparada", "Enviado a GP", "Finalizado", "Extraviado"]
REP_CAUSAS = ["Fallo de maquina", "Mal uso"]
REP_ORIGEN_REPUESTO = ["Scrap", "Outlet A", "Outlet B", "Outlet C", "Nuevo", "Envío de GP"]
REP_ESTADO_FINAL = ["Outlet B", "Outlet C", "Scrap", "GP", "Repuesto"]
# Al terminar la reparación de una devolución, su clasificación pasa a ser esta (GP queda como estaba)
CLASIF_POR_ESTADO_FINAL = {"Outlet B": "B", "Outlet C": "C", "Scrap": "Scrap", "Repuesto": "Scrap"}

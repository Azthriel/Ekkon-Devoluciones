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

# Los códigos coinciden con las listas desplegables de la planilla "Devoluciones nuevo"
CLASIFICACIONES = [
    ("N", "N — Nuevo, vuelve a stock de venta"),
    ("A", "A — Outlet"),
    ("B", "B — Outlet"),
    ("C", "C — Outlet"),
    ("D", "D — Service externo"),
    ("E", "E — Service externo"),
    ("Service", "Service — Service externo"),
    ("Service Interno", "Service Interno — Se repara acá"),
    ("Scrap", "Scrap — Irreparable / descarte"),
]

CONDICIONES = ["buena", "caja rota", "Con uso", "Service", "Service Interno",
               "Extraviado", "Irreparable", "Objeto distinto"]

# Condición que se sugiere al elegir la clasificación (Alan puede cambiarla)
CONDICION_SUGERIDA = {
    "N": "buena", "A": "caja rota", "B": "Con uso", "C": "Con uso", "D": "Service", "E": "Service",
    "Service": "Service", "Service Interno": "Service Interno", "Scrap": "Irreparable",
}

MOTIVOS = ["no lo quiere", "cancelado", "no funciona", "Roto", "Extraviado",
           "No cumple con las caracteristicas de la publicación", "Recibio otra cosa",
           "Faltan partes o accesorios", "No se pudo entregar"]

DEPOSITOS_ORIGEN = ["Podesta", "Full", "LP"]

# Depósito final que se escribe en la planilla según la clasificación
DEPOSITO_FINAL = {
    "N": "Podestá", "A": "Outlet Podesta", "B": "Outlet Podesta", "C": "Outlet Podesta",
    "D": "Service Podesta", "E": "Service Podesta", "Service": "Service Podesta",
    "Service Interno": "Service Podesta", "Scrap": "Scrap",
}
CLASIFICACIONES_OUTLET = ("A", "B", "C")

# Planilla de Google Sheets
HOJA_PLANILLA = "Devoluciones"

ESTADOS = {
    "cargada": "Cargada",
    "reclamo_armado": "Reclamo armado",
    "sin_reclamo": "Sin reclamo",
    "reclamado": "Reclamo enviado",
    "pendiente": "Pendiente de ML",
    "cobertura": "Con cobertura",
    "sin_cobertura": "Sin cobertura",
}

# Estados que el perfil de carga todavía puede modificar
ESTADOS_EDITABLES_CARGA = ("cargada", "reclamo_armado", "sin_reclamo")

ROLES = {
    "admin": "Administrador",
    "carga": "Carga",
}

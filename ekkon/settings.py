"""Configuración fija de la aplicación.

La API key web de Firebase no es un secreto: identifica el proyecto y la
seguridad real la dan las reglas de Firestore (ver firestore.rules).
"""

APP_NAME = "Ekkon Devoluciones"

FIREBASE_PROJECT_ID = "ekkon-bf945"
# Firebase > Configuración del proyecto > General > Tus apps > App web > apiKey
FIREBASE_API_KEY = ""

# Límite de caracteres que acepta Mercado Libre en el mensaje de reclamo
LIMITE_MENSAJE = 320

# Fotos: se comprimen y se guardan dentro de Firestore (plan gratuito, sin Storage)
FOTOS_MAX_POR_DEVOLUCION = 8
FOTO_LADO_MAXIMO = 1600
FOTO_BYTES_MAXIMOS = 850_000

CLASIFICACIONES = [
    ("N", "N — Vuelve a stock de venta"),
    ("A", "A — Outlet"),
    ("B", "B — Outlet"),
    ("C", "C — Outlet"),
    ("D", "D — Service externo"),
    ("E", "E — Service externo"),
    ("Service", "Service — Service externo"),
]

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

"""Acceso a datos (Firestore) y reglas de negocio de las devoluciones."""
from __future__ import annotations

import datetime as dt
import re

from . import settings
from .firebase import Firestore, FirebaseError

COL_DEV = "devoluciones"
COL_USUARIOS = "usuarios"
DOC_CONFIG = "config/app"


# ---------------------------------------------------------------- validaciones

def limpiar_numero_venta(texto: str) -> str:
    return re.sub(r"\D", "", texto or "")


def validar_numero_venta(texto: str) -> tuple[str, str | None, str | None]:
    """Devuelve (numero_limpio, error, advertencia)."""
    crudo = (texto or "").strip()
    numero = limpiar_numero_venta(crudo)
    if not numero:
        return numero, "Ingrese el número de venta.", None
    advertencia = None
    if numero != crudo.replace(" ", ""):
        advertencia = "Se quitaron caracteres que no eran números."
    if len(numero) != 16:
        aviso = f"El número tiene {len(numero)} dígitos; las ventas de ML suelen tener 16."
        advertencia = f"{advertencia} {aviso}" if advertencia else aviso
    elif not numero.startswith("2"):
        advertencia = "Las ventas de ML suelen empezar con 2. Revíselo."
    return numero, None, advertencia


def descripcion_clasificacion(codigo: str) -> str:
    return dict(settings.CLASIFICACIONES).get(codigo, codigo or "—")


# ---------------------------------------------------------------- reclamo con Claude

def armar_prompt(d: dict, cantidad_fotos: int) -> str:
    lineas = [
        "Necesito el mensaje de reclamo para esta devolución de Mercado Libre.",
        "",
        f"Número de venta: {d.get('numero_venta', '')}",
        f"Clasificación: {descripcion_clasificacion(d.get('clasificacion', ''))}",
    ]
    if d.get("codigo_producto"):
        lineas.append(f"Código de producto: {d['codigo_producto']}")
    if d.get("link_publicacion"):
        lineas.append(f"Publicación: {d['link_publicacion']}")
    if d.get("problema_comprador"):
        lineas.append(f"Problema que informó el comprador: {d['problema_comprador']}")
    lineas += [
        f"Estado en que llegó el producto: {d.get('descripcion', '')}",
        f"Fotos adjuntas: {cantidad_fotos}",
        "",
        f"Respondé con el mensaje (máximo {settings.LIMITE_MENSAJE} caracteres) y en una línea aparte "
        "\"Porcentaje sugerido: XX%\".",
    ]
    return "\n".join(lineas)


_RE_PORCENTAJE = re.compile(r"porcentaje[^\d\n]{0,40}(\d{1,3})\s*%", re.IGNORECASE)
_RE_CUALQUIER_PCT = re.compile(r"(\d{1,3})\s*%")


def leer_respuesta_claude(texto: str) -> tuple[str, int | None]:
    """Separa el mensaje del porcentaje sugerido en la respuesta pegada."""
    texto = (texto or "").strip()
    pct = None
    m = _RE_PORCENTAJE.search(texto)
    if m:
        pct = int(m.group(1))
    else:
        todos = _RE_CUALQUIER_PCT.findall(texto)
        if todos:
            pct = int(todos[-1])
    if pct is not None and not 0 <= pct <= 100:
        pct = None
    lineas = []
    for linea in texto.splitlines():
        l = linea.strip()
        if not l or _RE_PORCENTAJE.search(l) or l.lower().startswith(("mensaje", "**mensaje")):
            if l.lower().startswith(("mensaje:", "**mensaje:**", "mensaje de reclamo:")):
                resto = l.split(":", 1)[1].strip().strip("*").strip()
                if resto:
                    lineas.append(resto)
            continue
        lineas.append(l)
    mensaje = " ".join(lineas).strip().strip('"“”').strip()
    mensaje = re.sub(r"\*\*(.+?)\*\*", r"\1", mensaje)
    return mensaje, pct


# ---------------------------------------------------------------- repositorios

class Devoluciones:
    def __init__(self, fs: Firestore):
        self.fs = fs

    def obtener(self, numero: str) -> dict | None:
        return self.fs.obtener(f"{COL_DEV}/{numero}")

    def crear(self, datos: dict, fotos: list[bytes], usuario: dict) -> dict:
        ahora = dt.datetime.now(dt.timezone.utc)
        doc = dict(datos)
        doc.update({
            "fotos": len(fotos),
            "cargado_por": usuario.get("email", ""),
            "cargado_por_uid": usuario.get("_id", ""),
            "cargado_en": ahora,
            "actualizado_en": ahora,
        })
        try:
            creado = self.fs.crear(COL_DEV, datos["numero_venta"], doc)
        except FirebaseError as e:
            if e.codigo.startswith("ALREADY_EXISTS"):
                raise FirebaseError("ALREADY_EXISTS", "Esa venta ya fue cargada.") from e
            raise
        self.reemplazar_fotos(datos["numero_venta"], fotos, cantidad_anterior=0)
        return creado

    def actualizar(self, numero: str, campos: dict) -> dict:
        campos = dict(campos)
        campos["actualizado_en"] = dt.datetime.now(dt.timezone.utc)
        return self.fs.actualizar(f"{COL_DEV}/{numero}", campos)

    def reemplazar_fotos(self, numero: str, fotos: list[bytes], cantidad_anterior: int) -> None:
        for i, data in enumerate(fotos, 1):
            self.fs.guardar(f"{COL_DEV}/{numero}/fotos/f{i:02d}", {"orden": i, "jpg": data})
        for i in range(len(fotos) + 1, cantidad_anterior + 1):
            try:
                self.fs.borrar(f"{COL_DEV}/{numero}/fotos/f{i:02d}")
            except FirebaseError:
                pass

    def fotos(self, numero: str) -> list[bytes]:
        docs = self.fs.listar(f"{COL_DEV}/{numero}/fotos")
        docs.sort(key=lambda x: x.get("orden", 0))
        return [d["jpg"] for d in docs if d.get("jpg")]

    def recientes(self, limite: int = 300) -> list[dict]:
        return self.fs.consultar(COL_DEV, orden=[("cargado_en", "DESCENDING")], limite=limite)

    def borrar(self, numero: str, cantidad_fotos: int) -> None:
        for i in range(1, cantidad_fotos + 1):
            try:
                self.fs.borrar(f"{COL_DEV}/{numero}/fotos/f{i:02d}")
            except FirebaseError:
                pass
        self.fs.borrar(f"{COL_DEV}/{numero}")


class Usuarios:
    def __init__(self, fs: Firestore):
        self.fs = fs

    def obtener(self, uid: str) -> dict | None:
        return self.fs.obtener(f"{COL_USUARIOS}/{uid}")

    def listar(self) -> list[dict]:
        return sorted(self.fs.listar(COL_USUARIOS), key=lambda u: (u.get("nombre") or u.get("email", "")).lower())

    def crear_perfil(self, uid: str, email: str, nombre: str, rol: str) -> dict:
        return self.fs.guardar(f"{COL_USUARIOS}/{uid}", {
            "email": email.strip().lower(), "nombre": nombre.strip(), "rol": rol,
            "activo": True, "creado_en": dt.datetime.now(dt.timezone.utc),
        })

    def actualizar(self, uid: str, campos: dict) -> dict:
        return self.fs.actualizar(f"{COL_USUARIOS}/{uid}", campos)


class ConfigApp:
    def __init__(self, fs: Firestore):
        self.fs = fs

    def leer(self) -> dict:
        return self.fs.obtener(DOC_CONFIG) or {}

    def guardar(self, campos: dict) -> dict:
        return self.fs.actualizar(DOC_CONFIG, campos, debe_existir=False)

"""Compresión de fotos para que entren en un documento de Firestore (< 1 MiB)."""
from __future__ import annotations

import base64
import io

from PIL import Image, ImageOps

from . import settings


def comprimir(ruta_o_bytes) -> bytes:
    if isinstance(ruta_o_bytes, (bytes, bytearray)):
        img = Image.open(io.BytesIO(ruta_o_bytes))
    else:
        img = Image.open(ruta_o_bytes)
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    lado = settings.FOTO_LADO_MAXIMO
    while True:
        copia = img.copy()
        copia.thumbnail((lado, lado))
        for calidad in (82, 72, 62, 52):
            buf = io.BytesIO()
            copia.save(buf, "JPEG", quality=calidad, optimize=True)
            if buf.tell() <= settings.FOTO_BYTES_MAXIMOS:
                return buf.getvalue()
        lado = int(lado * 0.8)
        if lado < 400:
            return buf.getvalue()


def miniatura_b64(data: bytes, lado: int = 260) -> str:
    img = Image.open(io.BytesIO(data))
    img.thumbnail((lado, lado))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=75)
    return base64.b64encode(buf.getvalue()).decode()

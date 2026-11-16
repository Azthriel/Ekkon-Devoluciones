"""Caché local de una colección de Firestore (en el equipo), con actualización incremental.

Firestore gratis permite 50.000 lecturas por día. En lugar de leer toda la colección cada vez que se abre una
lista, se guarda en el equipo y solo se piden los documentos que cambiaron desde la última vez (campo
"actualizado_en", que todos los que escriben deben poner).
"""
from __future__ import annotations

import datetime as dt
import json
import threading
from pathlib import Path

from . import settings

RECARGA_COMPLETA = dt.timedelta(hours=24)   # una vez por día se lee todo (para enterarse de lo borrado)
SOLAPAMIENTO = dt.timedelta(minutes=30)     # margen por diferencias de hora entre equipos
SIN_CONSULTAR = dt.timedelta(seconds=20)    # si se pidió hace menos, no vuelve a consultar


def _a_json(v):
    if isinstance(v, dt.datetime):
        return {"__dt__": v.isoformat()}
    if isinstance(v, bytes):
        return None
    raise TypeError(type(v))


def _de_json(d: dict):
    if "__dt__" in d and len(d) == 1:
        return dt.datetime.fromisoformat(d["__dt__"])
    return d


class CacheColeccion:
    def __init__(self, fs, coleccion: str, archivo: Path | None = None):
        self.fs = fs
        self.coleccion = coleccion
        self.archivo = archivo
        self._lock = threading.RLock()
        self._docs: dict[str, dict] | None = None
        self._completa_en: dt.datetime | None = None
        self._consultado_en: dt.datetime | None = None

    def usar_archivo(self, archivo: Path | None) -> None:
        with self._lock:
            self.archivo = archivo
            self._docs = None
            self._completa_en = self._consultado_en = None

    def _leer_disco(self) -> None:
        if not self.archivo:
            return
        try:
            datos = json.loads(Path(self.archivo).read_text("utf-8"), object_hook=_de_json)
            if datos.get("proyecto") != settings.FIREBASE_PROJECT_ID:
                return
            self._docs = {d["_id"]: d for d in datos.get("docs", [])}
            self._completa_en = dt.datetime.fromisoformat(datos["completa_en"])
        except (OSError, ValueError, KeyError, TypeError):
            self._docs = None

    def _guardar_disco(self) -> None:
        if not self.archivo or self._docs is None or self._completa_en is None:
            return
        try:
            datos = {"proyecto": settings.FIREBASE_PROJECT_ID, "completa_en": self._completa_en.isoformat(),
                     "docs": list(self._docs.values())}
            tmp = Path(self.archivo).with_suffix(".tmp")
            tmp.write_text(json.dumps(datos, default=_a_json, ensure_ascii=False), "utf-8")
            tmp.replace(self.archivo)
        except (OSError, TypeError, ValueError):
            pass

    def _ultima_actualizacion(self) -> dt.datetime | None:
        fechas = [d["actualizado_en"] for d in (self._docs or {}).values()
                  if isinstance(d.get("actualizado_en"), dt.datetime)]
        return max(fechas) if fechas else None

    def todos(self, forzar: bool = False) -> list[dict]:
        with self._lock:
            ahora = dt.datetime.now(dt.timezone.utc)
            if self._docs is None and not forzar:
                self._leer_disco()
            vieja = self._completa_en is None or ahora - self._completa_en > RECARGA_COMPLETA
            if forzar or self._docs is None or vieja:
                self._docs = {d["_id"]: d for d in self.fs.consultar(self.coleccion)}
                self._completa_en = ahora
                self._guardar_disco()
            elif self._consultado_en is None or ahora - self._consultado_en > SIN_CONSULTAR:
                desde = self._ultima_actualizacion()
                filtros = [("actualizado_en", "GREATER_THAN", desde - SOLAPAMIENTO)] if desde else []
                cambiados = self.fs.consultar(self.coleccion, filtros=filtros)
                if cambiados:
                    for d in cambiados:
                        self._docs[d["_id"]] = d
                    self._guardar_disco()
            self._consultado_en = ahora
            return list(self._docs.values())

    def poner(self, doc: dict | None, borrar: str | None = None) -> None:
        """Lo que escribe este equipo se agrega a la caché sin volver a leer."""
        with self._lock:
            if self._docs is None:
                return
            if borrar:
                self._docs.pop(borrar, None)
            if doc and doc.get("_id"):
                self._docs[doc["_id"]] = doc
            self._guardar_disco()

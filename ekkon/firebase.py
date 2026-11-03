"""Clientes REST de Firebase Auth y Cloud Firestore.

Se usa la API REST con el token del usuario (no el Admin SDK), así las reglas
de seguridad de Firestore se aplican siempre, también desde el .exe.
"""
from __future__ import annotations

import base64
import datetime as dt
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from urllib.parse import quote

import requests

from . import settings

TIMEOUT = 30

MENSAJES_ERROR = {
    "INVALID_LOGIN_CREDENTIALS": "Correo o contraseña incorrectos.",
    "INVALID_PASSWORD": "Correo o contraseña incorrectos.",
    "EMAIL_NOT_FOUND": "Correo o contraseña incorrectos.",
    "INVALID_EMAIL": "El correo no es válido.",
    "USER_DISABLED": "El usuario está deshabilitado.",
    "EMAIL_EXISTS": "Ya existe un usuario con ese correo.",
    "WEAK_PASSWORD": "La contraseña debe tener al menos 6 caracteres.",
    "TOO_MANY_ATTEMPTS_TRY_LATER": "Demasiados intentos. Espere unos minutos.",
    "TOKEN_EXPIRED": "La sesión venció. Inicie sesión nuevamente.",
    "INVALID_REFRESH_TOKEN": "La sesión venció. Inicie sesión nuevamente.",
    "PERMISSION_DENIED": "No tiene permisos para esta acción o su usuario fue bloqueado.",
    "ALREADY_EXISTS": "El registro ya existe.",
    "NOT_FOUND": "No se encontró el registro.",
    "CONFIGURATION_NOT_FOUND": "Falta habilitar el acceso con correo y contraseña en Firebase.",
    "OPERATION_NOT_ALLOWED": "Falta habilitar el acceso con correo y contraseña en Firebase.",
    "SIN_CONEXION": "No hay conexión con el servidor. Revise internet.",
}


class FirebaseError(Exception):
    def __init__(self, codigo: str, detalle: str = ""):
        self.codigo = codigo
        self.detalle = detalle
        base = codigo.split(":")[0].strip()
        super().__init__(MENSAJES_ERROR.get(base, detalle or codigo))


def _post(url: str, **kwargs) -> dict:
    return _request("POST", url, **kwargs)


def _request(metodo: str, url: str, **kwargs) -> dict:
    try:
        r = requests.request(metodo, url, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as exc:  # pragma: no cover - red
        raise FirebaseError("SIN_CONEXION", str(exc)) from exc
    if r.status_code >= 400:
        try:
            err = r.json().get("error", {})
        except ValueError:
            err = {}
        if isinstance(err, str):
            raise FirebaseError(err.upper(), err)
        mensaje = str(err.get("message", ""))
        # Auth devuelve el código en "message" (ej. INVALID_LOGIN_CREDENTIALS);
        # Firestore lo devuelve en "status" (ej. PERMISSION_DENIED).
        primero = mensaje.split(":")[0].strip()
        if primero and primero.replace("_", "").isalnum() and primero.upper() == primero:
            codigo = primero
        else:
            codigo = err.get("status") or f"HTTP_{r.status_code}"
        raise FirebaseError(codigo, mensaje or r.text)
    return r.json() if r.content else {}


# ---------------------------------------------------------------- Auth

@dataclass
class Sesion:
    uid: str
    email: str
    id_token: str
    refresh_token: str
    vence: float = 0.0

    def vigente(self) -> bool:
        return time.time() < self.vence - 120


class Auth:
    URL = "https://identitytoolkit.googleapis.com/v1/accounts"
    URL_TOKEN = "https://securetoken.googleapis.com/v1/token"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or settings.FIREBASE_API_KEY

    def _url(self, accion: str) -> str:
        return f"{self.URL}:{accion}?key={self.api_key}"

    def iniciar_sesion(self, email: str, password: str) -> Sesion:
        d = _post(self._url("signInWithPassword"),
                  json={"email": email.strip(), "password": password, "returnSecureToken": True})
        return Sesion(d["localId"], d["email"], d["idToken"], d["refreshToken"],
                      time.time() + int(d.get("expiresIn", 3600)))

    def renovar(self, refresh_token: str, email: str = "") -> Sesion:
        d = _post(f"{self.URL_TOKEN}?key={self.api_key}",
                  data={"grant_type": "refresh_token", "refresh_token": refresh_token})
        return Sesion(d["user_id"], email, d["id_token"], d["refresh_token"],
                      time.time() + int(d.get("expires_in", 3600)))

    def crear_usuario(self, email: str, password: str) -> str:
        """Crea la cuenta en Firebase Auth y devuelve su uid (no cambia la sesión actual)."""
        d = _post(self._url("signUp"),
                  json={"email": email.strip(), "password": password, "returnSecureToken": True})
        return d["localId"]

    def enviar_reset(self, email: str) -> None:
        _post(self._url("sendOobCode"), json={"requestType": "PASSWORD_RESET", "email": email.strip()})


# ---------------------------------------------------------------- Firestore: valores

def codificar(v: Any) -> dict:
    if v is None:
        return {"nullValue": None}
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        return {"integerValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, (bytes, bytearray)):
        return {"bytesValue": base64.b64encode(bytes(v)).decode()}
    if isinstance(v, dt.datetime):
        if v.tzinfo is None:
            v = v.astimezone()
        return {"timestampValue": v.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")}
    if isinstance(v, (list, tuple)):
        return {"arrayValue": {"values": [codificar(x) for x in v]}}
    if isinstance(v, dict):
        return {"mapValue": {"fields": {k: codificar(x) for k, x in v.items()}}}
    return {"stringValue": str(v)}


def _parse_ts(s: str) -> dt.datetime:
    s = s.rstrip("Z")
    if "." in s:
        base, frac = s.split(".", 1)
        s = f"{base}.{frac[:6]}"
    return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)


def decodificar(v: dict) -> Any:
    if "nullValue" in v:
        return None
    if "booleanValue" in v:
        return v["booleanValue"]
    if "integerValue" in v:
        return int(v["integerValue"])
    if "doubleValue" in v:
        return float(v["doubleValue"])
    if "stringValue" in v:
        return v["stringValue"]
    if "bytesValue" in v:
        return base64.b64decode(v["bytesValue"])
    if "timestampValue" in v:
        return _parse_ts(v["timestampValue"])
    if "arrayValue" in v:
        return [decodificar(x) for x in v["arrayValue"].get("values", [])]
    if "mapValue" in v:
        return {k: decodificar(x) for k, x in v["mapValue"].get("fields", {}).items()}
    if "referenceValue" in v:
        return v["referenceValue"]
    if "geoPointValue" in v:
        return v["geoPointValue"]
    return None


def documento_a_dict(doc: dict) -> dict:
    datos = {k: decodificar(v) for k, v in doc.get("fields", {}).items()}
    datos["_id"] = doc["name"].rsplit("/", 1)[-1]
    return datos


# ---------------------------------------------------------------- Firestore: cliente

class Firestore:
    def __init__(self, token: Callable[[], str], project_id: str | None = None):
        self._token = token
        pid = project_id or settings.FIREBASE_PROJECT_ID
        self.raiz = f"projects/{pid}/databases/(default)/documents"
        self.base = f"https://firestore.googleapis.com/v1/{self.raiz}"

    def _h(self) -> dict:
        return {"Authorization": f"Bearer {self._token()}"}

    @staticmethod
    def _ruta(ruta: str) -> str:
        return "/".join(quote(p, safe="") for p in ruta.strip("/").split("/"))

    def obtener(self, ruta: str) -> dict | None:
        try:
            return documento_a_dict(_request("GET", f"{self.base}/{self._ruta(ruta)}", headers=self._h()))
        except FirebaseError as e:
            if e.codigo.startswith("NOT_FOUND") or "not found" in e.detalle.lower():
                return None
            raise

    def crear(self, coleccion: str, doc_id: str, datos: dict) -> dict:
        """Crea el documento; falla con ALREADY_EXISTS si ya existe."""
        d = _post(f"{self.base}/{self._ruta(coleccion)}",
                  params={"documentId": doc_id}, headers=self._h(),
                  json={"fields": {k: codificar(v) for k, v in datos.items()}})
        return documento_a_dict(d)

    def actualizar(self, ruta: str, campos: dict, debe_existir: bool = True) -> dict:
        params: list[tuple[str, str]] = [("updateMask.fieldPaths", k) for k in campos]
        if debe_existir:
            params.append(("currentDocument.exists", "true"))
        d = _request("PATCH", f"{self.base}/{self._ruta(ruta)}", params=params, headers=self._h(),
                     json={"fields": {k: codificar(v) for k, v in campos.items()}})
        return documento_a_dict(d)

    def guardar(self, ruta: str, datos: dict) -> dict:
        """Crea o reemplaza el documento completo."""
        d = _request("PATCH", f"{self.base}/{self._ruta(ruta)}", headers=self._h(),
                     json={"fields": {k: codificar(v) for k, v in datos.items()}})
        return documento_a_dict(d)

    def borrar(self, ruta: str) -> None:
        _request("DELETE", f"{self.base}/{self._ruta(ruta)}", headers=self._h())

    def listar(self, coleccion: str, tamanio: int = 300) -> list[dict]:
        salida, token = [], None
        while True:
            params = {"pageSize": tamanio}
            if token:
                params["pageToken"] = token
            d = _request("GET", f"{self.base}/{self._ruta(coleccion)}", params=params, headers=self._h())
            salida += [documento_a_dict(x) for x in d.get("documents", [])]
            token = d.get("nextPageToken")
            if not token:
                return salida

    def consultar(self, coleccion: str, orden: Iterable[tuple[str, str]] = (),
                  filtros: Iterable[tuple[str, str, Any]] = (), limite: int | None = None,
                  padre: str = "") -> list[dict]:
        """runQuery simple. filtros: (campo, op, valor) con op EQUAL, GREATER_THAN_OR_EQUAL, etc."""
        q: dict = {"from": [{"collectionId": coleccion}]}
        filtros = list(filtros)
        if filtros:
            ff = [{"fieldFilter": {"field": {"fieldPath": c}, "op": op, "value": codificar(v)}}
                  for c, op, v in filtros]
            q["where"] = ff[0] if len(ff) == 1 else {"compositeFilter": {"op": "AND", "filters": ff}}
        orden = list(orden)
        if orden:
            q["orderBy"] = [{"field": {"fieldPath": c}, "direction": d} for c, d in orden]
        if limite:
            q["limit"] = limite
        url = f"{self.base}/{self._ruta(padre)}:runQuery" if padre else f"{self.base}:runQuery"
        filas = _post(url, headers=self._h(), json={"structuredQuery": q})
        return [documento_a_dict(f["document"]) for f in filas if "document" in f]

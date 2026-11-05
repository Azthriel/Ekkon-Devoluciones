"""Archivos locales del usuario: sesión recordada y fotos para adjuntar."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def carpeta_datos() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(Path.home(), ".local", "share")
    p = Path(base) / "EkkonDevoluciones"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _archivo_sesion() -> Path:
    return carpeta_datos() / "sesion.json"


def guardar_sesion(email: str, refresh_token: str) -> None:
    _archivo_sesion().write_text(json.dumps({"email": email, "refresh_token": refresh_token}), "utf-8")


def leer_sesion() -> dict | None:
    try:
        return json.loads(_archivo_sesion().read_text("utf-8"))
    except (OSError, ValueError):
        return None


def borrar_sesion() -> None:
    try:
        _archivo_sesion().unlink()
    except OSError:
        pass


def carpeta_fotos(numero_venta: str) -> Path:
    p = carpeta_datos() / "fotos" / numero_venta
    p.mkdir(parents=True, exist_ok=True)
    return p


def guardar_fotos(numero_venta: str, fotos: list[bytes]) -> Path:
    carpeta = carpeta_fotos(numero_venta)
    for viejo in carpeta.glob("*.jpg"):
        viejo.unlink(missing_ok=True)
    for i, data in enumerate(fotos, 1):
        (carpeta / f"{numero_venta}_{i:02d}.jpg").write_bytes(data)
    return carpeta


def abrir_carpeta(ruta: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(ruta))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(ruta)])
        else:
            subprocess.Popen(["xdg-open", str(ruta)])
    except OSError:
        pass


def ruta_chrome() -> str | None:
    """Ubicación de chrome.exe en Windows (instalación para todos o para el usuario)."""
    if not sys.platform.startswith("win"):
        return None
    for base in (os.environ.get("PROGRAMFILES"), os.environ.get("PROGRAMFILES(X86)"), os.environ.get("LOCALAPPDATA")):
        if base:
            ruta = Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"
            if ruta.exists():
                return str(ruta)
    return None


def abrir_url(url: str, page=None) -> None:
    """Abre el link en Google Chrome si está instalado; si no, en el navegador predeterminado."""
    chrome = ruta_chrome()
    if chrome:
        try:
            subprocess.Popen([chrome, url])
            return
        except OSError:
            pass
    if page is not None:
        page.launch_url(url)
    else:
        import webbrowser
        webbrowser.open(url)

"""Escáner de códigos de barras con la cámara del celular (solo en el .apk; extensión flet_camara)."""
from __future__ import annotations

from typing import Any, Optional

from flet.core.control import Control


class Escaner(Control):
    """Control invisible: va en page.overlay. escanear() abre la cámara y devuelve el código leído."""

    def __init__(self, data: Any = None):
        Control.__init__(self, data=data)

    def _get_control_name(self):
        return "ekkon_escaner"

    def _resultado(self, out) -> Optional[str]:
        if not out:
            return None
        if str(out).startswith("ERROR:"):
            raise RuntimeError(str(out)[6:].strip())
        return str(out).strip()

    def escanear(self, espera: float = 600) -> Optional[str]:
        """Código leído; None si se cerró sin leer. RuntimeError si la cámara falló."""
        return self._resultado(self.invoke_method("escanear", {}, wait_for_result=True, wait_timeout=espera))

    def analizar(self, ruta: str, espera: float = 60) -> Optional[str]:
        """Código de barras de una imagen guardada (para la prueba automática)."""
        return self._resultado(self.invoke_method("analizar", {"ruta": ruta}, wait_for_result=True,
                                                  wait_timeout=espera))

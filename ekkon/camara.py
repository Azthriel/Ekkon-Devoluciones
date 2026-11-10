"""Cámara del celular (solo en el .apk). La parte de Flutter está en extensiones/flet_camara."""
from __future__ import annotations

from typing import Any, Optional

from flet.core.control import Control


class Camara(Control):
    """Control invisible: va en page.overlay. tomar_foto() abre la cámara y devuelve la ruta de la foto."""

    def __init__(self, data: Any = None):
        Control.__init__(self, data=data)

    def _get_control_name(self):
        return "ekkon_camara"

    def tomar_foto(self, lado_maximo: int = 2000, espera: float = 900) -> Optional[str]:
        """Ruta del archivo de la foto, None si se canceló. Lanza RuntimeError si la cámara falló."""
        out = self.invoke_method("tomar_foto", {"max": str(lado_maximo)}, wait_for_result=True,
                                 wait_timeout=espera)
        if not out:
            return None
        if str(out).startswith("ERROR:"):
            raise RuntimeError(str(out)[6:].strip())
        return str(out)

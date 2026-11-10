"""Piezas visuales compartidas."""
from __future__ import annotations

import datetime as dt

import flet as ft

from .. import settings

COLOR_SEMILLA = "#1F4E8C"

# Se pone en True al iniciar en un celular (Android): cambia la disposición de pantallas y algunos textos
MOVIL = False


def es_movil() -> bool:
    return MOVIL


def fila(controles: list, spacing: int = 16, **kw) -> ft.Control:
    """Campos uno al lado del otro en la PC; uno debajo del otro (a todo el ancho) en el celular."""
    if MOVIL:
        return ft.Column(controles, spacing=12, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
    kw.setdefault("vertical_alignment", ft.CrossAxisAlignment.START)
    return ft.Row(controles, wrap=True, spacing=spacing, **kw)


def pegar() -> str:
    """Cómo se pega en este equipo, para los textos de ayuda."""
    return "mantenga presionado y toque Pegar" if MOVIL else "Ctrl+V"

COLOR_ESTADO = {
    "cargada": ft.Colors.BLUE_GREY,
    "reclamo_armado": ft.Colors.INDIGO,
    "sin_reclamo": ft.Colors.GREY,
    "reclamado": ft.Colors.AMBER_800,
    "pendiente": ft.Colors.ORANGE_800,
    "cobertura": ft.Colors.GREEN_700,
    "sin_cobertura": ft.Colors.RED_700,
    "cancelacion": ft.Colors.PURPLE_700,
}


def chip_estado(estado: str) -> ft.Control:
    color = COLOR_ESTADO.get(estado, ft.Colors.GREY)
    return ft.Container(
        ft.Text(settings.ESTADOS.get(estado, estado or "—"), size=12, weight=ft.FontWeight.W_600, color=color),
        padding=ft.padding.symmetric(3, 10),
        border_radius=20,
        bgcolor=ft.Colors.with_opacity(0.12, color),
    )


def titulo(texto: str, subtitulo: str | None = None) -> ft.Control:
    filas: list[ft.Control] = [ft.Text(texto, size=20 if MOVIL else 24, weight=ft.FontWeight.W_700)]
    if subtitulo:
        filas.append(ft.Text(subtitulo, size=12 if MOVIL else 13, color=ft.Colors.ON_SURFACE_VARIANT))
    return ft.Column(filas, spacing=2)


def encabezado(titulo_ctrl: ft.Control, *acciones: ft.Control) -> ft.Control:
    """Título con botones a la derecha (en el celular, los botones van debajo)."""
    if MOVIL:
        return ft.Column([titulo_ctrl, ft.Row(list(acciones), wrap=True, spacing=8, run_spacing=8)]
                         if acciones else [titulo_ctrl], spacing=8)
    return ft.Row([titulo_ctrl, *acciones], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                  vertical_alignment=ft.CrossAxisAlignment.START)


def tarjeta_lista(contenido: ft.Control, al_tocar) -> ft.Control:
    """Fila de un listado en el celular (en lugar de la tabla)."""
    return ft.Container(contenido, padding=ft.padding.symmetric(10, 14), border_radius=12, ink=True,
                        on_click=lambda _: al_tocar(),
                        bgcolor=ft.Colors.with_opacity(0.45, ft.Colors.SURFACE_CONTAINER_HIGHEST),
                        border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT))


def tarjeta(contenido: ft.Control, padding: int = 20, expand: bool = False) -> ft.Control:
    return ft.Container(
        contenido,
        padding=min(padding, 12) if MOVIL else padding,
        expand=expand,
        border_radius=14,
        bgcolor=ft.Colors.with_opacity(0.45, ft.Colors.SURFACE_CONTAINER_HIGHEST),
        border=ft.border.all(1, ft.Colors.OUTLINE_VARIANT),
    )


def seccion(texto: str) -> ft.Control:
    return ft.Text(texto, size=15, weight=ft.FontWeight.W_600, color=ft.Colors.PRIMARY)


def fecha_corta(valor) -> str:
    if isinstance(valor, dt.datetime):
        return valor.astimezone().strftime("%d/%m/%Y %H:%M")
    if isinstance(valor, str) and len(valor) == 10 and valor[4] == "-":
        a, m, d = valor.split("-")
        return f"{d}/{m}/{a}"
    return valor or "—"


def hoy_iso() -> str:
    return dt.date.today().isoformat()

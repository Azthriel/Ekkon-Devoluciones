"""Piezas visuales compartidas."""
from __future__ import annotations

import datetime as dt

import flet as ft

from .. import settings

COLOR_SEMILLA = "#1F4E8C"

COLOR_ESTADO = {
    "cargada": ft.Colors.BLUE_GREY,
    "reclamo_armado": ft.Colors.INDIGO,
    "sin_reclamo": ft.Colors.GREY,
    "reclamado": ft.Colors.AMBER_800,
    "pendiente": ft.Colors.ORANGE_800,
    "cobertura": ft.Colors.GREEN_700,
    "sin_cobertura": ft.Colors.RED_700,
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
    filas: list[ft.Control] = [ft.Text(texto, size=24, weight=ft.FontWeight.W_700)]
    if subtitulo:
        filas.append(ft.Text(subtitulo, size=13, color=ft.Colors.ON_SURFACE_VARIANT))
    return ft.Column(filas, spacing=2)


def tarjeta(contenido: ft.Control, padding: int = 20, expand: bool = False) -> ft.Control:
    return ft.Container(
        contenido,
        padding=padding,
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

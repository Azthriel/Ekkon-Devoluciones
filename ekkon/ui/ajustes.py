"""Ajustes generales (solo administrador)."""
from __future__ import annotations

import flet as ft

from ..firebase import FirebaseError
from ..version import VERSION
from .comun import seccion, tarjeta, titulo


class VistaAjustes:
    def __init__(self, app):
        self.app = app
        self.page: ft.Page = app.page

    def control(self) -> ft.Control:
        c = self.app.config
        claude = ft.TextField(label="Link del proyecto de Claude para armar reclamos",
                              value=c.get("claude_project_url", ""), hint_text="https://claude.ai/project/…")
        ultima = ft.TextField(label="Última versión publicada", value=c.get("ultima_version", ""), width=260,
                              hint_text=VERSION)
        minima = ft.TextField(label="Versión mínima permitida", value=c.get("version_minima", ""), width=260,
                              helper_text="Las versiones anteriores quedan bloqueadas.")
        descarga = ft.TextField(label="Link de descarga", value=c.get("url_descarga", ""),
                                hint_text="https://github.com/Azthriel/Ekkon-Devoluciones/releases/latest")

        def guardar(_):
            campos = {"claude_project_url": claude.value.strip(), "ultima_version": ultima.value.strip(),
                      "version_minima": minima.value.strip(), "url_descarga": descarga.value.strip()}
            try:
                self.app.cfg.guardar(campos)
                self.app.config.update(campos)
                self.app.avisar("Ajustes guardados.")
            except FirebaseError as e:
                self.app.manejar_error(e)

        return ft.Column([
            titulo("Ajustes", f"Versión instalada: {VERSION}"),
            tarjeta(ft.Column([seccion("Reclamos"), claude], spacing=14)),
            tarjeta(ft.Column([seccion("Actualizaciones"), ft.Row([ultima, minima], spacing=16), descarga],
                              spacing=14)),
            ft.Row([ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar, height=46)]),
        ], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

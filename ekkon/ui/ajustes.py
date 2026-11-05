"""Ajustes generales (solo administrador)."""
from __future__ import annotations

import flet as ft

from .. import sheets
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
        planilla = ft.TextField(label="Link de la planilla \"Devoluciones nuevo\" (Google Sheets)",
                                value=c.get("planilla_url", ""),
                                hint_text="https://docs.google.com/spreadsheets/d/…")
        para_transf = ft.TextField(label="Destinatarios del email de transferencia",
                                   value=c.get("email_transferencia_para", ""),
                                   helper_text="Separados por coma. Ej.: logistica@…, service@…")
        ultima = ft.TextField(label="Última versión publicada", value=c.get("ultima_version", ""), width=260,
                              hint_text=VERSION)
        minima = ft.TextField(label="Versión mínima permitida", value=c.get("version_minima", ""), width=260,
                              helper_text="Las versiones anteriores quedan bloqueadas.")
        descarga = ft.TextField(label="Link de descarga", value=c.get("url_descarga", ""),
                                hint_text="https://github.com/Azthriel/Ekkon-Devoluciones/releases/latest")

        estado_clave = ft.Text()
        selector = ft.FilePicker()
        self.page.overlay.append(selector)

        def pintar_clave():
            info = sheets.leer_clave()
            if info:
                estado_clave.value = f"Clave cargada en esta PC: {info.get('client_email', '')}"
                estado_clave.color = ft.Colors.GREEN_800
            else:
                estado_clave.value = "No hay clave cargada en esta PC."
                estado_clave.color = ft.Colors.ERROR

        def clave_elegida(e: ft.FilePickerResultEvent):
            if not e.files:
                return
            try:
                email = sheets.guardar_clave(e.files[0].path)
                self.app.avisar(f"Clave guardada. Comparta la planilla como Editor con {email}.")
            except sheets.SheetsError as err:
                self.app.avisar(str(err), error=True)
            pintar_clave()
            self.page.update()

        selector.on_result = clave_elegida

        def probar(_):
            link = planilla.value.strip()
            try:
                p = sheets.Planilla(sheets.id_de_link(link))
                hoja = p.leer()
                ultima_fila = hoja.numero_fila(hoja.ultima_con_venta())
                self.app.avisar(f"Conexión correcta: hoja \"{p.hoja}\", última venta en la fila {ultima_fila}.")
            except (sheets.SheetsError, ValueError) as err:
                self.app.avisar(str(err), error=True)

        def guardar(_):
            link = planilla.value.strip()
            if link and not sheets.id_de_link(link):
                self.app.avisar("El link de la planilla no parece válido.", error=True)
                return
            campos = {"claude_project_url": claude.value.strip(), "planilla_url": link,
                      "email_transferencia_para": para_transf.value.strip(),
                      "ultima_version": ultima.value.strip(), "version_minima": minima.value.strip(),
                      "url_descarga": descarga.value.strip()}
            try:
                self.app.cfg.guardar(campos)
                self.app.config.update(campos)
                self.app.avisar("Ajustes guardados.")
            except FirebaseError as err:
                self.app.manejar_error(err)

        pintar_clave()
        return ft.Column([
            titulo("Ajustes", f"Versión instalada: {VERSION}"),
            tarjeta(ft.Column([seccion("Reclamos"), claude], spacing=14)),
            tarjeta(ft.Column([
                seccion("Planilla de Google Sheets"),
                planilla,
                ft.Text("Clave de la cuenta de servicio (archivo .json). Se guarda solo en esta PC.", size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Row([ft.OutlinedButton("Cargar clave .json", icon=ft.Icons.KEY,
                                          on_click=lambda _: selector.pick_files(
                                              dialog_title="Elegir la clave de la cuenta de servicio",
                                              allowed_extensions=["json"])),
                        ft.OutlinedButton("Probar conexión", icon=ft.Icons.WIFI_TETHERING, on_click=probar),
                        estado_clave], wrap=True, spacing=12),
            ], spacing=14)),
            tarjeta(ft.Column([seccion("Emails"), para_transf], spacing=14)),
            tarjeta(ft.Column([seccion("Actualizaciones"), ft.Row([ultima, minima], spacing=16), descarga],
                              spacing=14)),
            ft.Row([ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar, height=46)]),
        ], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

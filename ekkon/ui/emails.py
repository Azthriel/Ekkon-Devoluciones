"""Email de solicitud de transferencia, armado desde la planilla.

Toma las filas con Transferencia = "A la espera de movimiento". El origen es siempre
Service Podestá (al hacer la NC la unidad entra ahí); el destino sale de "Deposito final".
"""
from __future__ import annotations

from urllib.parse import quote

import flet as ft

from .. import settings
from ..firebase import FirebaseError
from ..planilla import C_TRANSF, EMAIL_ENVIADO, email_transferencia, letra_columna, pendientes
from ..sheets import SheetsError
from .comun import fecha_corta, seccion, tarjeta, titulo
from .sincronizar import abrir_planilla


class VistaEmails:
    def __init__(self, app):
        self.app = app
        self.page: ft.Page = app.page
        self.hoja = None
        self.planilla = None
        self.items: list = []
        self.marcados: set = set()
        self.panel = ft.Column(spacing=12)
        self.estado = ft.Text("", color=ft.Colors.ON_SURFACE_VARIANT)
        self.progreso = ft.ProgressBar(visible=False)

    def control(self) -> ft.Control:
        vista = ft.Column([
            ft.Row([titulo("Email de transferencia",
                           f"Filas de la planilla con Transferencia = \"A la espera de movimiento\". "
                           f"Origen: {settings.ORIGEN_TRANSFERENCIA}."),
                    ft.FilledTonalButton("Leer planilla", icon=ft.Icons.REFRESH, on_click=lambda _: self.cargar())],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            self.progreso, self.estado, self.panel,
        ], spacing=12, expand=True, scroll=ft.ScrollMode.AUTO)
        self.cargar(actualizar=False)
        return vista

    def _update(self):
        try:
            self.page.update()
        except Exception:  # noqa: BLE001
            pass

    def cargar(self, actualizar: bool = True) -> None:
        self.progreso.visible = True
        if actualizar:
            self._update()
        try:
            self.planilla = abrir_planilla(self.app)
            self.hoja = self.planilla.leer()
            self.items = pendientes(self.hoja, self.app.config.get("modelos_por_sku") or {})
            self.marcados = {it.fila for it in self.items}
            self.estado.value = f"{len(self.items)} fila(s) a la espera de movimiento."
            self.estado.color = ft.Colors.ON_SURFACE_VARIANT
        except (SheetsError, ValueError) as e:
            self.estado.value = str(e)
            self.estado.color = ft.Colors.ERROR
            self.items = []
        self.progreso.visible = False
        self._pintar()
        self._update()

    def _recordar_modelos(self, items) -> None:
        nuevos = {it.sku: it.producto for it in items if it.editado and it.sku and it.producto}
        if not nuevos:
            return
        modelos = dict(self.app.config.get("modelos_por_sku") or {})
        modelos.update(nuevos)
        try:
            self.app.cfg.guardar({"modelos_por_sku": modelos})
            self.app.config["modelos_por_sku"] = modelos
        except FirebaseError:
            pass  # no es crítico: la próxima vez se vuelve a corregir

    def _seleccionados(self):
        return [it for it in self.items if it.fila in self.marcados]

    def _pintar(self) -> None:
        if not self.items:
            self.panel.controls = [tarjeta(ft.Row([ft.Icon(ft.Icons.INBOX, color=ft.Colors.OUTLINE),
                                                   ft.Text("No hay filas a la espera de movimiento.")]))]
            return
        vista_previa = ft.TextField(multiline=True, read_only=True, min_lines=10, max_lines=18,
                                    text_style=ft.TextStyle(font_family="Consolas", size=13))
        asunto_txt = ft.Text(weight=ft.FontWeight.W_600, selectable=True)

        def refrescar(_=None):
            asunto, cuerpo = email_transferencia(self._seleccionados())
            asunto_txt.value = f"Asunto: {asunto}"
            vista_previa.value = cuerpo
            self._update()

        def marcar(fila, valor):
            (self.marcados.add if valor else self.marcados.discard)(fila)
            refrescar()

        def producto(it, valor):
            it.producto = (valor or "").strip()
            it.editado = True
            refrescar()

        def destino(it, valor):
            it.destino = (valor or "").strip()
            refrescar()

        def campo(valor, ancho, al_cambiar, ayuda=None):
            return ft.Container(ft.TextField(value=valor, dense=True, text_size=13, tooltip=ayuda,
                                             content_padding=ft.padding.symmetric(8, 10), on_change=al_cambiar),
                                width=ancho)

        filas = []
        for it in self.items:
            filas.append(ft.DataRow([
                ft.DataCell(ft.Checkbox(value=it.fila in self.marcados,
                                        on_change=lambda e, f=it.fila: marcar(f, e.control.value))),
                ft.DataCell(ft.Text(str(it.fila))),
                ft.DataCell(ft.Text(fecha_corta(it.fecha.isoformat()) if it.fecha else "—")),
                ft.DataCell(ft.Text(it.venta, selectable=True)),
                ft.DataCell(ft.Text(it.sku or "—")),
                ft.DataCell(campo(it.producto, 240, lambda e, it=it: producto(it, e.control.value),
                                  "Modelo que va en el email. Si lo corrige, se recuerda para ese SKU.")),
                ft.DataCell(ft.Text(it.clasificacion)),
                ft.DataCell(campo(it.destino, 170, lambda e, it=it: destino(it, e.control.value),
                                  "Sale de la columna \"Deposito final\".")),
            ]))
        tabla = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(c)) for c in
                     ("", "Fila", "Revisión", "Venta", "SKU", "Producto", "Clasif.", "Destino")],
            rows=filas, heading_row_height=38, data_row_min_height=42, data_row_max_height=50, column_spacing=18)

        def destinatarios():
            return (self.app.config.get("email_transferencia_para") or "").strip()

        def copiar(_):
            sel = self._seleccionados()
            self._recordar_modelos(sel)
            self.page.set_clipboard(email_transferencia(sel)[1])
            self.app.avisar("Texto del email copiado.")

        def gmail(_):
            sel = self._seleccionados()
            if not sel:
                self.app.avisar("No hay filas seleccionadas.", error=True)
                return
            self._recordar_modelos(sel)
            asunto, cuerpo = email_transferencia(sel)
            self.page.launch_url("https://mail.google.com/mail/?view=cm&fs=1"
                                 f"&to={quote(destinatarios())}&su={quote(asunto)}&body={quote(cuerpo)}")

        def enviado(_):
            sel = self._seleccionados()
            if not sel:
                self.app.avisar("No hay filas seleccionadas.", error=True)
                return
            col = self.hoja.indice(C_TRANSF)
            if col is None:
                self.app.avisar("No encuentro la columna Transferencia en la planilla.", error=True)
                return

            def hacer():
                try:
                    self.planilla.escribir([(f"{letra_columna(col)}{it.fila}", EMAIL_ENVIADO) for it in sel])
                except SheetsError as e:
                    self.app.avisar(str(e), error=True)
                    return
                self._recordar_modelos(sel)
                self.app.avisar(f"Se marcó \"{EMAIL_ENVIADO}\" en {len(sel)} fila(s).")
                self.cargar()

            self.app.confirmar("Marcar como enviado",
                               f"En la columna Transferencia se reemplaza \"A la espera de movimiento\" por "
                               f"\"{EMAIL_ENVIADO}\" en {len(sel)} fila(s). ¿Continuar?", hacer, "Marcar")

        para = destinatarios()
        self.panel.controls = [
            tarjeta(ft.Column([ft.Row([tabla], scroll=ft.ScrollMode.AUTO)]), padding=8),
            tarjeta(ft.Column([
                seccion("Vista previa"),
                ft.Text(f"Para: {para}" if para else "Para: (configure los destinatarios en Ajustes)",
                        color=None if para else ft.Colors.ERROR),
                asunto_txt, vista_previa,
                ft.Row([ft.FilledButton("Abrir en Gmail", icon=ft.Icons.MAIL, on_click=gmail),
                        ft.OutlinedButton("Copiar texto", icon=ft.Icons.COPY, on_click=copiar),
                        ft.OutlinedButton("Marcar como enviado en la planilla", icon=ft.Icons.DONE_ALL,
                                          on_click=enviado)], wrap=True),
            ], spacing=10)),
        ]
        asunto, cuerpo = email_transferencia(self._seleccionados())
        asunto_txt.value = f"Asunto: {asunto}"
        vista_previa.value = cuerpo

"""Emails de transferencia (productos nuevos) y de baja/alta outlet, armados desde la planilla."""
from __future__ import annotations

from urllib.parse import quote

import flet as ft

from ..planilla import EMAIL_ENVIADO, C_TRANSF, email_outlet, email_transferencia, letra_columna, pendientes
from ..firebase import FirebaseError
from ..sheets import SheetsError
from .comun import fecha_corta, seccion, tarjeta, titulo
from .sincronizar import abrir_planilla

TIPOS = {
    "transferencia": ("Transferencia Service Podestá → Podestá",
                      "NC realizadas de productos nuevos (clasificación N) que todavía no tienen transferencia.",
                      email_transferencia, "email_transferencia_para"),
    "outlet": ("Baja SKU nuevo / alta SKU outlet",
               "NC realizadas de productos A, B y C que todavía no tienen el movimiento a Outlet Podestá.",
               email_outlet, "email_outlet_para"),
}


class VistaEmails:
    def __init__(self, app):
        self.app = app
        self.page: ft.Page = app.page
        self.hoja = None
        self.planilla = None
        self.items: dict[str, list] = {"transferencia": [], "outlet": []}
        self.marcados: dict[str, set] = {"transferencia": set(), "outlet": set()}
        self.paneles = {t: ft.Column(spacing=12) for t in TIPOS}
        self.estado = ft.Text("", color=ft.Colors.ON_SURFACE_VARIANT)
        self.progreso = ft.ProgressBar(visible=False)

    def control(self) -> ft.Control:
        self.tabs = ft.Tabs(
            selected_index=0, animation_duration=200, expand=True,
            tabs=[ft.Tab(text=TIPOS[t][0], content=ft.Container(
                ft.Column([self.paneles[t]], scroll=ft.ScrollMode.AUTO, expand=True), padding=ft.padding.only(top=14)))
                for t in TIPOS])
        vista = ft.Column([
            ft.Row([titulo("Emails", "Se arman con las filas de la planilla que tienen NdC = Si y la columna "
                                     "Transferencia vacía."),
                    ft.FilledTonalButton("Leer planilla", icon=ft.Icons.REFRESH, on_click=lambda _: self.cargar())],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            self.progreso, self.estado, self.tabs,
        ], spacing=12, expand=True)
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
            for t in TIPOS:
                self.items[t] = pendientes(self.hoja, t, self.app.config.get("modelos_por_sku") or {})
                self.marcados[t] = {it.fila for it in self.items[t]}
            self.estado.value = (f"{len(self.items['transferencia'])} pendiente(s) de transferencia y "
                                 f"{len(self.items['outlet'])} de baja/alta outlet.")
            self.estado.color = ft.Colors.ON_SURFACE_VARIANT
        except (SheetsError, ValueError) as e:
            self.estado.value = str(e)
            self.estado.color = ft.Colors.ERROR
            for t in TIPOS:
                self.items[t] = []
        self.progreso.visible = False
        for t in TIPOS:
            self._pintar(t)
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

    def _seleccionados(self, tipo):
        return [it for it in self.items[tipo] if it.fila in self.marcados[tipo]]

    def _pintar(self, tipo: str) -> None:
        nombre, ayuda, armar, clave_para = TIPOS[tipo]
        items = self.items[tipo]
        panel = self.paneles[tipo]
        if not items:
            panel.controls = [tarjeta(ft.Row([ft.Icon(ft.Icons.INBOX, color=ft.Colors.OUTLINE),
                                              ft.Text("No hay pendientes para este email.")]))]
            return
        vista_previa = ft.TextField(multiline=True, read_only=True, min_lines=10, max_lines=18,
                                    text_style=ft.TextStyle(font_family="Consolas", size=13))
        asunto_txt = ft.Text(weight=ft.FontWeight.W_600, selectable=True)

        def refrescar(_=None):
            asunto, cuerpo = armar(self._seleccionados(tipo))
            asunto_txt.value = f"Asunto: {asunto}"
            vista_previa.value = cuerpo
            self._update()

        def marcar(fila, valor):
            (self.marcados[tipo].add if valor else self.marcados[tipo].discard)(fila)
            refrescar()

        def sku_outlet(it, valor):
            it.sku_outlet = (valor or "").strip()
            refrescar()

        def producto(it, valor):
            it.producto = (valor or "").strip()
            it.editado = True
            refrescar()

        columnas = ["", "Fila", "Revisión", "Venta", "SKU", "Producto", "Clasif."]
        if tipo == "outlet":
            columnas.append("SKU outlet")
        filas = []
        for it in items:
            celdas = [
                ft.DataCell(ft.Checkbox(value=it.fila in self.marcados[tipo],
                                        on_change=lambda e, f=it.fila: marcar(f, e.control.value))),
                ft.DataCell(ft.Text(str(it.fila))),
                ft.DataCell(ft.Text(fecha_corta(it.fecha.isoformat()) if it.fecha else "—")),
                ft.DataCell(ft.Text(it.venta, selectable=True)),
                ft.DataCell(ft.Text(it.sku or "—")),
                ft.DataCell(ft.Container(ft.TextField(
                    value=it.producto, dense=True, text_size=13, content_padding=ft.padding.symmetric(8, 10),
                    tooltip="Modelo que va en el email. Si lo corrige, se recuerda para ese SKU.",
                    on_change=lambda e, it=it: producto(it, e.control.value)), width=260)),
                ft.DataCell(ft.Text(it.clasificacion)),
            ]
            if tipo == "outlet":
                celdas.append(ft.DataCell(ft.Container(ft.TextField(
                    value=it.sku_outlet, dense=True, text_size=13, hint_text="completar",
                    content_padding=ft.padding.symmetric(8, 10),
                    on_change=lambda e, it=it: sku_outlet(it, e.control.value)), width=150)))
            filas.append(ft.DataRow(celdas))
        tabla = ft.DataTable(columns=[ft.DataColumn(ft.Text(c)) for c in columnas], rows=filas,
                             heading_row_height=38, data_row_min_height=42, data_row_max_height=50,
                             column_spacing=18)

        def destinatarios():
            return (self.app.config.get(clave_para) or "").strip()

        def copiar(_):
            self._recordar_modelos(self._seleccionados(tipo))
            asunto, cuerpo = armar(self._seleccionados(tipo))
            self.page.set_clipboard(cuerpo)
            self.app.avisar("Texto del email copiado.")

        def gmail(_):
            sel = self._seleccionados(tipo)
            if not sel:
                self.app.avisar("No hay filas seleccionadas.", error=True)
                return
            self._recordar_modelos(sel)
            asunto, cuerpo = armar(sel)
            url = ("https://mail.google.com/mail/?view=cm&fs=1"
                   f"&to={quote(destinatarios())}&su={quote(asunto)}&body={quote(cuerpo)}")
            self.page.launch_url(url)

        def enviado(_):
            sel = self._seleccionados(tipo)
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
                               f"Se va a escribir \"{EMAIL_ENVIADO}\" en la columna Transferencia de "
                               f"{len(sel)} fila(s) de la planilla. ¿Continuar?", hacer, "Marcar")

        para = destinatarios()
        panel.controls = [
            ft.Text(ayuda, color=ft.Colors.ON_SURFACE_VARIANT),
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
        asunto, cuerpo = armar(self._seleccionados(tipo))
        asunto_txt.value = f"Asunto: {asunto}"
        vista_previa.value = cuerpo

"""Cancelaciones: carga por número de venta, lista para el remito interno y email de pedidos a Carolina.

Las cancelaciones vuelven como N, en buen estado y sin reclamo. Con nota de crédito o sin ella,
el stock vuelve a Podestá y se valida físicamente con el remito interno.
"""
from __future__ import annotations

import datetime as dt
from urllib.parse import quote

import flet as ft

from .. import settings
from ..datos import email_cancelaciones, lista_remito, validar_numero_venta
from ..firebase import FirebaseError
from ..local import abrir_url
from .comun import fecha_corta, seccion, tarjeta, titulo


class VistaCancelaciones:
    def __init__(self, app):
        self.app = app
        self.page: ft.Page = app.page
        self.cancelaciones: list[dict] = []
        self.sel_remito: set[str] = set()
        self.sel_email: set[str] = set()
        self.info = None          # venta encontrada en el informe
        self.panel_remito = ft.Column(spacing=12)
        self.panel_email = ft.Column(spacing=12)
        self.recientes = ft.Column(spacing=4)
        self._armar_carga()

    # ------------------------------------------------------------ carga

    def _armar_carga(self) -> None:
        self.numero = ft.TextField(label="Venta # o ID Carrito", width=300, prefix_icon=ft.Icons.TAG,
                                   on_change=self._buscar, on_submit=lambda _: self._agregar())
        self.lleva_nc = ft.Switch(label="Lleva nota de crédito", value=True)
        self.pedido = ft.TextField(label="N° de pedido", width=200, hint_text="Sale solo del informe",
                                   tooltip="Se completa con el informe de ventas; si no aparece, escríbalo.")
        self.notas = ft.TextField(label="Notas (opcional)", expand=True)
        self.info_txt = ft.Text("", size=13)
        self.btn = ft.FilledButton("Agregar cancelación", icon=ft.Icons.ADD, on_click=lambda _: self._agregar(),
                                   height=46)

    def _buscar(self, _=None) -> None:
        numero, error, _aviso = validar_numero_venta(self.numero.value)
        self.info = None
        self.info_txt.value, self.info_txt.color = "", None
        if error or len(numero) != 16:
            self._update()
            return
        try:
            r = self.app.indice.buscar(numero)
        except FirebaseError:
            r = None
        if r and r.venta:
            self.info = r.venta
            self.pedido.value = r.venta.pedido or self.pedido.value
            extra = f"ID Carrito {numero} → Venta # {r.venta.venta}. " if r.tipo == "carrito" else ""
            self.info_txt.value = (f"{extra}{r.venta.producto or 'Producto sin nombre'} · SKU {r.venta.codigo or '—'} · "
                                   f"pedido {r.venta.pedido or '—'} · {r.venta.deposito}")
            self.info_txt.color = ft.Colors.GREEN_800
        elif r and r.tipo == "carrito":
            self.info_txt.value = ("Ese carrito tiene varias ventas: cargue el Venta # del producto que volvió.")
            self.info_txt.color = ft.Colors.AMBER_800
        else:
            self.info_txt.value = "No figura en el informe de ventas. Se puede cargar igual; complete el pedido."
            self.info_txt.color = ft.Colors.AMBER_800
        self._update()

    def _agregar(self) -> None:
        numero, error, _ = validar_numero_venta(self.numero.value)
        if error:
            self.app.avisar(error, error=True)
            return
        if self.info is not None and numero in (self.info.venta, self.info.carrito):
            numero = self.info.venta
        try:
            if self.app.devs.obtener(numero):
                self.app.avisar(f"La venta {numero} ya está cargada.", error=True)
                return
            self.app.devs.crear_cancelacion(numero, bool(self.lleva_nc.value), self.info, self.app.usuario,
                                            pedido=(self.pedido.value or "").strip(),
                                            notas=(self.notas.value or "").strip())
        except FirebaseError as e:
            self.app.manejar_error(e)
            return
        self.app.avisar(f"Cancelación {numero} cargada ({'con' if self.lleva_nc.value else 'sin'} NC).")
        self.numero.value = self.pedido.value = self.notas.value = ""
        self.info, self.info_txt.value = None, ""
        self.lleva_nc.value = True
        self.recargar()
        try:
            self.numero.focus()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ vista

    def control(self) -> ft.Control:
        def pestania(texto, contenido):
            return ft.Tab(text=texto, content=ft.Container(
                ft.Column([contenido], scroll=ft.ScrollMode.AUTO, expand=True), padding=ft.padding.only(top=14)))

        vista = ft.Column([
            titulo("Cancelaciones", "Vuelven como N a Podestá. Con o sin NC, se validan con el remito interno."),
            tarjeta(ft.Column([
                seccion("Cargar cancelación"),
                ft.Row([self.numero, self.pedido, self.notas], spacing=16),
                ft.Row([self.lleva_nc, self.btn, ft.Container(self.info_txt, expand=True)], spacing=20,
                       vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ], spacing=12), padding=16),
            ft.Tabs(selected_index=0, animation_duration=200, expand=True, tabs=[
                pestania("Remito interno", self.panel_remito),
                pestania("Email a Carolina (pedidos)", self.panel_email),
                pestania("Últimas cargadas", self.recientes),
            ]),
        ], spacing=14, expand=True)
        self.recargar(actualizar=False)
        return vista

    def _update(self) -> None:
        try:
            self.page.update()
        except Exception:  # noqa: BLE001
            pass

    def recargar(self, actualizar: bool = True) -> None:
        try:
            self.cancelaciones = self.app.devs.cancelaciones()
        except FirebaseError as e:
            self.cancelaciones = []
            self.app.manejar_error(e)
        pend_remito = [d for d in self.cancelaciones if not d.get("remito_hecho")]
        pend_email = [d for d in self.cancelaciones if not d.get("informado_caro")]
        self.sel_remito = {d["numero_venta"] for d in pend_remito}
        self.sel_email = {d["numero_venta"] for d in pend_email}
        self._pintar_remito(pend_remito)
        self._pintar_email(pend_email)
        self._pintar_recientes()
        if actualizar:
            self._update()

    @staticmethod
    def _tabla(filas: list[ft.DataRow], columnas: list[str]) -> ft.Control:
        tabla = ft.DataTable(columns=[ft.DataColumn(ft.Text(c)) for c in columnas], rows=filas,
                             heading_row_height=36, data_row_min_height=38, data_row_max_height=44,
                             column_spacing=18)
        return tarjeta(ft.Row([tabla], scroll=ft.ScrollMode.AUTO), padding=8)

    def _vista_previa(self, texto: str) -> ft.TextField:
        return ft.TextField(value=texto, multiline=True, read_only=True, min_lines=4, max_lines=14,
                            text_style=ft.TextStyle(font_family="Consolas", size=13))

    # ------------------------------------------------------------ remito interno

    def _pintar_remito(self, pendientes: list[dict]) -> None:
        if not pendientes:
            self.panel_remito.controls = [ft.Text("No hay cancelaciones pendientes de remito.")]
            return
        modelos = self.app.config.get("modelos_por_sku") or {}
        previa = self._vista_previa("")
        numero_remito = ft.TextField(label="N° de remito (opcional)", width=200, hint_text="N-00057")

        def refrescar():
            previa.value = lista_remito([d for d in pendientes if d["numero_venta"] in self.sel_remito], modelos)
            self._update()

        def marcar(venta, valor):
            (self.sel_remito.add if valor else self.sel_remito.discard)(venta)
            refrescar()

        filas = [ft.DataRow([
            ft.DataCell(ft.Checkbox(value=True, on_change=lambda e, v=d["numero_venta"]: marcar(v, e.control.value))),
            ft.DataCell(ft.Text(d["numero_venta"], selectable=True)),
            ft.DataCell(ft.Text(d.get("codigo_producto") or "—")),
            ft.DataCell(ft.Text(d.get("producto") or "—", width=320, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)),
            ft.DataCell(ft.Text("Sí" if d.get("lleva_nc") else "No")),
            ft.DataCell(ft.Text(fecha_corta(d.get("cargado_en")))),
        ]) for d in pendientes]

        def copiar(_):
            self.page.set_clipboard(previa.value or "")
            self.app.avisar("Lista copiada. Péguela en el remito de Canva.")

        def hecho(_):
            sel = [d for d in pendientes if d["numero_venta"] in self.sel_remito]
            if not sel:
                self.app.avisar("No hay cancelaciones seleccionadas.", error=True)
                return

            def confirmar():
                ahora = dt.datetime.now(dt.timezone.utc)
                for d in sel:
                    try:
                        self.app.devs.actualizar(d["numero_venta"], {
                            "remito_hecho": True, "remito_en": ahora,
                            "remito_numero": (numero_remito.value or "").strip(),
                            "transferencia": settings.TRANSF_REALIZADA})
                    except FirebaseError as e:
                        self.app.manejar_error(e)
                        return
                self.app.avisar(f"Remito registrado para {len(sel)} cancelación(es). "
                                "En la planilla pasan a \"Realizada\" al sincronizar.")
                self.recargar()

            self.app.confirmar("Remito hecho", f"¿El stock de {len(sel)} cancelación(es) ya llegó a Podestá con el "
                                               "remito interno firmado?", confirmar, "Sí, marcar")

        self.panel_remito.controls = [
            ft.Text("Tilde las que van en este remito. La lista tiene el mismo formato que el email de transferencia.",
                    color=ft.Colors.ON_SURFACE_VARIANT),
            self._tabla(filas, ["", "Venta", "SKU", "Producto", "Lleva NC", "Cargada"]),
            seccion("Lista para el remito"), previa,
            ft.Row([ft.FilledButton("Copiar lista", icon=ft.Icons.COPY, on_click=copiar), numero_remito,
                    ft.OutlinedButton("Marcar remito hecho", icon=ft.Icons.TASK_ALT, on_click=hecho)],
                   wrap=True, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
        ]
        refrescar_inicial = lista_remito(pendientes, modelos)
        previa.value = refrescar_inicial

    # ------------------------------------------------------------ email a Carolina

    def _pintar_email(self, pendientes: list[dict]) -> None:
        if not pendientes:
            self.panel_email.controls = [ft.Text("No hay pedidos de cancelaciones para informar.")]
            return
        previa = self._vista_previa("")
        para = (self.app.config.get("email_cancelaciones_para") or "").strip()

        def seleccion():
            return [d for d in pendientes if d["numero_venta"] in self.sel_email]

        def refrescar():
            previa.value = email_cancelaciones(seleccion())[1]
            self._update()

        def marcar(venta, valor):
            (self.sel_email.add if valor else self.sel_email.discard)(venta)
            refrescar()

        filas = [ft.DataRow([
            ft.DataCell(ft.Checkbox(value=True, on_change=lambda e, v=d["numero_venta"]: marcar(v, e.control.value))),
            ft.DataCell(ft.Text(d.get("pedido") or "Sin pedido",
                                color=None if d.get("pedido") else ft.Colors.ERROR, weight=ft.FontWeight.W_600)),
            ft.DataCell(ft.Text(d["numero_venta"], selectable=True)),
            ft.DataCell(ft.Text(d.get("producto") or "—", width=320, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)),
        ]) for d in pendientes]

        def gmail(_):
            sel = seleccion()
            if not sel:
                self.app.avisar("No hay pedidos seleccionados.", error=True)
                return
            asunto, cuerpo = email_cancelaciones(sel)
            abrir_url(page=self.page, url="https://mail.google.com/mail/?view=cm&fs=1"
                                          f"&to={quote(para)}&su={quote(asunto)}&body={quote(cuerpo)}")

        def copiar(_):
            self.page.set_clipboard(email_cancelaciones(seleccion())[1])
            self.app.avisar("Texto del email copiado.")

        def informado(_):
            sel = seleccion()
            if not sel:
                self.app.avisar("No hay pedidos seleccionados.", error=True)
                return

            def confirmar():
                ahora = dt.datetime.now(dt.timezone.utc)
                for d in sel:
                    try:
                        self.app.devs.actualizar(d["numero_venta"], {"informado_caro": True, "informado_en": ahora})
                    except FirebaseError as e:
                        self.app.manejar_error(e)
                        return
                self.app.avisar(f"{len(sel)} pedido(s) marcados como informados.")
                self.recargar()

            self.app.confirmar("Marcar como informados", f"¿Ya le envió a Carolina los {len(sel)} pedido(s)?",
                               confirmar, "Sí, marcar")

        self.panel_email.controls = [
            self._tabla(filas, ["", "Pedido", "Venta", "Producto"]),
            seccion("Vista previa"),
            ft.Text(f"Para: {para}" if para else "Para: (configure el email de Carolina en Ajustes)",
                    color=None if para else ft.Colors.ERROR),
            ft.Text(f"Asunto: {settings.EMAIL_CANCELACIONES_ASUNTO}", weight=ft.FontWeight.W_600),
            previa,
            ft.Row([ft.FilledButton("Abrir en Gmail", icon=ft.Icons.MAIL, on_click=gmail),
                    ft.OutlinedButton("Copiar texto", icon=ft.Icons.COPY, on_click=copiar),
                    ft.OutlinedButton("Marcar como informados", icon=ft.Icons.DONE_ALL, on_click=informado)],
                   wrap=True, spacing=12),
        ]
        previa.value = email_cancelaciones(pendientes)[1]

    # ------------------------------------------------------------ últimas cargadas

    def _pintar_recientes(self) -> None:
        if not self.cancelaciones:
            self.recientes.controls = [ft.Text("Todavía no hay cancelaciones cargadas.")]
            return
        filas = [ft.DataRow([
            ft.DataCell(ft.Text(d["numero_venta"], selectable=True)),
            ft.DataCell(ft.Text(d.get("pedido") or "—")),
            ft.DataCell(ft.Text(d.get("codigo_producto") or "—")),
            ft.DataCell(ft.Text("Sí" if d.get("lleva_nc") else "No")),
            ft.DataCell(ft.Text(("Hecho " + (d.get("remito_numero") or "")).strip() if d.get("remito_hecho")
                                else "Pendiente")),
            ft.DataCell(ft.Text("Sí" if d.get("informado_caro") else "No")),
            ft.DataCell(ft.Text(fecha_corta(d.get("cargado_en")))),
        ]) for d in self.cancelaciones[:100]]
        self.recientes.controls = [
            self._tabla(filas, ["Venta", "Pedido", "SKU", "Lleva NC", "Remito", "Informado", "Cargada"])]

"""Listado de devoluciones, detalle, pendientes y registro de resultados."""
from __future__ import annotations

import datetime as dt

import flet as ft

from ..local import abrir_url

from .. import local, settings
from ..datos import descripcion_clasificacion, guia_mercadolibre
from ..firebase import FirebaseError
from ..fotos import miniatura_b64
from .comun import chip_estado, fecha_corta, hoy_iso, seccion, tarjeta, titulo

ESTADOS_PENDIENTES = ("reclamado", "pendiente")


class VistaLista:
    def __init__(self, app, modo: str = "todas"):
        self.app = app
        self.page: ft.Page = app.page
        self.modo = modo
        self.filas: list[dict] = []
        self.contenedor = ft.Container(expand=True)
        self.buscar = ft.TextField(hint_text="Buscar por Venta #, ID Carrito, SKU o texto", prefix_icon=ft.Icons.SEARCH,
                                   width=340, dense=True, on_change=lambda _: self._pintar())
        opciones = [ft.dropdown.Option("todos", "Todos los estados")]
        opciones += [ft.dropdown.Option(k, v) for k, v in settings.ESTADOS.items()]
        self.filtro = ft.Dropdown(options=opciones, value="todos", width=230, dense=True,
                                  on_change=lambda _: self._pintar())
        self.filtro_pend = ft.Dropdown(
            value="todos", width=330, dense=True, on_change=lambda _: self._pintar(),
            options=[ft.dropdown.Option("todos", "Sin NC o esperando cobertura"),
                     ft.dropdown.Option("sin_nc", "Sin nota de crédito"),
                     ft.dropdown.Option("cobertura", "Esperando cobertura de ML")])
        self.solo_hoy = ft.Checkbox(label="Vencen hoy", value=False, on_change=lambda _: self._pintar())
        self.contador = ft.Text("", color=ft.Colors.ON_SURFACE_VARIANT)
        self.tabla = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(t)) for t in
                     ("Venta", "Vence", "Clasif.", "Reclamo", "%", "Estado", "NC", "Cargó", "Carga")],
            rows=[], heading_row_height=40, data_row_min_height=44, data_row_max_height=52,
            column_spacing=22, show_checkbox_column=False, expand=True)
        self.cargando = ft.ProgressBar(visible=False)

    # ------------------------------------------------------------ armado

    def control(self) -> ft.Control:
        self.contenedor.content = self._vista_listado()
        self.recargar()
        return self.contenedor

    def _vista_listado(self) -> ft.Control:
        if self.modo == "pendientes":
            encabezado = titulo("Pendientes", "Devoluciones sin nota de crédito (con o sin reclamo) y reclamos "
                                              "enviados que esperan la respuesta de Mercado Libre.")
        else:
            encabezado = titulo("Devoluciones", "Toque una fila para ver el detalle.")
        filtros: list[ft.Control] = [self.buscar]
        if self.modo != "pendientes":
            filtros += [self.filtro, self.solo_hoy]
        else:
            filtros += [self.filtro_pend]
        filtros += [ft.IconButton(ft.Icons.REFRESH, tooltip="Actualizar", on_click=lambda _: self.recargar()),
                    self.contador]
        if self.app.es_admin:
            # El botón va arriba a la derecha, junto al título, así no se sale de la pantalla
            from .sincronizar import sincronizar
            encabezado = ft.Row([encabezado,
                                 ft.FilledTonalButton("Sincronizar planilla", icon=ft.Icons.TABLE_CHART,
                                                      on_click=lambda _: sincronizar(self.app))],
                                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                vertical_alignment=ft.CrossAxisAlignment.START)
        return ft.Column([
            encabezado,
            ft.Row(filtros, spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True),
            self.cargando,
            tarjeta(ft.Column([ft.Row([self.tabla], scroll=ft.ScrollMode.AUTO)], scroll=ft.ScrollMode.AUTO,
                              expand=True), padding=8),
        ], spacing=14, expand=True)

    def recargar(self) -> None:
        self.cargando.visible = True
        self._actualizar()
        try:
            self.filas = self.app.devs.recientes(500)
        except FirebaseError as e:
            self.filas = []
            self.app.manejar_error(e)
        self.cargando.visible = False
        self._pintar()

    def _actualizar(self) -> None:
        try:
            self.page.update()
        except Exception:  # noqa: BLE001 - control aún no montado
            pass

    def _ventas_de_carrito(self, texto: str) -> set:
        """Si se buscó un ID Carrito (16 dígitos), los Venta # de ese carrito según el informe."""
        numero = "".join(ch for ch in texto if ch.isdigit())
        if len(numero) != 16:
            return set()
        try:
            r = self.app.indice.buscar(numero)
        except Exception:  # noqa: BLE001 - sin informe o sin conexión: se busca solo por texto
            return set()
        if r.tipo == "carrito":
            return {o[0] for o in (r.opciones or [])}
        return set()

    def _visibles(self) -> list[dict]:
        texto = (self.buscar.value or "").strip().lower()
        ventas_del_carrito = self._ventas_de_carrito(texto) if texto else set()
        hoy = hoy_iso()
        salida = []
        for d in self.filas:
            estado = d.get("estado")
            if self.modo == "pendientes":
                sin_nc = not d.get("nc_realizada")
                esperando = estado in ESTADOS_PENDIENTES
                que = self.filtro_pend.value or "todos"
                if (que == "sin_nc" and not sin_nc) or (que == "cobertura" and not esperando) \
                        or (que == "todos" and not (sin_nc or esperando)):
                    continue
            else:
                if self.filtro.value not in (None, "todos") and estado != self.filtro.value:
                    continue
                if self.solo_hoy.value and d.get("fecha_vencimiento") != hoy:
                    continue
            if texto:
                pajar = " ".join(str(d.get(k, "")) for k in
                                 ("numero_venta", "carrito", "codigo_producto", "producto", "pedido",
                                  "descripcion", "cargado_por")).lower()
                if texto not in pajar and d.get("numero_venta") not in ventas_del_carrito:
                    continue
            salida.append(d)
        return salida

    def _pintar(self) -> None:
        hoy = hoy_iso()
        filas = self._visibles()
        self.tabla.rows = []
        for d in filas:
            vence = d.get("fecha_vencimiento", "")
            color_vence = ft.Colors.ERROR if vence and vence <= hoy and d.get("estado") in (
                "cargada", "reclamo_armado") else None
            pct = d.get("porcentaje_sugerido")
            self.tabla.rows.append(ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(d.get("numero_venta", ""), weight=ft.FontWeight.W_600, selectable=True)),
                    ft.DataCell(ft.Text(fecha_corta(vence), color=color_vence)),
                    ft.DataCell(ft.Text(d.get("clasificacion", ""))),
                    ft.DataCell(ft.Icon(ft.Icons.CHECK_CIRCLE if d.get("reclamo") else ft.Icons.REMOVE_CIRCLE_OUTLINE,
                                        color=ft.Colors.GREEN_700 if d.get("reclamo") else ft.Colors.OUTLINE,
                                        size=18)),
                    ft.DataCell(ft.Text(f"{pct}%" if pct is not None else "—")),
                    ft.DataCell(chip_estado(d.get("estado", ""))),
                    ft.DataCell(ft.Icon(ft.Icons.RECEIPT_LONG, color=ft.Colors.GREEN_700, size=18,
                                        tooltip="NC realizada") if d.get("nc_realizada") else
                                ft.Text("Pendiente", size=12, color=ft.Colors.AMBER_800)),
                    ft.DataCell(ft.Text((d.get("cargado_por") or "").split("@")[0])),
                    ft.DataCell(ft.Text(fecha_corta(d.get("cargado_en")))),
                ],
                on_select_changed=lambda _, d=d: self.abrir_detalle(d),
            ))
        self.contador.value = f"{len(filas)} de {len(self.filas)}"
        if self.modo == "pendientes":
            por_enviar = sum(1 for d in self.filas if d.get("estado") == "reclamo_armado")
            if por_enviar:
                self.contador.value += f"  ·  {por_enviar} reclamo(s) armados que Alan todavía no envió"
        self._actualizar()

    # ------------------------------------------------------------ detalle

    def _puede_editar(self, d: dict) -> bool:
        return self.app.es_admin or d.get("estado") in settings.ESTADOS_EDITABLES_CARGA

    def _guia(self, d: dict, url_venta: str, mensaje: str, abrir_carpeta, cerrar) -> ft.Control | None:
        """Tarjeta "Qué hacer en Mercado Libre" con los pasos y los botones para hacerlo."""
        estado = d.get("estado")
        pendiente_reclamo = d.get("reclamo") and estado in ("cargada", "reclamo_armado")
        pendiente_revision = not d.get("reclamo") and estado == "sin_reclamo" and not d.get("ml_revisada")
        if not (pendiente_reclamo or pendiente_revision):
            return None
        g = guia_mercadolibre(d)
        filas: list[ft.Control] = [seccion("Qué hacer en Mercado Libre")]
        if g["tipo"] == "reclamo" and not mensaje:
            filas.append(ft.Text("Primero hay que armar el mensaje: toque \"Editar\" → \"Armar reclamo\".",
                                 color=ft.Colors.AMBER_800, weight=ft.FontWeight.W_600))
        if g["opcion"]:
            filas.append(ft.Container(ft.Text(f"Opción de reclamo: {g['opcion']}", weight=ft.FontWeight.W_700),
                                      padding=ft.padding.symmetric(6, 10), border_radius=8,
                                      bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY)))
        if g["nota"]:
            filas.append(ft.Text(g["nota"], size=12, color=ft.Colors.AMBER_800))
        filas += [ft.Text(f"{i}. {p}", size=13) for i, p in enumerate(g["pasos"], 1)]
        pct = d.get("porcentaje_sugerido")
        botones: list[ft.Control] = [
            ft.OutlinedButton("Ver venta en ML", icon=ft.Icons.OPEN_IN_NEW,
                              on_click=lambda _: abrir_url(page=self.page, url=url_venta))]
        if g["tipo"] == "reclamo":
            botones += [
                ft.OutlinedButton("Copiar mensaje", icon=ft.Icons.COPY, disabled=not mensaje,
                                  on_click=lambda _: (self.page.set_clipboard(mensaje),
                                                      self.app.avisar("Mensaje copiado. Péguelo en ML con Ctrl+V."))),
                ft.OutlinedButton("Abrir fotos", icon=ft.Icons.FOLDER_OPEN, on_click=abrir_carpeta),
                ft.FilledButton("Marcar reclamo enviado", icon=ft.Icons.SEND, disabled=not mensaje,
                                on_click=lambda _: (cerrar(), self._reclamo_enviado(d))),
            ]
            if pct is not None:
                filas.insert(1, ft.Text(f"Porcentaje a pedir: {pct}% del precio de venta",
                                        weight=ft.FontWeight.W_600))
        else:
            botones.append(ft.FilledButton("Marcar revisada en ML", icon=ft.Icons.TASK_ALT,
                                           on_click=lambda _: (cerrar(), self._marcar_revisada(d))))
        filas.append(ft.Row(botones, wrap=True, spacing=10, run_spacing=8))
        return ft.Container(ft.Column(filas, spacing=8), padding=16, border_radius=12,
                            bgcolor=ft.Colors.with_opacity(0.06, ft.Colors.PRIMARY),
                            border=ft.border.all(1, ft.Colors.with_opacity(0.35, ft.Colors.PRIMARY)))

    def abrir_detalle(self, d: dict, desde_carga: bool = False) -> None:
        if not (d.get("producto") and d.get("deposito_origen")):
            # Cargada antes de importar el informe: se muestran los datos del informe igual
            try:
                v = self.app.indice.buscar(d.get("numero_venta", "")).venta
            except FirebaseError:
                v = None
            if v:
                d = dict(d)
                d.update({"producto": v.producto, "pedido": v.pedido, "carrito": v.carrito,
                          "fecha_venta": v.fecha.isoformat() if v.fecha else ""})
                if not d.get("deposito_origen") and v.deposito:
                    d["deposito_origen"] = v.deposito
                d.setdefault("codigo_producto", v.codigo)
                if not d.get("codigo_producto"):
                    d["codigo_producto"] = v.codigo
        galeria = ft.Row([ft.ProgressRing(width=24, height=24)], wrap=True, spacing=8, run_spacing=8)
        fotos: list[bytes] = []

        def dato(etiqueta: str, valor) -> ft.Control:
            return ft.Column([ft.Text(etiqueta, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                              ft.Text(str(valor) if valor not in (None, "") else "—", selectable=True)], spacing=1)

        mensaje = d.get("mensaje_reclamo") or ""
        cuerpo: list[ft.Control] = [
            ft.Row([chip_estado(d.get("estado", "")),
                    ft.Text(f"Cargó {d.get('cargado_por', '')} el {fecha_corta(d.get('cargado_en'))}",
                            size=12, color=ft.Colors.ON_SURFACE_VARIANT)], spacing=12),
            ft.Row([dato("Vence", fecha_corta(d.get("fecha_vencimiento"))),
                    dato("Clasificación", descripcion_clasificacion(d.get("clasificacion", ""))),
                    dato("Código", d.get("codigo_producto")),
                    dato("% sugerido", f"{d['porcentaje_sugerido']}%" if d.get("porcentaje_sugerido") is not None
                         else None)], spacing=30, wrap=True),
            ft.Row([dato("Condición", d.get("condicion")), dato("Motivo", d.get("motivo")),
                    self._deposito(d) if self.app.es_admin else dato("Depósito de origen", d.get("deposito_origen")),
                    dato("N° de mediación", d.get("numero_mediacion")),
                    dato("Nota de crédito", "Realizada" if d.get("nc_realizada") else "Pendiente"),
                    dato("Costo de envío", f"$ {d['costo_envio']:,.2f}".replace(",", "X").replace(".", ",")
                         .replace("X", ".") if d.get("costo_envio") is not None else None)],
                   spacing=30, wrap=True),
            ft.Row([dato("Producto", d.get("producto")), dato("Pedido", d.get("pedido")),
                    dato("Fecha de venta", fecha_corta(d.get("fecha_venta")) if d.get("fecha_venta") else None),
                    dato("ID Carrito", d.get("carrito"))], spacing=30, wrap=True),
            dato("Problema informado por el comprador", d.get("problema_comprador")),
            dato("Estado en que llegó", d.get("descripcion")),
        ]
        url_venta = settings.link_venta(d.get("numero_venta", ""), d.get("carrito", ""))
        enlaces: list[ft.Control] = [ft.TextButton("Ver venta en Mercado Libre", icon=ft.Icons.OPEN_IN_NEW,
                                                   on_click=lambda _: abrir_url(page=self.page, url=url_venta))]
        if d.get("link_publicacion"):
            enlaces.append(ft.TextButton("Abrir publicación", icon=ft.Icons.OPEN_IN_NEW,
                                         on_click=lambda _: abrir_url(page=self.page, url=d["link_publicacion"])))
        cuerpo.append(ft.Row(enlaces, wrap=True))
        if d.get("reclamo"):
            cuerpo.append(tarjeta(ft.Column([
                ft.Row([seccion("Mensaje de reclamo"),
                        ft.Text(f"{len(mensaje)}/{settings.LIMITE_MENSAJE}", size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT)],
                       alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Text(mensaje or "Todavía no se armó el mensaje.", selectable=True),
                ft.Row([ft.TextButton("Copiar mensaje", icon=ft.Icons.COPY, disabled=not mensaje,
                                      on_click=lambda _: (self.page.set_clipboard(mensaje),
                                                          self.app.avisar("Mensaje copiado.")))]),
            ], spacing=6), padding=14))
        if d.get("estado") in ("cobertura", "sin_cobertura"):
            cuerpo.append(ft.Row([dato("Monto reintegrado", d.get("monto_reintegrado")),
                                  dato("N° de movimiento", d.get("numero_movimiento")),
                                  dato("Resultado registrado", fecha_corta(d.get("resultado_en")))], spacing=30))
        cuerpo += [seccion(f"Fotos ({d.get('fotos', 0)})"), galeria]

        dlg = ft.AlertDialog(
            title=ft.Text(f"Venta {d.get('numero_venta')}"),
            content=ft.Container(ft.Column(cuerpo, spacing=14, scroll=ft.ScrollMode.AUTO, tight=True),
                                 width=760),
        )

        def cerrar(_=None):
            self.page.close(dlg)

        def abrir_carpeta(_):
            if fotos:
                local.abrir_carpeta(local.guardar_fotos(d["numero_venta"], fotos))

        def editar(_):
            cerrar()
            from .carga import VistaCarga

            def volver():
                self.contenedor.content = self._vista_listado()
                self.recargar()

            self.contenedor.content = VistaCarga(self.app, existente=d, al_terminar=volver).control()
            self._actualizar()

        acciones: list[ft.Control] = [ft.TextButton("Abrir fotos en carpeta", icon=ft.Icons.FOLDER_OPEN,
                                                    on_click=abrir_carpeta)]
        guia = self._guia(d, url_venta, mensaje, abrir_carpeta, cerrar)
        if guia:
            dlg.content.content.controls.insert(1, guia)
        if self.app.es_admin:
            # Acciones del día a día arriba del detalle, a mano y sin tener que bajar
            botones: list[ft.Control] = []
            if not d.get("nc_realizada"):
                botones.append(ft.FilledTonalButton("Marcar NC realizada", icon=ft.Icons.RECEIPT_LONG,
                                                    on_click=lambda _: (cerrar(), self._marcar_nc(d))))
            if d.get("estado") in ("reclamado", "pendiente", "reclamo_armado"):
                botones.append(ft.FilledTonalButton("Registrar resultado", icon=ft.Icons.FACT_CHECK,
                                                    on_click=lambda _: (cerrar(), self.registrar_resultado(d))))
            botones.append(ft.OutlinedButton("Costo de envío", icon=ft.Icons.LOCAL_SHIPPING,
                                             on_click=lambda _: (cerrar(), self._costo_envio(d))))
            if botones:
                dlg.content.content.controls.insert(1, ft.Row(botones, wrap=True, spacing=10, run_spacing=8))
            acciones.append(ft.TextButton("Borrar", icon=ft.Icons.DELETE_OUTLINE,
                                          style=ft.ButtonStyle(color=ft.Colors.ERROR),
                                          on_click=lambda _: (cerrar(), self._borrar(d))))
        if self._puede_editar(d) and not desde_carga:
            acciones.append(ft.OutlinedButton("Editar", icon=ft.Icons.EDIT, on_click=editar))
        acciones.append(ft.FilledButton("Cerrar", on_click=cerrar))
        dlg.actions = acciones
        dlg.actions_alignment = ft.MainAxisAlignment.END
        self.page.open(dlg)

        try:
            fotos.extend(self.app.devs.fotos(d["numero_venta"]))
            galeria.controls = [ft.Image(src_base64=miniatura_b64(f, 400), width=170, height=170,
                                         fit=ft.ImageFit.COVER, border_radius=ft.border_radius.all(10))
                                for f in fotos] or [ft.Text("Sin fotos")]
        except FirebaseError as e:
            galeria.controls = [ft.Text(f"No se pudieron cargar las fotos: {e}", color=ft.Colors.ERROR)]
        self._actualizar()

    # ------------------------------------------------------------ acciones de administrador

    def _deposito(self, d: dict) -> ft.Control:
        def cambio(e):
            try:
                self.app.devs.actualizar(d["numero_venta"], {"deposito_origen": e.control.value})
                d["deposito_origen"] = e.control.value
                self.app.avisar(f"Depósito de origen: {e.control.value}.")
            except FirebaseError as err:
                self.app.manejar_error(err)

        return ft.Dropdown(label="Depósito de origen", value=d.get("deposito_origen"), width=200, dense=True,
                           options=[ft.dropdown.Option(x) for x in settings.DEPOSITOS_ORIGEN], on_change=cambio)

    def _marcar_revisada(self, d: dict) -> None:
        try:
            self.app.devs.actualizar(d["numero_venta"], {"ml_revisada": True,
                                                         "ml_revisada_en": dt.datetime.now(dt.timezone.utc),
                                                         "ml_revisada_por": self.app.usuario.get("email", "")})
            self.app.avisar(f"Venta {d['numero_venta']}: revisada en ML.")
        except FirebaseError as e:
            self.app.manejar_error(e)
        self._reabrir(d)

    def _reabrir(self, d: dict, recargar: bool = True) -> None:
        """Vuelve a abrir el detalle (con los datos actualizados) después de una acción."""
        if recargar:
            self.recargar()
            d = next((x for x in self.filas if x.get("numero_venta") == d.get("numero_venta")), d)
        self.abrir_detalle(d)

    def _costo_envio(self, d: dict) -> None:
        actual = d.get("costo_envio")
        campo = ft.TextField(label="Costo de envío", prefix_text="$ ", autofocus=True, width=260,
                             value="" if actual is None else f"{actual:.2f}".replace(".", ","),
                             input_filter=ft.InputFilter(r"[0-9.,]"),
                             helper_text="Ponga 0 si no tuvo costo de envío.")
        error = ft.Text("", color=ft.Colors.ERROR, visible=False)
        dlg = ft.AlertDialog(modal=True, title=ft.Text(f"Costo de envío — {d['numero_venta']}"),
                             content=ft.Container(ft.Column([campo, error], tight=True), width=420))

        def guardar(_=None):
            texto = (campo.value or "").replace(".", "").replace(",", ".").strip()
            try:
                valor = float(texto)
            except ValueError:
                error.value, error.visible = "Ingrese un importe.", True
                self.page.update()
                return
            self.page.close(dlg)
            try:
                self.app.devs.actualizar(d["numero_venta"], {"costo_envio": valor})
                self.app.avisar("Costo de envío guardado. Se escribe en la planilla al sincronizar.")
            except FirebaseError as e:
                self.app.manejar_error(e)
            self._reabrir(d)

        campo.on_submit = guardar
        dlg.actions = [ft.TextButton("Cancelar", on_click=lambda _: (self.page.close(dlg),
                                                                    self._reabrir(d, recargar=False))),
                       ft.FilledButton("Guardar", on_click=guardar)]
        self.page.open(dlg)

    def _marcar_nc(self, d: dict) -> None:
        clasif = d.get("clasificacion")
        if not clasif:
            self.app.avisar("La venta no tiene clasificación. Edítela antes de marcar la NC.", error=True)
            self._reabrir(d, recargar=False)
            return
        transferencia = settings.transferencia_al_hacer_nc(clasif)
        final = settings.DEPOSITO_FINAL.get(clasif, "Service Podesta")
        try:
            self.app.devs.actualizar(d["numero_venta"], {"nc_realizada": True, "transferencia": transferencia,
                                                         "deposito_final": final})
            self.app.avisar(f"Venta {d['numero_venta']}: NC realizada. En la planilla quedará "
                            f"Transferencia \"{transferencia}\" y depósito final \"{final}\" al sincronizar.")
        except FirebaseError as e:
            self.app.manejar_error(e)
        self._reabrir(d)

    def _reclamo_enviado(self, d: dict) -> None:
        mediacion = ft.TextField(label="N° de mediación / reclamo en ML (opcional)", autofocus=True,
                                 input_filter=ft.NumbersOnlyInputFilter())
        dlg = ft.AlertDialog(modal=True, title=ft.Text(f"Reclamo enviado — {d['numero_venta']}"),
                             content=ft.Container(mediacion, width=420))

        def guardar(_):
            self.page.close(dlg)
            campos = {"estado": "reclamado", "reclamado_en": dt.datetime.now(dt.timezone.utc),
                      "reclamado_por": self.app.usuario.get("email", "")}
            if (mediacion.value or "").strip():
                campos["numero_mediacion"] = mediacion.value.strip()
            try:
                self.app.devs.actualizar(d["numero_venta"], campos)
                self.app.avisar(f"Venta {d['numero_venta']}: reclamo enviado.")
            except FirebaseError as e:
                self.app.manejar_error(e)
            self._reabrir(d)

        dlg.actions = [ft.TextButton("Cancelar", on_click=lambda _: (self.page.close(dlg),
                                                                    self._reabrir(d, recargar=False))),
                       ft.FilledButton("Guardar", on_click=guardar)]
        self.page.open(dlg)

    def registrar_resultado(self, d: dict) -> None:
        resultado = ft.RadioGroup(content=ft.Row([
            ft.Radio(value="cobertura", label="Hubo cobertura"),
            ft.Radio(value="sin_cobertura", label="No hubo cobertura"),
        ]), value="cobertura")
        monto = ft.TextField(label="Monto reintegrado", prefix_text="$ ", width=220,
                             input_filter=ft.InputFilter(r"[0-9.,]"))
        movimiento = ft.TextField(label="N° de movimiento / ID de Devolución por Compra Protegida", expand=True)
        error = ft.Text("", color=ft.Colors.ERROR, visible=False)

        def cambio(_):
            hay = resultado.value == "cobertura"
            monto.disabled = movimiento.disabled = not hay
            self.page.update()

        resultado.on_change = cambio
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Resultado del reclamo — {d['numero_venta']}"),
            content=ft.Container(ft.Column([resultado, ft.Row([monto, movimiento]), error], tight=True,
                                           spacing=14), width=640),
        )

        def guardar(_):
            campos: dict = {"estado": resultado.value, "resultado_en": dt.datetime.now(dt.timezone.utc),
                            "resultado_por": self.app.usuario.get("email", "")}
            if resultado.value == "cobertura":
                texto = (monto.value or "").replace(",", ".")
                try:
                    campos["monto_reintegrado"] = float(texto)
                except ValueError:
                    error.value, error.visible = "Ingrese el monto reintegrado.", True
                    self.page.update()
                    return
                campos["numero_movimiento"] = (movimiento.value or "").strip()
            else:
                campos["monto_reintegrado"] = 0.0
                campos["numero_movimiento"] = ""
            try:
                self.app.devs.actualizar(d["numero_venta"], campos)
            except FirebaseError as e:
                self.app.manejar_error(e)
                return
            self.page.close(dlg)
            self.app.avisar("Resultado registrado.")
            self._reabrir(d)

        dlg.actions = [ft.TextButton("Cancelar", on_click=lambda _: (self.page.close(dlg),
                                                                    self._reabrir(d, recargar=False))),
                       ft.FilledButton("Guardar resultado", icon=ft.Icons.SAVE, on_click=guardar)]
        self.page.open(dlg)

    def _borrar(self, d: dict) -> None:
        def hacer():
            try:
                self.app.devs.borrar(d["numero_venta"], int(d.get("fotos", 0)))
                self.app.avisar(f"Venta {d['numero_venta']} borrada.")
            except FirebaseError as e:
                self.app.manejar_error(e)
            self.recargar()

        self.app.confirmar("Borrar devolución",
                           f"¿Seguro que desea borrar la venta {d['numero_venta']} y sus fotos? No se puede deshacer.",
                           hacer, "Borrar")

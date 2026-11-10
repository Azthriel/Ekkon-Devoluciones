"""Reparaciones del service: listado, carga/edición, importación y sincronización con la planilla."""
from __future__ import annotations

import datetime as dt

import flet as ft

from .. import reparaciones as R
from .. import settings
from ..datos import importe
from ..firebase import FirebaseError
from ..sheets import Planilla, SheetsError, id_de_link
from .comun import fecha_corta, seccion, tarjeta, titulo

COLOR_ESTADO_REP = {
    "Para revisar": ft.Colors.BLUE_GREY, "Revisada": ft.Colors.BLUE, "Esperando repuesto": ft.Colors.ORANGE_800,
    "Esperando cotización": ft.Colors.ORANGE_800, "Presupuesto abonado": ft.Colors.TEAL,
    "Para reparar": ft.Colors.INDIGO, "Reparada": ft.Colors.GREEN_700, "Enviado a GP": ft.Colors.PURPLE_700,
    "Finalizado": ft.Colors.GREEN_900, "Extraviado": ft.Colors.RED_700,
}


def chips_estado(estados: list[str]) -> ft.Control:
    return ft.Row([ft.Container(ft.Text(e, size=11, weight=ft.FontWeight.W_600,
                                        color=COLOR_ESTADO_REP.get(e, ft.Colors.GREY)),
                                padding=ft.padding.symmetric(2, 8), border_radius=12,
                                bgcolor=ft.Colors.with_opacity(0.12, COLOR_ESTADO_REP.get(e, ft.Colors.GREY)))
                   for e in estados or []] or [ft.Text("—")], spacing=4, wrap=True)


def abrir_planilla_rep(app) -> Planilla:
    return Planilla(id_de_link(app.config.get("planilla_reparaciones_url", "")), hoja="")


class VistaReparaciones:
    def __init__(self, app):
        self.app = app
        self.page: ft.Page = app.page
        self.filas: list[dict] = []
        self.buscar = ft.TextField(hint_text="Buscar por OS, Venta #, SKU o producto", prefix_icon=ft.Icons.SEARCH,
                                   width=360, dense=True, on_change=lambda _: self._pintar())
        self.filtro = ft.Dropdown(value="abiertas", width=230, dense=True, on_change=lambda _: self._pintar(),
                                  options=[ft.dropdown.Option("abiertas", "Sin terminar"),
                                           ft.dropdown.Option("todas", "Todas")] +
                                  [ft.dropdown.Option(e, e) for e in settings.REP_ESTADOS])
        self.contador = ft.Text("", color=ft.Colors.ON_SURFACE_VARIANT)
        self.tabla = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(t)) for t in
                     ("N° Venta/OS", "Producto", "Estado", "Causa", "Reparado", "Estado final", "Revisión",
                      "Reparación")],
            rows=[], heading_row_height=40, data_row_min_height=44, data_row_max_height=56, column_spacing=20)

    # ------------------------------------------------------------ listado

    def control(self) -> ft.Control:
        acciones: list[ft.Control] = [ft.FilledButton("Nueva reparación", icon=ft.Icons.BUILD,
                                                      on_click=lambda _: self.editar(None))]
        if self.app.es_admin:
            acciones += [ft.FilledTonalButton("Sincronizar planilla", icon=ft.Icons.TABLE_CHART,
                                              on_click=lambda _: self.sincronizar()),
                         ft.TextButton("Importar de la planilla", icon=ft.Icons.DOWNLOAD,
                                       on_click=lambda _: self.importar())]
        vista = ft.Column([
            ft.Row([titulo("Reparaciones", "Toque una fila para actualizarla."), ft.Row(acciones, spacing=10)],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.START),
            ft.Row([self.buscar, self.filtro,
                    ft.IconButton(ft.Icons.REFRESH, tooltip="Actualizar", on_click=lambda _: self.recargar()),
                    self.contador], spacing=12, scroll=ft.ScrollMode.AUTO),
            tarjeta(ft.Column([ft.Row([self.tabla], scroll=ft.ScrollMode.AUTO)], scroll=ft.ScrollMode.ALWAYS,
                              expand=True), padding=8, expand=True),
        ], spacing=14, expand=True)
        self.recargar(actualizar=False)
        return vista

    def _update(self):
        try:
            self.page.update()
        except Exception:  # noqa: BLE001
            pass

    def recargar(self, actualizar: bool = True) -> None:
        try:
            self.filas = sorted(self.app.reparaciones.listar(),
                                key=lambda r: (r.get("fecha_revision") or "", r.get("numero") or ""), reverse=True)
        except FirebaseError as e:
            self.filas = []
            self.app.manejar_error(e)
        self._pintar(actualizar)

    def _visibles(self) -> list[dict]:
        texto = (self.buscar.value or "").strip().lower()
        filtro = self.filtro.value or "abiertas"
        salida = []
        for r in self.filas:
            if filtro == "abiertas" and R.finalizada(r):
                continue
            if filtro not in ("abiertas", "todas") and filtro not in (r.get("estados") or []):
                continue
            if texto:
                pajar = " ".join(str(r.get(k, "")) for k in ("numero", "sku", "producto", "notas")).lower()
                if texto not in pajar and R.clave(texto) != R.clave(r.get("numero")):
                    continue
            salida.append(r)
        return salida

    def _pintar(self, actualizar: bool = True) -> None:
        filas = self._visibles()
        self.tabla.rows = [ft.DataRow(
            cells=[
                ft.DataCell(ft.Text(r.get("numero", ""), weight=ft.FontWeight.W_600, selectable=True)),
                ft.DataCell(ft.Text(r.get("producto") or "—", width=300, max_lines=2,
                                    overflow=ft.TextOverflow.ELLIPSIS, size=13)),
                ft.DataCell(chips_estado(r.get("estados"))),
                ft.DataCell(ft.Text(r.get("causa") or "—")),
                ft.DataCell(ft.Text(r.get("reparado") or "—")),
                ft.DataCell(ft.Text(r.get("estado_final") or "—")),
                ft.DataCell(ft.Text(fecha_corta(r.get("fecha_revision")) if r.get("fecha_revision") else "—")),
                ft.DataCell(ft.Text(fecha_corta(r.get("fecha_reparacion")) if r.get("fecha_reparacion") else "—")),
            ],
            on_select_changed=lambda _, r=r: self.editar(r)) for r in filas]
        self.contador.value = f"{len(filas)} de {len(self.filas)}"
        if actualizar:
            self._update()

    # ------------------------------------------------------------ carga / edición

    def editar(self, r: dict | None) -> None:
        nueva = r is None
        r = dict(r or {})
        numero = ft.TextField(label="N° de OS o Venta #", value=r.get("numero", ""), autofocus=nueva,
                              read_only=not nueva, width=260, prefix_icon=ft.Icons.TAG)
        info = ft.Text("", size=13, selectable=True)
        producto = ft.TextField(label="Producto", value=r.get("producto", ""), expand=True)
        sku = ft.TextField(label="SKU", value=r.get("sku", ""), width=160)
        seleccion = set(r.get("estados") or ([] if not nueva else ["Para revisar"]))
        chips = ft.Row(wrap=True, spacing=6, run_spacing=6)

        def pintar_chips():
            chips.controls = [ft.Chip(label=ft.Text(e), selected=e in seleccion, show_checkmark=True,
                                      on_select=lambda ev, e=e: marcar(e, ev.control.selected))
                              for e in settings.REP_ESTADOS]

        def marcar(e, valor):
            (seleccion.add if valor else seleccion.discard)(e)

        pintar_chips()

        def lista(label, opciones, valor, ancho=220):
            return ft.Dropdown(label=label, value=valor or None, width=ancho,
                               options=[ft.dropdown.Option(o) for o in opciones])

        causa = lista("Causa", settings.REP_CAUSAS, r.get("causa"))
        a_realizar = ft.TextField(label="Reparación a realizar", value=r.get("a_realizar", ""), multiline=True,
                                  min_lines=1, max_lines=3)
        hecho = ft.TextField(label="Qué se hizo", value=r.get("que_se_hizo", ""), multiline=True, min_lines=2,
                             max_lines=4)
        reparado = lista("¿Reparado?", ["Si", "No"], r.get("reparado"), 190)
        repuesto = lista("¿Se requirió repuesto?", ["Si", "No"], r.get("repuesto"), 250)
        origen = lista("¿De dónde se obtuvo?", settings.REP_ORIGEN_REPUESTO, r.get("origen_repuesto"), 250)
        final = lista("Estado final", settings.REP_ESTADO_FINAL, r.get("estado_final"))
        horas = ft.TextField(label="Horas aprox.", value="" if r.get("horas") in (None, "") else
                             str(r["horas"]).replace(".", ","), width=170)
        notas = ft.TextField(label="Notas adicionales", value=r.get("notas", ""), multiline=True, min_lines=1,
                             max_lines=3)
        error = ft.Text("", color=ft.Colors.ERROR, visible=False)

        def buscar(_=None):
            k = R.clave(numero.value)
            info.value, info.color = "", None
            if not k:
                self._update()
                return
            prod, cod, extra = "", "", ""
            try:
                if R.es_venta(k):
                    res = self.app.indice.buscar(k)
                    if res.venta:
                        prod, cod = res.venta.producto, res.venta.codigo
                        dev = self.app.devs.obtener(res.venta.venta)
                        extra = (f"Vinculada a la devolución {res.venta.venta} (clasificación "
                                 f"{dev.get('clasificacion', '—')}). Al terminar, se agrega la nota en la planilla."
                                 if dev else "Venta sin devolución cargada en la app.")
                        if res.venta.venta != k:
                            numero.value = res.venta.venta
                else:
                    o = self.app.indice_os.buscar(k)
                    if o:
                        prod, cod = o.get("producto", ""), o.get("sku", "")
                        partes = [f"OS {o.get('os')} · {o.get('tipo') or ''} · ingresó {fecha_corta(o.get('fecha'))}"]
                        if o.get("cliente"):
                            partes.append(f"Cliente: {o['cliente'].strip()}")
                        if o.get("informe"):
                            partes.append(f"Informe técnico: {o['informe'].strip()}")
                        extra = "\n".join(partes)
            except FirebaseError:
                pass
            if prod:
                if not (producto.value or "").strip() or producto.value.startswith(cod or "\0"):
                    producto.value = prod
                if not (sku.value or "").strip():
                    sku.value = cod
                info.value, info.color = extra or prod, ft.Colors.GREEN_800
            else:
                info.value = "No figura en los informes de OS ni de ventas. Complete el producto a mano."
                info.color = ft.Colors.AMBER_800
            self._update()

        numero.on_blur = buscar
        numero.on_submit = buscar

        dlg = ft.AlertDialog(modal=True, title=ft.Text("Nueva reparación" if nueva else f"Reparación {r.get('numero')}"))

        def guardar(_):
            k = R.clave(numero.value)
            if not k:
                error.value, error.visible = "Ingrese el N° de OS o el Venta #.", True
                self._update()
                return
            if nueva:
                try:
                    if self.app.reparaciones.obtener(k):
                        error.value, error.visible = "Esa OS / venta ya tiene una reparación cargada.", True
                        self._update()
                        return
                except FirebaseError:
                    pass
            datos = dict(r)
            datos.update({
                "numero": k if R.es_venta(k) else (numero.value or "").strip().lstrip("0") or k,
                "producto": (producto.value or "").strip(), "sku": (sku.value or "").strip(),
                "estados": [e for e in settings.REP_ESTADOS if e in seleccion],
                "causa": causa.value or "", "a_realizar": (a_realizar.value or "").strip(),
                "que_se_hizo": (hecho.value or "").strip(), "reparado": reparado.value or "",
                "repuesto": repuesto.value or "", "origen_repuesto": origen.value or "",
                "estado_final": final.value or "", "notas": (notas.value or "").strip(),
                "horas": importe(horas.value) if (horas.value or "").strip() else None,
            })
            datos = R.completar_fechas(datos)
            try:
                self.app.reparaciones.guardar(datos, self.app.usuario, nueva)
            except FirebaseError as e:
                self.app.manejar_error(e)
                return
            self.page.close(dlg)
            self.app.avisar("Reparación guardada." + (" Quedó terminada." if R.finalizada(datos) else ""))
            self.recargar()

        fechas = ft.Text(f"Revisión: {fecha_corta(r.get('fecha_revision')) if r.get('fecha_revision') else 'hoy'}"
                         f"   ·   Reparación: {fecha_corta(r.get('fecha_reparacion')) if r.get('fecha_reparacion') else 'se pone sola al marcarla reparada'}",
                         size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        dlg.content = ft.Container(ft.Column([
            ft.Row([numero, ft.OutlinedButton("Buscar producto", icon=ft.Icons.SEARCH, on_click=buscar)]),
            info,
            ft.Row([producto, sku], spacing=12),
            seccion("Estado actual (puede elegir varios)"), chips,
            ft.Row([causa, reparado, repuesto], spacing=12, wrap=True),
            a_realizar, hecho,
            ft.Row([origen, final, horas], spacing=12, wrap=True),
            notas, fechas, error,
        ], spacing=12, scroll=ft.ScrollMode.AUTO, tight=True), width=820, height=620)
        dlg.actions = [ft.TextButton("Cancelar", on_click=lambda _: self.page.close(dlg)),
                       ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar)]
        if not nueva and self.app.es_admin:
            dlg.actions.insert(0, ft.TextButton("Borrar", icon=ft.Icons.DELETE_OUTLINE,
                                                style=ft.ButtonStyle(color=ft.Colors.ERROR),
                                                on_click=lambda _: self._borrar(r, dlg)))
        self.page.open(dlg)
        if not nueva:
            buscar()   # muestra los datos de la OS (cliente, informe técnico) y completa el producto si falta

    def _borrar(self, r: dict, dlg) -> None:
        self.page.close(dlg)

        def hacer():
            try:
                self.app.reparaciones.borrar(r["numero"])
                self.app.avisar("Reparación borrada de la app (la fila de la planilla no se toca).")
            except FirebaseError as e:
                self.app.manejar_error(e)
            self.recargar()

        self.app.confirmar("Borrar reparación", f"¿Borrar la reparación {r.get('numero')}?", hacer, "Borrar")

    # ------------------------------------------------------------ planilla

    def _leer_planilla(self):
        planilla = abrir_planilla_rep(self.app)
        return planilla, planilla.leer(R.leer_hoja)

    def importar(self) -> None:
        try:
            _planilla, hoja = self._leer_planilla()
            existentes = {x["_id"] for x in self.app.reparaciones.listar()}
            os_idx = self.app.indice_os.todas()
        except (SheetsError, ValueError, FirebaseError) as e:
            self.app.avisar(str(e), error=True)
            return
        nuevas = R.desde_hoja(hoja, existentes, os_idx, lambda n: self.app.indice.buscar(n).venta)
        if not nuevas:
            self.app.avisar("No hay reparaciones nuevas en la planilla para importar.")
            return
        sin_producto = [r["numero"] for r in nuevas if not r.get("producto")]

        def hacer():
            for r in nuevas:
                try:
                    self.app.reparaciones.guardar(r, self.app.usuario, True)
                except FirebaseError as e:
                    self.app.manejar_error(e)
                    return
            self.app.avisar(f"Se importaron {len(nuevas)} reparación(es). Toque \"Sincronizar planilla\" para "
                            "completar producto y SKU en la planilla.")
            self.recargar()

        aviso = f" Sin producto en los informes: {', '.join(sin_producto)}." if sin_producto else ""
        self.app.confirmar("Importar reparaciones",
                           f"Se van a importar {len(nuevas)} reparación(es) de la planilla, completando producto y "
                           f"SKU desde los informes.{aviso}", hacer, "Importar")

    def sincronizar(self) -> None:
        try:
            planilla, hoja = self._leer_planilla()
            reps = self.app.reparaciones.listar()
            plan = R.planificar(hoja, reps)
        except (SheetsError, ValueError, FirebaseError) as e:
            self.app.avisar(str(e), error=True)
            return
        if plan.vacio:
            self.app.avisar("La planilla de reparaciones ya está al día.")
            return
        extra = (" No encontré estas columnas: " + ", ".join(sorted(plan.sin_columna)) + ".") if plan.sin_columna else ""

        def hacer():
            try:
                planilla.aplicar(plan, hoja)
            except SheetsError as e:
                self.app.avisar(str(e), error=True)
                return
            hoy = dt.date.today().isoformat()
            for r in reps:
                if not r.get("planilla_en"):
                    try:
                        self.app.reparaciones.guardar({**r, "planilla_en": hoy}, self.app.usuario, False)
                    except FirebaseError:
                        pass
            self.app.avisar(f"Planilla de reparaciones actualizada: {len(plan.filas_nuevas)} fila(s) nueva(s) y "
                            f"{len(plan.celdas)} celda(s) actualizada(s).")

        self.app.confirmar("Sincronizar planilla de reparaciones",
                           f"Se agregan {len(plan.filas_nuevas)} fila(s) y se actualizan {len(plan.celdas)} celda(s) "
                           f"en {len(plan.actualizadas)} reparación(es). Lo cargado en la app reemplaza lo que haya "
                           f"en esas celdas.{extra}", hacer, "Escribir en la planilla")

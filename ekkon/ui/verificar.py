"""Verificar reparaciones: Alan prueba los equipos que el service marcó como reparados."""
from __future__ import annotations

import flet as ft

from .. import reparaciones as R
from ..firebase import FirebaseError
from . import comun
from .comun import fecha_corta, seccion, tarjeta_lista, titulo

COLOR_VERIF = {"Funciona": ft.Colors.GREEN_700, "No funciona": ft.Colors.RED_700}


def chip_verificacion(r: dict) -> ft.Control:
    v = r.get("verificado") or ("Para verificar" if R.reparada(r) else "")
    if not v:
        return ft.Text("—")
    color = COLOR_VERIF.get(v, ft.Colors.AMBER_800)
    return ft.Container(ft.Text(v, size=11, weight=ft.FontWeight.W_600, color=color),
                        padding=ft.padding.symmetric(2, 8), border_radius=12,
                        bgcolor=ft.Colors.with_opacity(0.12, color))


class VistaVerificar:
    def __init__(self, app):
        self.app = app
        self.filas: list[dict] = []
        self.filtro = ft.Dropdown(value="pendientes", width=230, dense=True, on_change=lambda _: self._pintar(),
                                  options=[ft.dropdown.Option("pendientes", "Para verificar"),
                                           ft.dropdown.Option("No funciona", "No funciona"),
                                           ft.dropdown.Option("Funciona", "Funciona"),
                                           ft.dropdown.Option("todas", "Todas las reparadas")])
        self.buscar = ft.TextField(hint_text="Buscar OS, venta, SKU…", prefix_icon=ft.Icons.SEARCH, width=320,
                                   dense=True, on_change=lambda _: self._pintar())
        self.contador = ft.Text("", color=ft.Colors.ON_SURFACE_VARIANT)
        self.lista = ft.ListView(spacing=8, expand=True)
        if comun.MOVIL:
            self.buscar.width = self.filtro.width = None
            self.buscar.expand = self.filtro.expand = True

    def control(self) -> ft.Control:
        cabeza: list[ft.Control] = []
        if not comun.MOVIL:
            cabeza.append(titulo("Verificar reparaciones",
                                 "Equipos que el service marcó como reparados. Pruébelos e indique si funcionan."))
        vista = ft.Column(cabeza + [
            ft.Row([self.buscar, ft.IconButton(ft.Icons.REFRESH, tooltip="Actualizar",
                                               on_click=lambda _: self.recargar())], wrap=not comun.MOVIL),
            *([ft.Row([self.filtro]), self.contador] if comun.MOVIL else
              [ft.Row([self.filtro, self.contador], spacing=12, wrap=True)]),
            self.lista,
        ], spacing=10, expand=True)
        self.recargar(actualizar=False)
        return vista

    def recargar(self, actualizar: bool = True) -> None:
        try:
            self.filas = [r for r in self.app.reparaciones.listar() if R.reparada(r)]
        except FirebaseError as e:
            self.filas = []
            self.app.manejar_error(e)
        self.filas.sort(key=lambda r: str(r.get("fecha_reparacion") or ""), reverse=True)
        self._pintar(actualizar)

    def _visibles(self) -> list[dict]:
        texto = (self.buscar.value or "").strip().lower()
        f = self.filtro.value or "pendientes"
        salida = []
        for r in self.filas:
            if f == "pendientes" and r.get("verificado"):
                continue
            if f in R.VERIFICACIONES and r.get("verificado") != f:
                continue
            if texto:
                pajar = " ".join(str(r.get(k, "")) for k in ("numero", "sku", "producto")).lower()
                if texto not in pajar and R.clave(texto) != R.clave(r.get("numero")):
                    continue
            salida.append(r)
        return salida

    def _tarjeta(self, r: dict) -> ft.Control:
        es_os = not R.es_venta(R.clave(r.get("numero")))
        detalle = [x for x in (f"Reparada {fecha_corta(r.get('fecha_reparacion'))}" if r.get("fecha_reparacion")
                               else "", f"Final: {r['estado_final']}" if r.get("estado_final") else "") if x]
        return tarjeta_lista(ft.Column([
            ft.Row([ft.Text(("OS " if es_os else "Venta ") + str(r.get("numero", "")), weight=ft.FontWeight.W_700,
                            size=15), chip_verificacion(r)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Text(" · ".join(x for x in (r.get("sku"), r.get("producto")) if x) or "—", size=12, max_lines=2,
                    overflow=ft.TextOverflow.ELLIPSIS),
            *([ft.Text(f"Qué se hizo: {r['que_se_hizo']}", size=12, max_lines=2,
                       overflow=ft.TextOverflow.ELLIPSIS)] if r.get("que_se_hizo") else []),
            *([ft.Text("  ·  ".join(detalle), size=12, color=ft.Colors.ON_SURFACE_VARIANT)] if detalle else []),
        ], spacing=4), lambda r=r: self.verificar(r))

    def _pintar(self, actualizar: bool = True) -> None:
        filas = self._visibles()
        self.lista.controls = [self._tarjeta(r) for r in filas[:300]] or [
            ft.Container(ft.Text("No hay reparaciones para verificar." if self.filtro.value == "pendientes"
                                 else "No hay reparaciones con ese filtro.", color=ft.Colors.ON_SURFACE_VARIANT),
                         padding=20)]
        pendientes = sum(1 for r in self.filas if not r.get("verificado"))
        self.contador.value = f"{pendientes} para verificar"
        if actualizar:
            self.app.page.update()

    # ------------------------------------------------------------ verificar
    def verificar(self, r: dict) -> None:
        page = self.app.page
        resultado = ft.RadioGroup(ft.Row([ft.Radio(value=v, label=v) for v in R.VERIFICACIONES], wrap=True),
                                  value=r.get("verificado") or None)
        notas = ft.TextField(label="¿Por qué no funciona? / notas", value=r.get("notas_verificado", ""),
                             multiline=True, min_lines=2, max_lines=5)
        error = ft.Text("", color=ft.Colors.ERROR, visible=False)

        def dato(etiqueta, valor):
            return ft.Column([ft.Text(etiqueta, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                              ft.Text(str(valor) if valor not in (None, "") else "—", selectable=True)], spacing=1)

        cuerpo = [
            ft.Row([dato("Producto", r.get("producto")), dato("SKU", r.get("sku"))], spacing=24, wrap=True),
            ft.Row([dato("Reparada", fecha_corta(r.get("fecha_reparacion"))), dato("Estado final", r.get("estado_final")),
                    dato("Causa", r.get("causa"))], spacing=24, wrap=True),
            dato("Qué había que reparar", r.get("a_realizar")),
            dato("Qué se hizo", r.get("que_se_hizo")),
        ]
        if r.get("verificado"):
            cuerpo.append(ft.Text(f"Verificada por {r.get('verificado_por', '')} el "
                                  f"{fecha_corta(r.get('verificado_en'))}: {r['verificado']}", size=12,
                                  color=ft.Colors.ON_SURFACE_VARIANT))
        cuerpo += [seccion("Resultado de la prueba"), resultado, notas, error]

        def guardar(_):
            if resultado.value not in R.VERIFICACIONES:
                error.value, error.visible = "Elija si funciona o no.", True
                page.update()
                return
            if resultado.value == "No funciona" and not (notas.value or "").strip():
                error.value, error.visible = "Escriba por qué no funciona.", True
                page.update()
                return
            try:
                self.app.reparaciones.verificar(r.get("numero"), resultado.value, notas.value or "",
                                                self.app.usuario)
            except FirebaseError as e:
                error.value, error.visible = str(e), True
                page.update()
                return
            page.close(dlg)
            self.app.avisar(f"Reparación {r.get('numero')} verificada: {resultado.value}.")
            self.recargar()

        es_os = not R.es_venta(R.clave(r.get("numero")))
        dlg = ft.AlertDialog(
            modal=True, title=ft.Text(("OS " if es_os else "Venta ") + str(r.get("numero", ""))),
            inset_padding=ft.padding.symmetric(16, 10) if comun.MOVIL else None,
            content=ft.Container(ft.Column(cuerpo, tight=True, spacing=10, scroll=ft.ScrollMode.AUTO), width=620),
            actions=[ft.TextButton("Cancelar", on_click=lambda _: page.close(dlg)),
                     ft.FilledButton("Guardar", icon=ft.Icons.FACT_CHECK, on_click=guardar)])
        page.open(dlg)


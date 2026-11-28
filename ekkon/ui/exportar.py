"""Exportar un .csv con quién cargó cada devolución (para separar las procesadas por cada persona)."""
from __future__ import annotations

import datetime as dt

import flet as ft

from ..datos import csv_por_usuario
from ..firebase import FirebaseError


def exportar_por_usuario(app) -> None:
    page: ft.Page = app.page
    hoy = dt.date.today()
    rango = {"desde": hoy.replace(day=1), "hasta": hoy}
    try:
        devoluciones = app.devs.todas()
    except FirebaseError as e:
        app.manejar_error(e)
        return
    try:
        nombres = {u.get("email", ""): u.get("nombre") or u.get("email", "") for u in app.usuarios.listar()}
    except FirebaseError:
        nombres = {}
    totales_txt = ft.Column(spacing=4)
    btn_desde = ft.OutlinedButton(icon=ft.Icons.EVENT)
    btn_hasta = ft.OutlinedButton(icon=ft.Icons.EVENT)
    guardar_como = ft.FilePicker()
    page.overlay.append(guardar_como)
    estado = {"texto": "", "totales": {}}

    def calcular():
        estado["texto"], estado["totales"] = csv_por_usuario(devoluciones, rango["desde"], rango["hasta"], nombres)
        btn_desde.text = "Desde " + rango["desde"].strftime("%d/%m/%Y")
        btn_hasta.text = "Hasta " + rango["hasta"].strftime("%d/%m/%Y")
        total = sum(estado["totales"].values())
        totales_txt.controls = [ft.Text(f"{total} devolución(es) cargadas en ese período:", weight=ft.FontWeight.W_600)]
        totales_txt.controls += [ft.Text(f"   {quien}: {n}") for quien, n in estado["totales"].items()] or [
            ft.Text("   Ninguna.", color=ft.Colors.ON_SURFACE_VARIANT)]
        page.update()

    def elegir(cual):
        def al_elegir(e):
            if e.control.value:
                rango[cual] = e.control.value.date() if isinstance(e.control.value, dt.datetime) else e.control.value
                if rango["desde"] > rango["hasta"]:
                    rango["desde"], rango["hasta"] = rango["hasta"], rango["desde"]
                calcular()
        page.open(ft.DatePicker(value=dt.datetime.combine(rango[cual], dt.time()), first_date=dt.datetime(2026, 1, 1),
                                last_date=dt.datetime.combine(hoy, dt.time()), on_change=al_elegir))

    btn_desde.on_click = lambda _: elegir("desde")
    btn_hasta.on_click = lambda _: elegir("hasta")

    def guardado(e: ft.FilePickerResultEvent):
        if not e.path:
            return
        ruta = e.path if e.path.lower().endswith(".csv") else e.path + ".csv"
        try:
            with open(ruta, "w", encoding="utf-8-sig", newline="") as fh:   # con BOM: Excel respeta los acentos
                fh.write(estado["texto"])
        except OSError as err:
            app.avisar(f"No se pudo guardar: {err}", error=True)
            return
        app.avisar(f"Guardado: {ruta}")

    guardar_como.on_result = guardado

    def guardar(_):
        page.close(dlg)
        nombre = f"cargas_por_usuario_{rango['desde'].isoformat()}_a_{rango['hasta'].isoformat()}.csv"
        guardar_como.save_file(dialog_title="Guardar el .csv", file_name=nombre, allowed_extensions=["csv"])

    dlg = ft.AlertDialog(
        modal=True, title=ft.Text("Exportar quién cargó cada devolución"),
        content=ft.Container(ft.Column([
            ft.Text("Un .csv con la fecha de carga, quién la cargó, el Venta #, el tipo, la clasificación y el estado. "
                    "Se abre con Excel.", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Row([btn_desde, btn_hasta], wrap=True),
            totales_txt,
        ], tight=True, spacing=12), width=520),
        actions=[ft.TextButton("Cancelar", on_click=lambda _: page.close(dlg)),
                 ft.FilledButton("Guardar .csv", icon=ft.Icons.DOWNLOAD, on_click=guardar)])
    page.open(dlg)
    calcular()

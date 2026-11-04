"""Sincronización de devoluciones con la planilla, con resumen previo y confirmación."""
from __future__ import annotations

import flet as ft

from ..firebase import FirebaseError
from ..planilla import planificar
from ..sheets import Planilla, SheetsError, id_de_link


def abrir_planilla(app) -> Planilla:
    return Planilla(id_de_link(app.config.get("planilla_url", "")))


def sincronizar(app, al_terminar=None) -> None:
    page: ft.Page = app.page
    espera = ft.AlertDialog(modal=True, content=ft.Row([ft.ProgressRing(), ft.Text("Leyendo la planilla…")],
                                                       tight=True, spacing=16))
    page.open(espera)
    try:
        planilla = abrir_planilla(app)
        hoja = planilla.leer()
        devoluciones = app.devs.recientes(1000)
        plan = planificar(hoja, devoluciones)
    except (SheetsError, ValueError, FirebaseError) as e:
        page.close(espera)
        app.avisar(str(e), error=True)
        return
    page.close(espera)

    lineas: list[ft.Control] = []
    if plan.filas_nuevas:
        lineas.append(ft.Text(f"• Agregar {len(plan.filas_nuevas)} venta(s) nueva(s) al final "
                              f"(desde la fila {plan.filas_nuevas[0][0]})."))
    if plan.celdas:
        lineas.append(ft.Text(f"• Completar {len(plan.celdas)} celda(s) vacía(s) en "
                              f"{len(plan.actualizadas)} venta(s) que ya estaban."))
    if plan.vacio:
        lineas.append(ft.Text("La planilla ya está al día. No hay nada para escribir."))
    if plan.sin_columna:
        lineas.append(ft.Text("No encontré estas columnas y se omiten: " + ", ".join(sorted(plan.sin_columna)),
                              color=ft.Colors.ERROR))
    if plan.conflictos:
        lineas.append(ft.Text(f"{len(plan.conflictos)} celda(s) tienen un valor distinto al del programa. "
                              "No se tocan:", weight=ft.FontWeight.W_600))
        tabla = ft.DataTable(
            columns=[ft.DataColumn(ft.Text(t)) for t in ("Venta", "Columna", "En la planilla", "En el programa")],
            rows=[ft.DataRow([ft.DataCell(ft.Text(str(x), size=12)) for x in c]) for c in plan.conflictos[:100]],
            heading_row_height=34, data_row_min_height=30, data_row_max_height=36, column_spacing=18)
        lineas.append(ft.Container(ft.Column([tabla], scroll=ft.ScrollMode.AUTO), height=220))

    dlg = ft.AlertDialog(modal=True, title=ft.Text("Sincronizar con la planilla"),
                         content=ft.Container(ft.Column(lineas, tight=True, spacing=10), width=720))

    def aplicar(_):
        page.close(dlg)
        try:
            planilla.aplicar(plan, hoja)
        except SheetsError as e:
            app.avisar(str(e), error=True)
            return
        app.avisar(f"Planilla actualizada: {len(plan.filas_nuevas)} fila(s) nueva(s) y "
                   f"{len(plan.celdas)} celda(s) completada(s).")
        if al_terminar:
            al_terminar()

    acciones: list[ft.Control] = [ft.TextButton("Cerrar" if plan.vacio else "Cancelar",
                                                on_click=lambda _: page.close(dlg))]
    if not plan.vacio:
        acciones.append(ft.FilledButton("Escribir en la planilla", icon=ft.Icons.CLOUD_UPLOAD, on_click=aplicar))
    dlg.actions = acciones
    page.open(dlg)

"""Sincronización de devoluciones con la planilla, con resumen previo y confirmación."""
from __future__ import annotations

import datetime

import flet as ft

from ..firebase import FirebaseError
from .. import reparaciones as R
from ..planilla import planificar
from ..sheets import Planilla, SheetsError, id_de_link


def abrir_planilla(app) -> Planilla:
    return Planilla(id_de_link(app.config.get("planilla_url", "")))


def sincronizar(app, al_terminar=None) -> None:
    page: ft.Page = app.page
    espera = ft.AlertDialog(modal=True, content=ft.Row([ft.ProgressRing(), ft.Text("Leyendo la planilla y el informe…")],
                                                       tight=True, spacing=16))
    page.open(espera)
    # Si se están corrigiendo devoluciones en segundo plano, espera a que terminen
    with app.candado:
        pass
    try:
        planilla = abrir_planilla(app)
        hoja = planilla.leer()
        devoluciones = app.devs.recientes(1000)
        try:
            ventas = app.indice.todas()
        except FirebaseError:
            ventas = {}
        # Reparaciones terminadas de devoluciones: agregan la nota y cambian la clasificación
        cambios_rep: dict[str, dict] = {}
        try:
            reps = {R.clave(r.get("numero")): r for r in app.reparaciones.listar() if R.es_venta(R.clave(r.get("numero")))}
        except FirebaseError:
            reps = {}
        for d in devoluciones:
            r = reps.get(d.get("numero_venta", ""))
            cambios = R.cambios_para_devolucion(d, r) if r else {}
            if cambios:
                d.update(cambios)
                cambios_rep[d["numero_venta"]] = cambios
        plan = planificar(hoja, devoluciones, ventas)
    except (SheetsError, ValueError, FirebaseError) as e:
        page.close(espera)
        app.avisar(str(e), error=True)
        return
    page.close(espera)

    correcciones = plan.correcciones()
    corregir = ft.Checkbox(label=f"Corregir también esas {len(correcciones)} fila(s): reemplazar el ID Carrito "
                                 "por el Venta #", value=True, visible=bool(correcciones))
    lineas: list[ft.Control] = []
    if plan.filas_nuevas:
        lineas.append(ft.Text(f"• Agregar {len(plan.filas_nuevas)} venta(s) nueva(s) al final "
                              f"(desde la fila {plan.filas_nuevas[0][0]})."))
    if plan.celdas:
        lineas.append(ft.Text(f"• Completar {len(plan.celdas)} celda(s) vacía(s) en "
                              f"{len(plan.actualizadas)} venta(s) que ya estaban."))
    if plan.completadas_informe:
        lineas.append(ft.Text(f"  De esas, {len(plan.completadas_informe)} son filas cargadas a mano que se "
                              "completan con el informe de ventas (fecha de compra, artículo, SKU, depósito, costo).",
                              size=12, color=ft.Colors.ON_SURFACE_VARIANT))
    if not ventas:
        lineas.append(ft.Text("No hay informe de ventas importado: no se completan fecha de compra, artículo "
                              "ni costo.", color=ft.Colors.AMBER_800))
    if plan.vacio and not correcciones:
        lineas.append(ft.Text("La planilla ya está al día. No hay nada para escribir."))
    if plan.carritos:
        lineas.append(ft.Text(f"{len(plan.carritos)} fila(s) tienen el ID Carrito en \"N° Venta\":",
                              weight=ft.FontWeight.W_600))
        for a1, carrito, vs in plan.carritos[:30]:
            detalle = f"→ Venta # {vs[0]}" if len(vs) == 1 else f"→ carrito con {len(vs)} ventas, corregir a mano"
            lineas.append(ft.Text(f"   {a1}: {carrito} {detalle}", size=12))
        lineas.append(corregir)
    if plan.resueltas_en_planilla:
        lineas.append(ft.Text(f"• {len(plan.resueltas_en_planilla)} reclamo(s) que en el programa figuran esperando "
                              "respuesta ya tienen resultado en la planilla: se actualizan en el programa."))
    if cambios_rep:
        lineas.append(ft.Text(f"• {len(cambios_rep)} devolución(es) con la reparación terminada: se agrega la nota "
                              "y se actualiza la clasificación."))
    if plan.duplicadas:
        lineas.append(ft.Text("Ventas cargadas dos veces en el programa (se escribe una sola fila):",
                              weight=ft.FontWeight.W_600, color=ft.Colors.AMBER_800))
        for venta, usada, repetida in plan.duplicadas[:20]:
            lineas.append(ft.Text(f"   Venta # {venta}: se usa la carga {usada}; sobra la carga {repetida}.", size=12))
    if plan.repetidas_en_planilla:
        lineas.append(ft.Text("Ventas que aparecen más de una vez en la planilla (borre la fila que sobra):",
                              weight=ft.FontWeight.W_600, color=ft.Colors.AMBER_800))
        for venta, filas in plan.repetidas_en_planilla[:20]:
            lineas.append(ft.Text(f"   {venta}: filas {', '.join(map(str, filas))}", size=12))
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
                         content=ft.Container(ft.Column(lineas, tight=True, spacing=8, scroll=ft.ScrollMode.AUTO),
                                              width=760))

    def aplicar(_):
        page.close(dlg)
        try:
            if not plan.vacio:
                planilla.aplicar(plan, hoja)
            if correcciones and corregir.value:
                planilla.escribir(correcciones)
        except SheetsError as e:
            app.avisar(str(e), error=True)
            return
        hoy = datetime.date.today().isoformat()
        for doc_id in plan.planilla_en:
            try:
                app.devs.actualizar(doc_id, {"planilla_en": hoy})
            except FirebaseError:
                pass
        for doc_id, cambios in plan.resueltas_en_planilla:
            try:
                app.devs.actualizar(doc_id, cambios)
            except FirebaseError:
                pass
        for numero, cambios in cambios_rep.items():
            try:
                app.devs.actualizar(numero, cambios)
            except FirebaseError:
                pass
        # Lo que se completó en la planilla con el informe también queda en el programa
        for d in devoluciones:
            v = ventas.get(d.get("numero_venta", ""))
            if v and not (d.get("producto") and d.get("deposito_origen")):
                try:
                    app.devs.actualizar(d["numero_venta"], app.completar_desde_informe(d, v))
                except FirebaseError:
                    pass
        extra = f" y {len(correcciones)} N° Venta corregido(s)" if correcciones and corregir.value else ""
        app.avisar(f"Planilla actualizada: {len(plan.filas_nuevas)} fila(s) nueva(s), "
                   f"{len(plan.celdas)} celda(s) completada(s){extra}.")
        if al_terminar:
            al_terminar()

    hay_algo = not plan.vacio or bool(correcciones) or bool(plan.resueltas_en_planilla)
    acciones: list[ft.Control] = [ft.TextButton("Cancelar" if hay_algo else "Cerrar",
                                                on_click=lambda _: page.close(dlg))]
    if hay_algo:
        acciones.append(ft.FilledButton("Escribir en la planilla", icon=ft.Icons.CLOUD_UPLOAD, on_click=aplicar))
    dlg.actions = acciones
    page.open(dlg)

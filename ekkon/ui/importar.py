"""Importar al programa las devoluciones que están solo en la planilla (cargadas a mano antes de la app)."""
from __future__ import annotations

from collections import Counter

import flet as ft

from .. import settings
from ..datos import COL_DEV
from ..firebase import FirebaseError
from ..planilla import importar_de_hoja
from ..sheets import SheetsError
from .sincronizar import abrir_planilla


def importar_devoluciones(app, al_terminar=None) -> None:
    page: ft.Page = app.page
    espera = ft.AlertDialog(modal=True, content=ft.Row([ft.ProgressRing(), ft.Text("Leyendo la planilla…")],
                                                       tight=True, spacing=16))
    page.open(espera)
    with app.candado:
        pass
    try:
        hoja = abrir_planilla(app).leer()
        existentes: set[str] = set()
        for d in app.devs.recientes(20000):
            existentes.update(x for x in (d.get("numero_venta"), d.get("carrito"), d.get("_id")) if x)
        try:
            ventas = app.indice.todas()
        except FirebaseError:
            ventas = {}
        imp = importar_de_hoja(hoja, existentes, ventas)
    except (SheetsError, ValueError, FirebaseError) as e:
        page.close(espera)
        app.avisar(str(e), error=True)
        return
    page.close(espera)

    lineas: list[ft.Control] = []
    if imp.nuevas:
        lineas.append(ft.Text(f"Se agregan {len(imp.nuevas)} devolución(es) que están solo en la planilla.",
                              weight=ft.FontWeight.W_600))
        por_estado = Counter(d["estado"] for d in imp.nuevas)
        lineas.append(ft.Text("  " + "  ·  ".join(f"{settings.ESTADOS.get(e, e)}: {n}"
                                                 for e, n in por_estado.most_common()), size=12))
        sin_nc = sum(1 for d in imp.nuevas if settings.necesita_nc(d) and not d.get("nc_realizada"))
        if sin_nc:
            lineas.append(ft.Text(f"  {sin_nc} tienen NdC vacía: van a aparecer en Pendientes como sin NC.",
                                  size=12, color=ft.Colors.AMBER_800))
        lineas.append(ft.Text("Quedan sin fotos ni mensaje de reclamo. La planilla no se modifica: para estas "
                              "filas, lo que diga la planilla manda.", size=12, color=ft.Colors.ON_SURFACE_VARIANT))
    else:
        lineas.append(ft.Text("No hay devoluciones nuevas en la planilla: ya están todas en el programa."))
    if imp.ya_estaban:
        lineas.append(ft.Text(f"{imp.ya_estaban} fila(s) ya estaban en el programa.", size=12,
                              color=ft.Colors.ON_SURFACE_VARIANT))
    if imp.omitidas:
        lineas.append(ft.Text(f"{len(imp.omitidas)} fila(s) no se importan:", weight=ft.FontWeight.W_600,
                              color=ft.Colors.AMBER_800))
        for fila, numero, motivo in imp.omitidas[:40]:
            lineas.append(ft.Text(f"   Fila {fila} ({numero}): {motivo}.", size=12))

    dlg = ft.AlertDialog(modal=True, title=ft.Text("Importar de la planilla"),
                         content=ft.Container(ft.Column(lineas, tight=True, spacing=8, scroll=ft.ScrollMode.AUTO),
                                              width=720))

    def aplicar(_):
        page.close(dlg)
        aviso = ft.AlertDialog(modal=True, content=ft.Row([ft.ProgressRing(),
                                                           ft.Text(f"Guardando {len(imp.nuevas)} devolución(es)…")],
                                                          tight=True, spacing=16))
        page.open(aviso)
        try:
            app.fs.guardar_varios([(f"{COL_DEV}/{d['numero_venta']}", d) for d in imp.nuevas])
        except FirebaseError as e:
            page.close(aviso)
            app.manejar_error(e)
            return
        page.close(aviso)
        app.avisar(f"Se importaron {len(imp.nuevas)} devolución(es) de la planilla.")
        if al_terminar:
            al_terminar()

    acciones: list[ft.Control] = [ft.TextButton("Cancelar" if imp.nuevas else "Cerrar",
                                                on_click=lambda _: page.close(dlg))]
    if imp.nuevas:
        acciones.append(ft.FilledButton(f"Importar {len(imp.nuevas)}", icon=ft.Icons.DOWNLOAD, on_click=aplicar))
    dlg.actions = acciones
    page.open(dlg)

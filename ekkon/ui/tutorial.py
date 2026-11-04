"""Tutorial integrado: se muestra al primer ingreso y desde el botón de ayuda."""
from __future__ import annotations

import json

import flet as ft

from .. import local

# Cada paso: (icono, título, [puntos]). Los textos están pensados para leerse en pocos segundos.
PASOS_CARGA = [
    (ft.Icons.WAVING_HAND, "Bienvenido",
     ["Acá se cargan las devoluciones de Mercado Libre. Ya no se usa Notion.",
      "Este tutorial tiene pocos pasos. Lo puede volver a abrir cuando quiera con el botón de ayuda (?) "
      "de la barra izquierda."]),
    (ft.Icons.TAG, "1. Número de venta",
     ["El botón \"Ver en ML las que vencen hoy\" abre la lista de devoluciones del día en Mercado Libre.",
      "Copie el número de venta desde ahí y péguelo con Ctrl+V. No lo escriba a mano.",
      "Si el número tiene algo raro, el programa le avisa debajo del campo.",
      "Si la venta ya estaba cargada, también le avisa."]),
    (ft.Icons.EVENT, "2. Fecha de vencimiento",
     ["Es el día en que vence el plazo para reclamar.",
      "Por defecto está la fecha de hoy. Tóquela para cambiarla."]),
    (ft.Icons.LOCAL_SHIPPING, "3. Motivo y depósito",
     ["En \"Motivo\" elija el motivo de la devolución tal como figura en Mercado Libre.",
      "En \"Depósito de origen\" deje Podesta. Elija Full solo si el producto vino del depósito de Full."]),
    (ft.Icons.CATEGORY, "4. Clasificación y condición",
     ["Clasificación: N vuelve a stock. A, B y C van a outlet. D, E y Service van al service externo. "
      "Service Interno se repara acá. Scrap es descarte.",
      "Condición: el programa la sugiere al elegir la clasificación, pero no siempre acierta. "
      "Revísela: buena, caja rota, con uso, service, irreparable, etc.",
      "Si elige N, el reclamo se desactiva solo. Si corresponde reclamar igual, vuelva a activarlo."]),
    (ft.Icons.PHOTO_CAMERA, "5. Estado y fotos",
     ["Escriba solo lo que se ve: golpes, rayones, faltantes, suciedad, señales de uso.",
      "No invente fallas. Mercado Libre pide describir con precisión.",
      "Toque \"Agregar fotos\" y elija las fotos del producto (de 1 a 8)."]),
    (ft.Icons.AUTO_AWESOME, "6. Armar reclamo",
     ["Toque \"Armar reclamo\". Se abren Claude y una carpeta con las fotos.",
      "En Claude: pegue con Ctrl+V, arrastre las fotos desde la carpeta y envíe.",
      "Cuando Claude responda, copie toda la respuesta.",
      "Vuelva acá y toque \"Pegar respuesta de Claude\". El mensaje y el porcentaje se completan solos."]),
    (ft.Icons.SAVE, "7. Guardar",
     ["Revise el mensaje y toque \"Guardar\". El formulario queda limpio para la próxima.",
      "Arriba del formulario hay una lista de pasos: cuando todos están en verde, ya puede guardar.",
      "En \"Devoluciones\" ve todo lo cargado. Si se equivocó, abra la venta y toque \"Editar\"."]),
]

PASOS_ADMIN = [
    (ft.Icons.HOURGLASS_FULL, "Pendientes",
     ["Muestra los reclamos armados o enviados que esperan respuesta de Mercado Libre.",
      "Abra una venta para marcarla como enviada o registrar el resultado: cobertura, monto y N° de movimiento."]),
    (ft.Icons.PEOPLE, "Usuarios",
     ["Cree usuarios y elija su perfil: Administrador o Carga.",
      "Apague \"Activo\" para bloquear a alguien. Queda afuera aunque tenga el programa abierto."]),
    (ft.Icons.TABLE_CHART, "Planilla y emails",
     ["En \"Devoluciones\", el botón \"Sincronizar planilla\" completa la planilla de Google Sheets.",
      "Solo completa celdas vacías y agrega las ventas que faltan. Nunca pisa lo que usted escribió.",
      "En \"Emails\" se arman las solicitudes de transferencia y de baja/alta outlet con las NC realizadas."]),
    (ft.Icons.SETTINGS, "Ajustes",
     ["Cargue el link del proyecto de Claude, el link de la planilla, la clave de la cuenta de servicio "
      "y los destinatarios de los emails.",
      "Con \"Versión mínima permitida\" puede obligar a todos a actualizar el programa."]),
]


def _archivo(uid: str):
    return local.carpeta_datos() / f"tutorial_{uid}.json"


def ya_visto(uid: str) -> bool:
    try:
        return json.loads(_archivo(uid).read_text("utf-8")).get("visto", False)
    except (OSError, ValueError):
        return False


def marcar_visto(uid: str, visto: bool = True) -> None:
    _archivo(uid).write_text(json.dumps({"visto": visto}), "utf-8")


def mostrar(app) -> None:
    page: ft.Page = app.page
    pasos = list(PASOS_CARGA)
    if app.es_admin:
        pasos += PASOS_ADMIN
    estado = {"i": 0}

    icono = ft.Icon(size=56, color=ft.Colors.PRIMARY)
    titulo = ft.Text(size=22, weight=ft.FontWeight.W_700, text_align=ft.TextAlign.CENTER)
    puntos = ft.Column(spacing=12)
    indicador = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=6)
    no_mostrar = ft.Checkbox(label="No mostrar al iniciar", value=ya_visto(app.usuario["_id"]))
    btn_atras = ft.TextButton("Anterior", icon=ft.Icons.ARROW_BACK)
    btn_sig = ft.FilledButton("Siguiente", icon=ft.Icons.ARROW_FORWARD)

    def pintar():
        i = estado["i"]
        ic, ti, items = pasos[i]
        icono.name = ic
        titulo.value = ti
        puntos.controls = [
            ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=20, color=ft.Colors.PRIMARY),
                    ft.Text(t, size=15, expand=True)], vertical_alignment=ft.CrossAxisAlignment.START)
            for t in items]
        indicador.controls = [
            ft.Container(width=22 if j == i else 8, height=8, border_radius=4,
                         bgcolor=ft.Colors.PRIMARY if j == i else ft.Colors.OUTLINE_VARIANT)
            for j in range(len(pasos))]
        btn_atras.disabled = i == 0
        ultimo = i == len(pasos) - 1
        btn_sig.text = "Terminar" if ultimo else "Siguiente"
        btn_sig.icon = ft.Icons.CHECK if ultimo else ft.Icons.ARROW_FORWARD
        page.update()

    def cerrar(_=None):
        marcar_visto(app.usuario["_id"], True if estado["i"] == len(pasos) - 1 else bool(no_mostrar.value))
        page.close(dlg)

    def mover(delta):
        nuevo = estado["i"] + delta
        if nuevo >= len(pasos):
            cerrar()
            return
        estado["i"] = max(0, nuevo)
        pintar()

    btn_atras.on_click = lambda _: mover(-1)
    btn_sig.on_click = lambda _: mover(1)

    dlg = ft.AlertDialog(
        modal=True,
        content=ft.Container(ft.Column([
            ft.Row([ft.IconButton(ft.Icons.CLOSE, tooltip="Cerrar tutorial", on_click=cerrar)],
                   alignment=ft.MainAxisAlignment.END),
            ft.Container(icono, alignment=ft.alignment.center),
            ft.Container(titulo, alignment=ft.alignment.center),
            ft.Container(puntos, padding=ft.padding.symmetric(8, 6)),
            indicador,
        ], tight=True, spacing=14), width=560, height=360),
        actions=[ft.Row([no_mostrar, ft.Row([btn_atras, btn_sig], tight=True)],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN, width=560)],
    )
    page.open(dlg)
    pintar()

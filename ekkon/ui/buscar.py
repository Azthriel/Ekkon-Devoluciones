"""Buscar venta: se escanea (o escribe) el N° de envío de la etiqueta y se ve a qué venta y producto corresponde."""
from __future__ import annotations

import flet as ft

from .. import settings
from ..envios_idx import solo_digitos
from ..firebase import FirebaseError
from ..local import abrir_url
from . import comun
from .comun import fecha_corta, tarjeta, titulo

ESTADOS_ENVIO = {"devolucion entregada": "Entregada", "devolucion enviada": "En camino",
                 "label_generated": "Etiqueta generada", "devolucion expirada": "Expirada",
                 "devolucion cancelada": "Cancelada", "devolucion no entregada": "No entregada"}


class VistaBuscar:
    def __init__(self, app):
        self.app = app
        self.page: ft.Page = app.page
        self.campo = ft.TextField(
            label="N° de envío, Venta #, ID Carrito o ID Reclamo", prefix_icon=ft.Icons.QR_CODE_SCANNER,
            autofocus=True, on_submit=lambda _: self.buscar(), expand=True,
            keyboard_type=ft.KeyboardType.NUMBER if comun.MOVIL else None,
            helper_text="Con el lector de códigos: escanee la etiqueta y busca solo.")
        self.resultado = ft.Column(spacing=12)
        self.btn_escanear = ft.FilledButton("Escanear", icon=ft.Icons.QR_CODE_SCANNER, on_click=self._escanear,
                                            visible=getattr(app, "escaner", None) is not None)

    def control(self) -> ft.Control:
        cabeza: list[ft.Control] = []
        if not comun.MOVIL:
            cabeza.append(titulo("Buscar venta", "Para las etiquetas que traen solo el código de barras del envío."))
        sin_informe = []
        try:
            meta = self.app.indice_envios.meta()
        except FirebaseError:
            meta = {}
        if not meta.get("importado_en"):
            sin_informe.append(ft.Text("Todavía no se importó el informe \"Devoluciones para APP\" (Ajustes). "
                                       "Por ahora solo se puede buscar por Venta # o ID Carrito.",
                                       color=ft.Colors.AMBER_800, size=13))
        else:
            sin_informe.append(ft.Text(f"Informe de devoluciones del {fecha_corta(meta['importado_en'])}.", size=12,
                                       color=ft.Colors.ON_SURFACE_VARIANT))
        return ft.Column(cabeza + [
            ft.Row([self.campo, ft.FilledTonalButton("Buscar", icon=ft.Icons.SEARCH, on_click=lambda _: self.buscar()),
                    self.btn_escanear], wrap=comun.MOVIL, vertical_alignment=ft.CrossAxisAlignment.START)
            if not comun.MOVIL else ft.Column([ft.Row([self.campo]), ft.Row([
                ft.FilledTonalButton("Buscar", icon=ft.Icons.SEARCH, on_click=lambda _: self.buscar(), expand=True),
                self.btn_escanear])], spacing=8),
            *sin_informe,
            self.resultado,
        ], spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)

    def _escanear(self, _=None) -> None:
        try:
            codigo = self.app.escaner.escanear()
        except Exception as e:  # noqa: BLE001 - cámara cancelada, sin permiso, tiempo agotado
            self.app.avisar(f"No se pudo escanear: {e}", error=True)
            return
        if codigo:
            self.campo.value = codigo
            self.buscar()

    # ------------------------------------------------------------ búsqueda
    def buscar(self) -> None:
        texto = (self.campo.value or "").strip()
        self.resultado.controls = []
        if not texto:
            self.page.update()
            return
        try:
            encontrados = self.app.indice_envios.buscar(texto)
        except FirebaseError as e:
            self.app.manejar_error(e)
            encontrados = []
        tarjetas = [self._tarjeta_envio(e) for e in encontrados]
        if not tarjetas:
            # Sin informe de devoluciones: quizás es un Venta # o ID Carrito
            tarjeta_venta = self._tarjeta_por_venta(solo_digitos(texto))
            if tarjeta_venta:
                tarjetas.append(tarjeta_venta)
        if not tarjetas:
            tarjetas.append(tarjeta(ft.Row([
                ft.Icon(ft.Icons.SEARCH_OFF, color=ft.Colors.AMBER_800),
                ft.Text(f"No encontré {texto}. Si es un envío nuevo, importe un informe de devoluciones más reciente "
                        "en Ajustes.", expand=True)])))
        self.resultado.controls = tarjetas
        # Para el próximo escaneo: el texto queda seleccionado y se reemplaza solo
        self.campo.value = ""
        self.campo.hint_text = f"Última búsqueda: {texto}"
        self.page.update()
        try:
            self.campo.focus()
        except Exception:  # noqa: BLE001
            pass

    def _venta_del_informe(self, numero: str, sku: str = ""):
        """(Venta, ID Carrito) a partir de un Venta # o ID Carrito, usando el informe de ventas."""
        try:
            r = self.app.indice.buscar(numero)
        except FirebaseError:
            return None, ""
        if r.tipo == "venta":
            return r.venta, r.venta.carrito
        if r.tipo == "carrito":
            if r.venta:
                return r.venta, numero
            elegidas = [o for o in (r.opciones or []) if sku and o[1] == sku]
            if len(elegidas) == 1:
                return self.app.indice.venta(elegidas[0][0]), numero
            return None, numero
        return None, ""

    def _devolucion_cargada(self, *numeros: str) -> dict | None:
        try:
            for d in self.app.devs.todas():
                if d.get("numero_venta") in numeros or (d.get("carrito") and d.get("carrito") in numeros):
                    return d
        except FirebaseError:
            pass
        return None

    def _tarjeta_envio(self, e: dict) -> ft.Control:
        venta, carrito = self._venta_del_informe(e.get("venta", ""), e.get("sku", ""))
        numero_venta = venta.venta if venta else e.get("venta", "")
        producto = e.get("producto") or (venta.producto if venta else "")
        sku = e.get("sku") or (venta.codigo if venta else "")
        datos = [("N° de envío", e.get("envio")), ("Venta #", numero_venta),
                 ("ID Carrito", carrito if carrito and carrito != numero_venta else ""),
                 ("Pedido", venta.pedido if venta else ""), ("Devolución", e.get("devolucion")),
                 ("Estado", ESTADOS_ENVIO.get(e.get("estado", ""), e.get("estado", ""))),
                 ("Creada", fecha_corta(e.get("fecha")))]
        return self._tarjeta(producto, sku, e.get("cantidad") or 1, datos, numero_venta, carrito)

    def _tarjeta_por_venta(self, numero: str) -> ft.Control | None:
        if len(numero) != 16:
            return None
        venta, carrito = self._venta_del_informe(numero)
        if not venta:
            return None
        datos = [("Venta #", venta.venta), ("ID Carrito", carrito if carrito and carrito != venta.venta else ""),
                 ("Pedido", venta.pedido), ("Vendida", venta.fecha.strftime("%d/%m/%Y") if venta.fecha else "")]
        return self._tarjeta(venta.producto, venta.codigo, venta.cantidad or 1, datos, venta.venta, carrito)

    def _tarjeta(self, producto: str, sku: str, cantidad: int, datos: list, numero_venta: str,
                 carrito: str) -> ft.Control:
        def copiar(valor, que):
            self.page.set_clipboard(valor)
            self.app.avisar(f"{que} {valor} copiado.")

        def dato(etiqueta, valor):
            if not valor:
                return None
            if etiqueta in ("Estado", "Creada", "Vendida"):
                return ft.Column([ft.Text(etiqueta, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                                  ft.Text(str(valor), weight=ft.FontWeight.W_600)], spacing=1)
            return ft.Container(ft.Column([
                ft.Text(etiqueta, size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Row([ft.Text(str(valor), weight=ft.FontWeight.W_600, color=ft.Colors.PRIMARY),
                        ft.Icon(ft.Icons.CONTENT_COPY, size=13, color=ft.Colors.PRIMARY)], spacing=4, tight=True)],
                spacing=1), on_click=lambda _: copiar(str(valor), etiqueta), tooltip="Tocar para copiar",
                border_radius=6, ink=True)

        cargada = self._devolucion_cargada(numero_venta, carrito)
        if cargada:
            estado = ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, color=ft.Colors.GREEN_700, size=18),
                             ft.Text(f"Ya está cargada en el programa ({settings.ESTADOS.get(cargada.get('estado'), '')})",
                                     color=ft.Colors.GREEN_700, weight=ft.FontWeight.W_600, expand=True)])
            accion = ft.OutlinedButton("Ver en Devoluciones", icon=ft.Icons.LIST_ALT,
                                       on_click=lambda _: self.app.ir_a_seccion("Devoluciones",
                                                                                buscar=cargada["numero_venta"]))
        else:
            estado = ft.Row([ft.Icon(ft.Icons.INFO_OUTLINE, color=ft.Colors.BLUE_700, size=18),
                             ft.Text("Todavía no está cargada en el programa.", color=ft.Colors.BLUE_700,
                                     expand=True)])
            accion = ft.FilledButton("Cargar esta devolución", icon=ft.Icons.ADD_A_PHOTO,
                                     on_click=lambda _: self.app.ir_a_seccion("Cargar", numero=numero_venta))
        return tarjeta(ft.Column([
            ft.Text("Esta es la venta de:", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Text(producto or "Producto sin nombre", size=20 if comun.MOVIL else 22, weight=ft.FontWeight.W_700,
                    selectable=True),
            ft.Row([ft.Container(ft.Text(f"SKU {sku or '—'}", weight=ft.FontWeight.W_600),
                                 bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.PRIMARY), border_radius=8,
                                 padding=ft.padding.symmetric(4, 10)),
                    ft.Text(f"Cantidad: {cantidad}", weight=ft.FontWeight.W_600 if cantidad > 1 else None,
                            color=ft.Colors.AMBER_800 if cantidad > 1 else None)], spacing=12, wrap=True),
            ft.Row([x for x in (dato(a, b) for a, b in datos) if x], spacing=24, run_spacing=10, wrap=True),
            estado,
            ft.Row([accion, ft.TextButton("Ver venta en ML", icon=ft.Icons.OPEN_IN_NEW,
                                          on_click=lambda _: abrir_url(page=self.page, url=settings.link_venta(
                                              numero_venta, carrito)))], wrap=True, spacing=8),
        ], spacing=10))

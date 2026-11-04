"""Carga y edición de devoluciones, con el armado del reclamo en Claude."""
from __future__ import annotations

import datetime as dt

import flet as ft

from .. import local, settings
from ..datos import armar_prompt, leer_respuesta_claude, validar_numero_venta
from ..firebase import FirebaseError
from ..fotos import comprimir, miniatura_b64
from .comun import seccion, tarjeta, titulo

URL_CLAUDE_POR_DEFECTO = "https://claude.ai/projects"


class VistaCarga:
    def __init__(self, app, existente: dict | None = None, al_terminar=None):
        self.app = app
        self.page: ft.Page = app.page
        self.existente = existente
        self.al_terminar = al_terminar
        self.editando = existente is not None
        self.guardada = self.editando  # ya existe en Firestore
        self.fotos: list[bytes] = []
        self.fotos_cambiaron = False
        self.cant_fotos_original = int((existente or {}).get("fotos", 0))
        self.vence = (existente or {}).get("fecha_vencimiento") or dt.date.today().isoformat()
        self._armar_controles()
        if self.editando:
            self._cargar_existente()

    # ------------------------------------------------------------ controles

    def _armar_controles(self) -> None:
        self.numero = ft.TextField(
            label="Número de venta *", hint_text="2000012345678901", width=320,
            prefix_icon=ft.Icons.TAG, on_change=self._validar_numero, on_blur=self._verificar_duplicado,
            read_only=self.editando)
        self.btn_vence = ft.OutlinedButton(icon=ft.Icons.EVENT, on_click=self._elegir_fecha, height=48)
        self.selector_fecha = ft.DatePicker(
            first_date=dt.datetime.now() - dt.timedelta(days=60),
            last_date=dt.datetime.now() + dt.timedelta(days=60),
            on_change=self._fecha_elegida)
        self.clasif = ft.Dropdown(
            label="Clasificación *", width=320,
            options=[ft.dropdown.Option(k, t) for k, t in settings.CLASIFICACIONES],
            on_change=self._clasif_cambio)
        self.condicion = ft.Dropdown(
            label="Condición *", width=320,
            options=[ft.dropdown.Option(c) for c in settings.CONDICIONES],
            helper_text="Se sugiere sola según la clasificación. Revísela.",
            on_change=lambda _: self._actualizar_pasos())
        self.motivo = ft.Dropdown(
            label="Motivo de la devolución *", width=480,
            options=[ft.dropdown.Option(m) for m in settings.MOTIVOS],
            helper_text="El motivo que figura en Mercado Libre.",
            on_change=lambda _: self._actualizar_pasos())
        self.deposito = ft.Dropdown(
            label="Depósito de origen", width=220, value="Podesta",
            options=[ft.dropdown.Option(d) for d in settings.DEPOSITOS_ORIGEN],
            helper_text="Full si vino del depósito de Full.")
        self.codigo = ft.TextField(label="SKU / código de producto", width=320, prefix_icon=ft.Icons.QR_CODE_2)
        self.link = ft.TextField(label="Link de la publicación", expand=True, prefix_icon=ft.Icons.LINK)
        self.problema = ft.TextField(label="Problema que informó el comprador", multiline=True,
                                     min_lines=2, max_lines=4,
                                     helper_text="Copiarlo de \"Problema de la venta\" y los mensajes del comprador.")
        self.descripcion = ft.TextField(label="Estado en que llegó el producto *", multiline=True,
                                        min_lines=3, max_lines=6,
                                        helper_text="Describir solo lo que se ve: golpes, faltantes, uso, suciedad, etc.",
                                        on_change=lambda _: self._actualizar_pasos())
        self.reclamo = ft.Switch(label="Corresponde reclamo a Mercado Libre", value=True,
                                 on_change=self._reclamo_cambio)

        self.galeria = ft.Row(wrap=True, spacing=10, run_spacing=10)
        self.btn_fotos = ft.OutlinedButton("Agregar fotos", icon=ft.Icons.ADD_PHOTO_ALTERNATE,
                                           on_click=self._pedir_fotos)
        self.txt_fotos = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)

        self.mensaje = ft.TextField(label="Mensaje de reclamo", multiline=True, min_lines=4, max_lines=6,
                                    max_length=settings.LIMITE_MENSAJE, expand=True,
                                    on_change=lambda _: self._actualizar_pasos())
        self.porcentaje = ft.TextField(label="% sugerido", width=130, suffix_text="%",
                                       input_filter=ft.NumbersOnlyInputFilter(), max_length=3,
                                       counter_text="")
        self.btn_armar = ft.FilledTonalButton("Armar reclamo", icon=ft.Icons.AUTO_AWESOME,
                                              on_click=self._armar_reclamo, height=46)
        self.btn_pegar = ft.OutlinedButton("Pegar respuesta de Claude", icon=ft.Icons.CONTENT_PASTE,
                                           on_click=self._pegar_respuesta, height=46)
        self.panel_reclamo = ft.Column([
            seccion("Reclamo"),
            ft.Text("1) \"Armar reclamo\" copia los datos, abre el proyecto de Claude y la carpeta con las fotos. "
                    "2) Pegue con Ctrl+V en Claude y arrastre las fotos. "
                    "3) Copie la respuesta y toque \"Pegar respuesta de Claude\".",
                    size=12, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Row([self.btn_armar, self.btn_pegar], wrap=True),
            ft.Row([self.mensaje, self.porcentaje], vertical_alignment=ft.CrossAxisAlignment.START),
        ], spacing=12)

        self.btn_guardar = ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=self._guardar, height=46)
        self.btn_limpiar = ft.TextButton("Limpiar", icon=ft.Icons.CLEAR_ALL, on_click=self._limpiar)
        self.progreso = ft.ProgressBar(visible=False)
        self.fila_pasos = ft.Row(wrap=True, spacing=8, run_spacing=8)
        self.siguiente = ft.Text(size=14, weight=ft.FontWeight.W_600)
        self._actualizar_fecha()
        self._actualizar_pasos(actualizar=False)

    def control(self) -> ft.Control:
        if self.selector_fecha not in self.page.overlay:
            self.page.overlay.append(self.selector_fecha)
        if self.editando:
            encabezado = titulo(f"Editar venta {self.existente['numero_venta']}",
                                "Los cambios se guardan sobre la carga existente.")
        else:
            encabezado = ft.Row([
                titulo("Cargar devolución", "Complete los datos y las fotos del producto devuelto."),
                ft.OutlinedButton("Ver en ML las que vencen hoy", icon=ft.Icons.OPEN_IN_NEW,
                                  on_click=lambda _: self.page.launch_url(settings.URL_ML_VENCEN_HOY)),
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.START)
        cuerpo = ft.Column([
            encabezado,
            ft.Container(ft.Column([self.fila_pasos, ft.Row([ft.Icon(ft.Icons.ARROW_FORWARD, size=18,
                                                                     color=ft.Colors.PRIMARY), self.siguiente])],
                                   spacing=10),
                         padding=14, border_radius=14,
                         bgcolor=ft.Colors.with_opacity(0.08, ft.Colors.PRIMARY)),
            tarjeta(ft.Column([
                seccion("Venta"),
                ft.Row([self.numero, ft.Column([ft.Text("Vence el reclamo", size=12), self.btn_vence], spacing=2),
                        self.deposito], wrap=True, spacing=16, vertical_alignment=ft.CrossAxisAlignment.START),
                ft.Row([self.motivo, self.codigo], wrap=True, spacing=16,
                       vertical_alignment=ft.CrossAxisAlignment.START),
                self.link,
                self.problema,
            ], spacing=14)),
            tarjeta(ft.Column([
                seccion("Clasificación, estado y fotos"),
                ft.Row([self.clasif, self.condicion], wrap=True, spacing=16,
                       vertical_alignment=ft.CrossAxisAlignment.START),
                self.descripcion,
                ft.Row([self.btn_fotos, self.txt_fotos], spacing=12),
                self.galeria,
            ], spacing=14)),
            tarjeta(ft.Column([self.reclamo, self.panel_reclamo], spacing=14)),
            self.progreso,
            ft.Row([self.btn_guardar, self.btn_limpiar] if not self.editando else
                   [self.btn_guardar, ft.TextButton("Cancelar", on_click=lambda _: self._terminar())]),
        ], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)
        return cuerpo

    # ------------------------------------------------------------ datos existentes

    def _cargar_existente(self) -> None:
        d = self.existente
        self.numero.value = d.get("numero_venta", "")
        self.clasif.value = d.get("clasificacion")
        self.condicion.value = d.get("condicion")
        self.motivo.value = d.get("motivo")
        self.deposito.value = d.get("deposito_origen") or "Podesta"
        self.codigo.value = d.get("codigo_producto", "")
        self.link.value = d.get("link_publicacion", "")
        self.problema.value = d.get("problema_comprador", "")
        self.descripcion.value = d.get("descripcion", "")
        self.reclamo.value = bool(d.get("reclamo", True))
        self.mensaje.value = d.get("mensaje_reclamo", "")
        pct = d.get("porcentaje_sugerido")
        self.porcentaje.value = str(pct) if pct is not None else ""
        self.panel_reclamo.visible = self.reclamo.value
        try:
            self.fotos = self.app.devs.fotos(d["numero_venta"])
        except FirebaseError as e:
            self.app.avisar(f"No se pudieron leer las fotos: {e}", error=True)
        self._refrescar_galeria(actualizar=False)

    # ------------------------------------------------------------ eventos

    def _validar_numero(self, _=None) -> str | None:
        numero, error, aviso = validar_numero_venta(self.numero.value)
        self.numero.error_text = None
        self.numero.helper_text = aviso
        if error and self.numero.value:
            self.numero.error_text = error
        self._actualizar_pasos()
        return None if error else numero

    def _verificar_duplicado(self, _=None) -> None:
        if self.editando:
            return
        numero, error, _aviso = validar_numero_venta(self.numero.value)
        if error:
            return
        try:
            existe = self.app.devs.obtener(numero)
        except FirebaseError:
            return
        if existe and not self.guardada:
            self.numero.error_text = f"Esa venta ya está cargada ({settings.ESTADOS.get(existe.get('estado'), '')})."
            self.page.update()

    def _elegir_fecha(self, _) -> None:
        try:
            self.selector_fecha.value = dt.datetime.fromisoformat(self.vence)
        except ValueError:
            pass
        self.page.open(self.selector_fecha)

    def _fecha_elegida(self, e) -> None:
        if e.control.value:
            self.vence = e.control.value.date().isoformat()
            self._actualizar_fecha()
            self.page.update()

    def _actualizar_fecha(self) -> None:
        a, m, d = self.vence.split("-")
        hoy = self.vence == dt.date.today().isoformat()
        self.btn_vence.text = f"{d}/{m}/{a}" + ("  (hoy)" if hoy else "")

    def _clasif_cambio(self, _) -> None:
        sugerida = settings.CONDICION_SUGERIDA.get(self.clasif.value)
        sugeridas = set(settings.CONDICION_SUGERIDA.values())
        if sugerida and (not self.condicion.value or self.condicion.value in sugeridas):
            self.condicion.value = sugerida
        if not self.editando:
            self.reclamo.value = self.clasif.value != "N"
            self.panel_reclamo.visible = self.reclamo.value
        self._actualizar_pasos()

    def _reclamo_cambio(self, _) -> None:
        self.panel_reclamo.visible = self.reclamo.value
        self._actualizar_pasos()

    def _pedir_fotos(self, _) -> None:
        self.app.selector_fotos.on_result = self._fotos_elegidas
        self.app.selector_fotos.pick_files(dialog_title="Elegir fotos de la devolución", allow_multiple=True,
                                           file_type=ft.FilePickerFileType.IMAGE)

    def _fotos_elegidas(self, e: ft.FilePickerResultEvent) -> None:
        if not e.files:
            return
        lugar = settings.FOTOS_MAX_POR_DEVOLUCION - len(self.fotos)
        if lugar <= 0:
            self.app.avisar(f"Máximo {settings.FOTOS_MAX_POR_DEVOLUCION} fotos por devolución.", error=True)
            return
        self.txt_fotos.value = "Procesando fotos…"
        self.page.update()
        errores = 0
        for f in e.files[:lugar]:
            try:
                self.fotos.append(comprimir(f.path))
            except Exception:  # noqa: BLE001
                errores += 1
        self.fotos_cambiaron = True
        if len(e.files) > lugar:
            self.app.avisar(f"Se agregaron {lugar}; el máximo es {settings.FOTOS_MAX_POR_DEVOLUCION}.")
        if errores:
            self.app.avisar(f"{errores} archivo(s) no se pudieron abrir como imagen.", error=True)
        self._refrescar_galeria()

    def _quitar_foto(self, indice: int) -> None:
        del self.fotos[indice]
        self.fotos_cambiaron = True
        self._refrescar_galeria()

    def _refrescar_galeria(self, actualizar: bool = True) -> None:
        self.galeria.controls = []
        for i, data in enumerate(self.fotos):
            self.galeria.controls.append(ft.Stack([
                ft.Image(src_base64=miniatura_b64(data), width=150, height=150, fit=ft.ImageFit.COVER,
                         border_radius=ft.border_radius.all(10)),
                ft.Container(ft.IconButton(ft.Icons.CLOSE, icon_size=16, tooltip="Quitar",
                                           on_click=lambda _, i=i: self._quitar_foto(i),
                                           style=ft.ButtonStyle(bgcolor=ft.Colors.with_opacity(0.75, ft.Colors.BLACK),
                                                                color=ft.Colors.WHITE)),
                             right=4, top=4),
            ], width=150, height=150))
        n = len(self.fotos)
        self.txt_fotos.value = f"{n} foto(s) — máximo {settings.FOTOS_MAX_POR_DEVOLUCION}" if n else "Sin fotos"
        self._actualizar_pasos(actualizar)

    # ------------------------------------------------------------ armado y guardado

    def _recolectar(self, exigir_fotos: bool) -> dict | None:
        numero, error, _ = validar_numero_venta(self.numero.value)
        faltan = []
        if error:
            faltan.append("número de venta")
        if not self.clasif.value:
            faltan.append("clasificación")
        if not self.condicion.value:
            faltan.append("condición")
        if not self.motivo.value:
            faltan.append("motivo")
        if not (self.descripcion.value or "").strip():
            faltan.append("estado en que llegó")
        if exigir_fotos and not self.fotos:
            faltan.append("al menos una foto")
        if faltan:
            self.app.avisar("Falta completar: " + ", ".join(faltan) + ".", error=True)
            return None
        pct = int(self.porcentaje.value) if (self.porcentaje.value or "").isdigit() else None
        if pct is not None and pct > 100:
            self.app.avisar("El porcentaje no puede superar 100.", error=True)
            return None
        mensaje = (self.mensaje.value or "").strip()
        reclamo = bool(self.reclamo.value)
        if not reclamo:
            estado = "sin_reclamo"
        elif mensaje:
            estado = "reclamo_armado"
        else:
            estado = "cargada"
        if self.editando and self.existente.get("estado") not in settings.ESTADOS_EDITABLES_CARGA:
            estado = self.existente.get("estado")  # el admin ya avanzó el estado
        return {
            "numero_venta": numero,
            "fecha_vencimiento": self.vence,
            "clasificacion": self.clasif.value,
            "condicion": self.condicion.value,
            "motivo": self.motivo.value,
            "deposito_origen": self.deposito.value or "Podesta",
            "codigo_producto": (self.codigo.value or "").strip(),
            "link_publicacion": (self.link.value or "").strip(),
            "problema_comprador": (self.problema.value or "").strip(),
            "descripcion": (self.descripcion.value or "").strip(),
            "reclamo": reclamo,
            "mensaje_reclamo": mensaje if reclamo else "",
            "porcentaje_sugerido": pct if reclamo else None,
            "estado": estado,
        }

    def _ocupado(self, si: bool) -> None:
        self.progreso.visible = si
        for b in (self.btn_guardar, self.btn_armar, self.btn_fotos):
            b.disabled = si
        self.page.update()

    def _persistir(self, datos: dict) -> bool:
        try:
            if self.guardada:
                self.app.devs.actualizar(datos["numero_venta"], datos)
                if self.fotos_cambiaron:
                    self.app.devs.reemplazar_fotos(datos["numero_venta"], self.fotos, self.cant_fotos_original)
                    self.app.devs.actualizar(datos["numero_venta"], {"fotos": len(self.fotos)})
                    self.cant_fotos_original = len(self.fotos)
            else:
                self.app.devs.crear(datos, self.fotos, self.app.usuario)
                self.guardada = True
                self.cant_fotos_original = len(self.fotos)
                self.numero.read_only = True
            self.fotos_cambiaron = False
            return True
        except FirebaseError as e:
            self.app.manejar_error(e)
            return False

    def _armar_reclamo(self, _) -> None:
        datos = self._recolectar(exigir_fotos=True)
        if not datos:
            return
        self._ocupado(True)
        try:
            if not self._persistir(datos):
                return
            prompt = armar_prompt(datos, len(self.fotos))
            self.page.set_clipboard(prompt)
            carpeta = local.guardar_fotos(datos["numero_venta"], self.fotos)
            local.abrir_carpeta(carpeta)
            self.page.launch_url(self.app.config.get("claude_project_url") or URL_CLAUDE_POR_DEFECTO)
            self.app.avisar("Datos copiados. Péguelos en Claude con Ctrl+V y arrastre las fotos de la carpeta.")
        finally:
            self._ocupado(False)

    def _pegar_respuesta(self, _) -> None:
        texto = self.page.get_clipboard() or ""
        if not texto.strip():
            self.app.avisar("El portapapeles está vacío. Copie la respuesta de Claude primero.", error=True)
            return
        mensaje, pct = leer_respuesta_claude(texto)
        self.mensaje.value = mensaje[: settings.LIMITE_MENSAJE]
        if pct is not None:
            self.porcentaje.value = str(pct)
        if len(mensaje) > settings.LIMITE_MENSAJE:
            self.app.avisar(f"El mensaje tenía {len(mensaje)} caracteres y se recortó a "
                            f"{settings.LIMITE_MENSAJE}. Revíselo.", error=True)
        self._actualizar_pasos()

    def _guardar(self, _) -> None:
        datos = self._recolectar(exigir_fotos=bool(self.reclamo.value))
        if not datos:
            return
        self._ocupado(True)
        ok = self._persistir(datos)
        self._ocupado(False)
        if not ok:
            return
        self.app.avisar(f"Venta {datos['numero_venta']} guardada ({settings.ESTADOS[datos['estado']]}).")
        if self.editando:
            self._terminar()
        else:
            self._limpiar()

    def _terminar(self) -> None:
        if self.al_terminar:
            self.al_terminar()

    def _limpiar(self, _=None) -> None:
        self.guardada = False
        self.fotos, self.fotos_cambiaron, self.cant_fotos_original = [], False, 0
        for c in (self.numero, self.codigo, self.link, self.problema, self.descripcion, self.mensaje,
                  self.porcentaje):
            c.value = ""
            c.error_text = None
        self.numero.helper_text = None
        self.numero.read_only = False
        self.clasif.value = None
        self.condicion.value = None
        self.motivo.value = None
        self.deposito.value = "Podesta"
        self.reclamo.value = True
        self.panel_reclamo.visible = True
        self.vence = dt.date.today().isoformat()
        self._actualizar_fecha()
        self._refrescar_galeria()

    # ------------------------------------------------------------ guía de pasos

    def _actualizar_pasos(self, actualizar: bool = True) -> None:
        _n, error_num, _ = validar_numero_venta(self.numero.value)
        reclamo = bool(self.reclamo.value)
        pasos = [
            ("Número de venta", not error_num, "Pegue el número de venta copiado de Mercado Libre."),
            ("Motivo", bool(self.motivo.value), "Elija el motivo de la devolución que figura en ML."),
            ("Clasificación", bool(self.clasif.value), "Elija la clasificación del producto."),
            ("Condición", bool(self.condicion.value), "Revise o elija la condición del producto."),
            ("Estado", bool((self.descripcion.value or "").strip()),
             "Escriba en qué estado llegó el producto."),
            ("Fotos", bool(self.fotos) or not reclamo, "Toque \"Agregar fotos\" y elija las fotos."),
        ]
        if reclamo:
            pasos.append(("Reclamo", bool((self.mensaje.value or "").strip()),
                          "Toque \"Armar reclamo\" y después \"Pegar respuesta de Claude\"."))
        self.fila_pasos.controls = []
        for i, (nombre, ok, _ayuda) in enumerate(pasos, 1):
            color = ft.Colors.GREEN_700 if ok else ft.Colors.OUTLINE
            self.fila_pasos.controls.append(ft.Container(
                ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE if ok else ft.Icons.RADIO_BUTTON_UNCHECKED,
                                size=18, color=color),
                        ft.Text(f"{i}. {nombre}", size=13, weight=ft.FontWeight.W_600,
                                color=ft.Colors.GREEN_800 if ok else ft.Colors.ON_SURFACE_VARIANT)],
                       spacing=6, tight=True),
                padding=ft.padding.symmetric(6, 12), border_radius=20,
                bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.GREEN) if ok else ft.Colors.SURFACE,
                border=ft.border.all(1, color)))
        pendiente = next((ayuda for _nom, ok, ayuda in pasos if not ok), None)
        self.siguiente.value = (f"Siguiente: {pendiente}" if pendiente
                                else "Todo listo. Toque \"Guardar\".")
        self.siguiente.color = ft.Colors.PRIMARY if pendiente else ft.Colors.GREEN_800
        if actualizar:
            try:
                self.page.update()
            except Exception:  # noqa: BLE001 - todavía no está en pantalla
                pass

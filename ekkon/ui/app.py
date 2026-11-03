"""Controlador principal: sesión, permisos y navegación."""
from __future__ import annotations

import threading
import time

import flet as ft

from .. import local, settings
from ..datos import ConfigApp, Devoluciones, Usuarios
from ..firebase import Auth, FirebaseError, Firestore, Sesion
from ..version import VERSION, comparar
from .comun import COLOR_SEMILLA, tarjeta

INTERVALO_CONTROL = 300  # segundos entre controles de usuario activo


class App:
    def __init__(self, page: ft.Page):
        self.page = page
        self.auth = Auth()
        self.sesion: Sesion | None = None
        self.usuario: dict | None = None
        self.config: dict = {}
        self.fs = Firestore(self.token)
        self.devs = Devoluciones(self.fs)
        self.usuarios = Usuarios(self.fs)
        self.cfg = ConfigApp(self.fs)
        self.selector_fotos = ft.FilePicker()
        self._vigilante: threading.Thread | None = None
        self._seccion_actual = 0

    # ------------------------------------------------------------ sesión

    @property
    def es_admin(self) -> bool:
        return bool(self.usuario and self.usuario.get("rol") == "admin")

    def token(self) -> str:
        if not self.sesion:
            raise FirebaseError("TOKEN_EXPIRED")
        if not self.sesion.vigente():
            self.sesion = self.auth.renovar(self.sesion.refresh_token, self.sesion.email)
            if local.leer_sesion():
                local.guardar_sesion(self.sesion.email, self.sesion.refresh_token)
        return self.sesion.id_token

    def iniciar(self) -> None:
        p = self.page
        p.title = f"{settings.APP_NAME} {VERSION}"
        p.theme = ft.Theme(color_scheme_seed=COLOR_SEMILLA, use_material3=True)
        p.dark_theme = ft.Theme(color_scheme_seed=COLOR_SEMILLA, use_material3=True)
        p.theme_mode = ft.ThemeMode.LIGHT
        p.padding = 0
        p.window.width = 1320
        p.window.height = 860
        p.window.min_width = 1050
        p.window.min_height = 680
        p.overlay.append(self.selector_fotos)

        if not settings.FIREBASE_API_KEY:
            self._pantalla_mensaje("Falta configurar Firebase",
                                   "Esta versión no tiene cargada la API key del proyecto. "
                                   "Descargue la versión publicada más reciente.")
            return

        guardada = local.leer_sesion()
        if guardada:
            self._cargando("Recuperando la sesión…")
            try:
                ses = self.auth.renovar(guardada["refresh_token"], guardada.get("email", ""))
                self.entrar(ses, recordar=True)
                return
            except FirebaseError:
                local.borrar_sesion()
        self.mostrar_login()

    def entrar(self, sesion: Sesion, recordar: bool) -> None:
        self.sesion = sesion
        try:
            perfil = self.usuarios.obtener(sesion.uid)
        except FirebaseError as e:
            perfil = None
            if not e.codigo.startswith("PERMISSION_DENIED"):
                self.sesion = None
                self.mostrar_login(str(e))
                return
        if not perfil:
            self._sin_perfil(sesion)
            return
        if not perfil.get("activo"):
            self.sesion = None
            local.borrar_sesion()
            self.mostrar_login("Su usuario está bloqueado. Consulte con el administrador.")
            return
        perfil["_id"] = sesion.uid
        perfil.setdefault("email", sesion.email)
        self.usuario = perfil
        if recordar:
            local.guardar_sesion(sesion.email or perfil.get("email", ""), sesion.refresh_token)
        try:
            self.config = self.cfg.leer()
        except FirebaseError:
            self.config = {}
        minima = self.config.get("version_minima")
        if minima and comparar(VERSION, minima) < 0:
            self._pantalla_mensaje(
                "Hay que actualizar el programa",
                f"Esta es la versión {VERSION} y la mínima permitida es {minima}. "
                "Descargue la versión nueva para continuar.",
                url=self.config.get("url_descarga"))
            return
        self.mostrar_shell()
        from . import tutorial
        if not tutorial.ya_visto(sesion.uid):
            tutorial.mostrar(self)
        ultima = self.config.get("ultima_version")
        if ultima and comparar(VERSION, ultima) < 0:
            self.avisar(f"Hay una versión nueva disponible ({ultima}).")
        self._iniciar_vigilante()

    def salir(self, mensaje: str | None = None) -> None:
        local.borrar_sesion()
        self.sesion = None
        self.usuario = None
        self.mostrar_login(mensaje)

    def _iniciar_vigilante(self) -> None:
        if self._vigilante and self._vigilante.is_alive():
            return

        def bucle():
            while self.usuario:
                time.sleep(INTERVALO_CONTROL)
                if not self.usuario:
                    return
                try:
                    perfil = self.usuarios.obtener(self.usuario["_id"])
                except FirebaseError as e:
                    if e.codigo.startswith("PERMISSION_DENIED"):
                        perfil = None
                    else:
                        continue
                if not perfil or not perfil.get("activo"):
                    self.salir("Su usuario fue bloqueado por el administrador.")
                    return
                self.usuario.update({"rol": perfil.get("rol"), "nombre": perfil.get("nombre")})

        self._vigilante = threading.Thread(target=bucle, daemon=True)
        self._vigilante.start()

    def manejar_error(self, e: Exception) -> None:
        if isinstance(e, FirebaseError) and e.codigo.startswith(("PERMISSION_DENIED", "TOKEN_EXPIRED",
                                                                 "INVALID_REFRESH_TOKEN")):
            try:
                perfil = self.usuarios.obtener(self.usuario["_id"]) if self.usuario else None
            except FirebaseError:
                perfil = None
            if not perfil or not perfil.get("activo"):
                self.salir("Su sesión se cerró: el usuario fue bloqueado o la sesión venció.")
                return
        self.avisar(str(e), error=True)

    # ------------------------------------------------------------ avisos

    def avisar(self, texto: str, error: bool = False) -> None:
        sb = ft.SnackBar(ft.Text(texto), bgcolor=ft.Colors.ERROR if error else None,
                         duration=6000 if error else 4000, show_close_icon=True)
        self.page.open(sb)

    def confirmar(self, titulo: str, texto: str, al_aceptar, texto_boton: str = "Aceptar") -> None:
        dlg = ft.AlertDialog(modal=True, title=ft.Text(titulo), content=ft.Text(texto))

        def ok(_):
            self.page.close(dlg)
            al_aceptar()

        dlg.actions = [ft.TextButton("Cancelar", on_click=lambda _: self.page.close(dlg)),
                       ft.FilledButton(texto_boton, on_click=ok)]
        self.page.open(dlg)

    # ------------------------------------------------------------ pantallas

    def _set(self, control: ft.Control) -> None:
        self.page.controls.clear()
        self.page.add(control)
        self.page.update()

    def _centrado(self, contenido: ft.Control) -> ft.Control:
        return ft.Container(
            ft.Container(contenido, width=430),
            alignment=ft.alignment.center, expand=True,
            gradient=ft.LinearGradient(
                begin=ft.alignment.top_left, end=ft.alignment.bottom_right,
                colors=[ft.Colors.with_opacity(0.10, COLOR_SEMILLA), ft.Colors.with_opacity(0.02, COLOR_SEMILLA)]),
        )

    def _marca(self) -> ft.Control:
        return ft.Row([
            ft.Container(ft.Icon(ft.Icons.ASSIGNMENT_RETURN, color=ft.Colors.ON_PRIMARY, size=26),
                         bgcolor=ft.Colors.PRIMARY, border_radius=12, padding=10),
            ft.Column([ft.Text("Ekkon", size=22, weight=ft.FontWeight.W_800),
                       ft.Text("Devoluciones Mercado Libre", size=12, color=ft.Colors.ON_SURFACE_VARIANT)],
                      spacing=0),
        ], spacing=12)

    def _cargando(self, texto: str) -> None:
        self._set(self._centrado(ft.Column([ft.ProgressRing(), ft.Text(texto)],
                                           horizontal_alignment=ft.CrossAxisAlignment.CENTER)))

    def _pantalla_mensaje(self, titulo: str, texto: str, url: str | None = None) -> None:
        acciones: list[ft.Control] = []
        if url:
            acciones.append(ft.FilledButton("Descargar versión nueva", icon=ft.Icons.DOWNLOAD,
                                            on_click=lambda _: self.page.launch_url(url)))
        if self.sesion:
            acciones.append(ft.TextButton("Cerrar sesión", on_click=lambda _: self.salir()))
        self._set(self._centrado(tarjeta(ft.Column(
            [self._marca(), ft.Divider(), ft.Text(titulo, size=18, weight=ft.FontWeight.W_600),
             ft.Text(texto), ft.Row(acciones)], spacing=14), padding=28)))

    def _sin_perfil(self, sesion: Sesion) -> None:
        uid = sesion.uid
        self._pantalla_mensaje(
            "Usuario sin perfil asignado",
            "La cuenta existe, pero todavía no tiene un perfil habilitado. Pídale al administrador que lo "
            f"habilite.\n\nIdentificador de la cuenta (UID):\n{uid}")
        self.page.set_clipboard(uid)
        self.avisar("Se copió el UID al portapapeles.")

    def mostrar_login(self, mensaje: str | None = None) -> None:
        guardada = local.leer_sesion() or {}
        email = ft.TextField(label="Correo", value=guardada.get("email", ""), autofocus=True,
                             prefix_icon=ft.Icons.MAIL_OUTLINE, keyboard_type=ft.KeyboardType.EMAIL)
        clave = ft.TextField(label="Contraseña", password=True, can_reveal_password=True,
                             prefix_icon=ft.Icons.LOCK_OUTLINE)
        recordar = ft.Checkbox(label="Mantener la sesión iniciada en esta PC", value=True)
        error = ft.Text(mensaje or "", color=ft.Colors.ERROR, visible=bool(mensaje))
        boton = ft.FilledButton("Ingresar", icon=ft.Icons.LOGIN, height=46, expand=True)
        progreso = ft.ProgressBar(visible=False)

        def ingresar(_=None):
            if not email.value or not clave.value:
                error.value, error.visible = "Complete correo y contraseña.", True
                self.page.update()
                return
            boton.disabled, progreso.visible, error.visible = True, True, False
            self.page.update()
            try:
                ses = self.auth.iniciar_sesion(email.value, clave.value)
            except FirebaseError as e:
                boton.disabled, progreso.visible = False, False
                error.value, error.visible = str(e), True
                self.page.update()
                return
            self.entrar(ses, recordar.value)

        def olvide(_):
            if not email.value:
                error.value, error.visible = "Escriba su correo para enviarle el enlace.", True
                self.page.update()
                return
            try:
                self.auth.enviar_reset(email.value)
                self.avisar("Le enviamos un correo para restablecer la contraseña.")
            except FirebaseError as e:
                self.avisar(str(e), error=True)

        boton.on_click = ingresar
        clave.on_submit = ingresar
        email.on_submit = lambda _: clave.focus()

        self._set(self._centrado(tarjeta(ft.Column([
            self._marca(),
            ft.Container(height=6),
            ft.Text("Iniciar sesión", size=20, weight=ft.FontWeight.W_600),
            email, clave, recordar, error,
            ft.Row([boton]), progreso,
            ft.TextButton("Olvidé mi contraseña", on_click=olvide),
            ft.Text(f"Versión {VERSION}", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
        ], spacing=14, tight=True), padding=30)))

    # ------------------------------------------------------------ estructura principal

    def _secciones(self):
        from .carga import VistaCarga
        from .lista import VistaLista
        from .usuarios import VistaUsuarios
        from .ajustes import VistaAjustes

        secciones = [
            ("Cargar", ft.Icons.ADD_A_PHOTO_OUTLINED, ft.Icons.ADD_A_PHOTO, lambda: VistaCarga(self).control()),
            ("Devoluciones", ft.Icons.LIST_ALT_OUTLINED, ft.Icons.LIST_ALT,
             lambda: VistaLista(self).control()),
        ]
        if self.es_admin:
            secciones += [
                ("Pendientes", ft.Icons.HOURGLASS_EMPTY, ft.Icons.HOURGLASS_FULL,
                 lambda: VistaLista(self, modo="pendientes").control()),
                ("Usuarios", ft.Icons.PEOPLE_OUTLINE, ft.Icons.PEOPLE, lambda: VistaUsuarios(self).control()),
                ("Ajustes", ft.Icons.SETTINGS_OUTLINED, ft.Icons.SETTINGS, lambda: VistaAjustes(self).control()),
            ]
        return secciones

    def mostrar_shell(self, indice: int = 0) -> None:
        secciones = self._secciones()
        self._seccion_actual = min(indice, len(secciones) - 1)
        contenido = ft.Container(expand=True, padding=ft.padding.symmetric(20, 28), alignment=ft.alignment.top_left)

        def ir(i: int):
            self._seccion_actual = i
            contenido.content = ft.Container(ft.ProgressRing(), alignment=ft.alignment.center)
            self.page.update()
            try:
                contenido.content = secciones[i][3]()
            except Exception as e:  # noqa: BLE001
                contenido.content = ft.Text(f"No se pudo abrir la sección: {e}", color=ft.Colors.ERROR)
            self.page.update()

        nombre = (self.usuario or {}).get("nombre") or (self.usuario or {}).get("email", "")
        rail = ft.NavigationRail(
            selected_index=self._seccion_actual,
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=96,
            group_alignment=-0.85,
            leading=ft.Container(
                ft.Container(ft.Icon(ft.Icons.ASSIGNMENT_RETURN, color=ft.Colors.ON_PRIMARY, size=24),
                             bgcolor=ft.Colors.PRIMARY, border_radius=12, padding=10),
                padding=ft.padding.only(top=18, bottom=10)),
            trailing=ft.Container(ft.Column([
                ft.CircleAvatar(content=ft.Text((nombre[:1] or "?").upper()), radius=18,
                                tooltip=f"{nombre}\n{settings.ROLES.get(self.usuario.get('rol'), '')}"),
                ft.IconButton(ft.Icons.HELP_OUTLINE, tooltip="Ver el tutorial",
                              on_click=lambda _: self._abrir_tutorial()),
                ft.IconButton(ft.Icons.LOGOUT, tooltip="Cerrar sesión",
                              on_click=lambda _: self.confirmar("Cerrar sesión", "¿Desea cerrar la sesión?",
                                                                self.salir, "Cerrar sesión")),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
                padding=ft.padding.only(top=30)),
            destinations=[ft.NavigationRailDestination(icon=s[1], selected_icon=s[2], label=s[0])
                          for s in secciones],
            on_change=lambda e: ir(e.control.selected_index),
        )
        self._set(ft.Row([rail, ft.VerticalDivider(width=1), contenido], expand=True, spacing=0))
        ir(self._seccion_actual)

    def _abrir_tutorial(self) -> None:
        from . import tutorial
        tutorial.mostrar(self)

    def ir_a(self, indice: int) -> None:
        self.mostrar_shell(indice)


def main(page: ft.Page) -> None:
    App(page).iniciar()

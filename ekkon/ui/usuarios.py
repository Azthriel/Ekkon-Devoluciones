"""Administración de usuarios: alta, rol y bloqueo."""
from __future__ import annotations

import flet as ft

from .. import settings
from ..firebase import FirebaseError
from .comun import tarjeta, titulo


class VistaUsuarios:
    def __init__(self, app):
        self.app = app
        self.page: ft.Page = app.page
        self.lista = ft.Column(spacing=8)

    def control(self) -> ft.Control:
        self.recargar(actualizar=False)
        return ft.Column([
            ft.Row([titulo("Usuarios", "Un usuario bloqueado no puede ingresar ni leer datos, "
                                       "aunque tenga una versión vieja del programa."),
                    ft.FilledButton("Nuevo usuario", icon=ft.Icons.PERSON_ADD, on_click=self._nuevo)],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            self.lista,
        ], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

    def recargar(self, actualizar: bool = True) -> None:
        try:
            usuarios = self.app.usuarios.listar()
        except FirebaseError as e:
            self.app.manejar_error(e)
            return
        self.lista.controls = [self._fila(u) for u in usuarios]
        if actualizar:
            self.page.update()

    def _fila(self, u: dict) -> ft.Control:
        propio = u["_id"] == self.app.usuario["_id"]
        rol = ft.Dropdown(value=u.get("rol", "carga"), width=230, dense=True, disabled=propio,
                          options=[ft.dropdown.Option(k, v) for k, v in settings.ROLES.items()],
                          on_change=lambda e, u=u: self._guardar(u, {"rol": e.control.value}))
        activo = ft.Switch(value=bool(u.get("activo")), disabled=propio,
                           label="Activo" if u.get("activo") else "Bloqueado",
                           on_change=lambda e, u=u: self._guardar(u, {"activo": e.control.value}))
        nombre = u.get("nombre") or u.get("email", "")
        return tarjeta(ft.Row([
            ft.CircleAvatar(content=ft.Text((nombre[:1] or "?").upper())),
            ft.Column([ft.Text(nombre + ("  (usted)" if propio else ""), weight=ft.FontWeight.W_600),
                       ft.Text(u.get("email", ""), size=12, color=ft.Colors.ON_SURFACE_VARIANT)],
                      spacing=2, expand=True),
            rol, activo,
            ft.IconButton(ft.Icons.LOCK_RESET, tooltip="Enviar correo para cambiar la contraseña",
                          on_click=lambda _, u=u: self._reset(u)),
        ], spacing=16), padding=14)

    def _guardar(self, u: dict, campos: dict) -> None:
        try:
            self.app.usuarios.actualizar(u["_id"], campos)
            self.app.avisar("Usuario actualizado.")
        except FirebaseError as e:
            self.app.manejar_error(e)
        self.recargar()

    def _reset(self, u: dict) -> None:
        try:
            self.app.auth.enviar_reset(u.get("email", ""))
            self.app.avisar(f"Se envió el correo a {u.get('email')}.")
        except FirebaseError as e:
            self.app.avisar(str(e), error=True)

    def _nuevo(self, _) -> None:
        nombre = ft.TextField(label="Nombre", autofocus=True)
        email = ft.TextField(label="Correo", keyboard_type=ft.KeyboardType.EMAIL)
        clave = ft.TextField(label="Contraseña inicial", password=True, can_reveal_password=True,
                             helper_text="Mínimo 6 caracteres. El usuario puede cambiarla con \"Olvidé mi contraseña\".")
        rol = ft.Dropdown(label="Perfil", value="carga",
                          options=[ft.dropdown.Option(k, v) for k, v in settings.ROLES.items()])
        error = ft.Text("", color=ft.Colors.ERROR, visible=False)
        dlg = ft.AlertDialog(modal=True, title=ft.Text("Nuevo usuario"),
                             content=ft.Container(ft.Column([nombre, email, clave, rol, error], tight=True,
                                                            spacing=12), width=420))

        def crear(_):
            if not (nombre.value and email.value and clave.value):
                error.value, error.visible = "Complete todos los campos.", True
                self.page.update()
                return
            try:
                uid = self.app.auth.crear_usuario(email.value, clave.value)
                self.app.usuarios.crear_perfil(uid, email.value, nombre.value, rol.value)
            except FirebaseError as e:
                error.value, error.visible = str(e), True
                self.page.update()
                return
            self.page.close(dlg)
            self.app.avisar(f"Usuario {email.value} creado.")
            self.recargar()

        dlg.actions = [ft.TextButton("Cancelar", on_click=lambda _: self.page.close(dlg)),
                       ft.FilledButton("Crear", on_click=crear)]
        self.page.open(dlg)

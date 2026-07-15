from __future__ import annotations

import threading
import traceback
import webbrowser

import flet as ft

from config import SUPABASE_OAUTH_REDIRECT_URL
from services.auth_service import (
    exchange_code_for_session,
    get_current_user,
    get_oauth_url,
    sign_out_local_session,
    wait_for_oauth_callback,
)
from services.response_utils import pretty, safe_get, to_dict
from services.usuario_service import (
    UsuarioContextoError,
    buscar_usuario_eventplus_por_auth_uuid,
    buscar_usuario_eventplus_por_email,
    cargar_contexto_usuario,
    formato_usuario_eventplus,
)


def formato_resumen_contexto(contexto: dict) -> str:
    cuenta_actual = safe_get(contexto, "cuenta_actual") or {}
    evento_actual = safe_get(contexto, "evento_actual") or {}
    cuentas_permitidas = safe_get(contexto, "cuentas_permitidas", []) or []
    eventos_permitidos = safe_get(contexto, "eventos_permitidos", []) or []

    cuenta_texto = safe_get(cuenta_actual, "nombre_cuenta", "Sin cuenta actual")
    evento_texto = safe_get(evento_actual, "nombre_evento", "Sin evento actual")
    fase_evento = safe_get(evento_actual, "fase_evento")
    if fase_evento:
        evento_texto = f"{evento_texto} ({fase_evento})"

    return "\n".join(
        [
            "CONTEXTO DE USUARIO CARGADO",
            "",
            f"Usuario: {safe_get(contexto, 'usr_nombre_usuario')}",
            f"Email: {safe_get(contexto, 'usr_email')}",
            f"Rol global calculado: {safe_get(contexto, 'rol_global_calculado')}",
            f"Cuenta actual: {cuenta_texto}",
            f"Evento actual: {evento_texto}",
            f"Cantidad de cuentas permitidas: {len(cuentas_permitidas)}",
            f"Cantidad de eventos permitidos: {len(eventos_permitidos)}",
            f"Puede registrar llegadas: {safe_get(contexto, 'puede_registrar_llegadas')}",
            f"Puede administrar usuarios: {safe_get(contexto, 'puede_administrar_usuarios')}",
        ]
    )


def build_login_view(page: ft.Page, initial_message: str | None = None) -> None:
    status = ft.Text(initial_message or "Listo para iniciar prueba.", size=16, selectable=True)

    result_box = ft.TextField(
        label="Resultado de la prueba",
        multiline=True,
        min_lines=22,
        max_lines=30,
        read_only=True,
        value="",
    )

    login_button = ft.ElevatedButton(
        "Iniciar sesion con Google",
        icon=ft.Icons.LOGIN,
    )

    logout_button = ft.OutlinedButton(
        "Cerrar sesion local",
        icon=ft.Icons.LOGOUT,
        visible=False,
    )

    def set_status(message: str) -> None:
        status.value = message
        page.update()

    def set_result(message: str) -> None:
        result_box.value = message
        page.update()

    def run_login_flow() -> None:
        try:
            login_button.disabled = True
            set_status("Solicitando URL OAuth a Supabase...")

            oauth_url = get_oauth_url()

            set_status(
                "Se abrira el navegador para iniciar sesion con Google. "
                "Despues del login, vuelve a esta ventana."
            )

            webbrowser.open(oauth_url)

            set_status(f"Esperando callback OAuth en {SUPABASE_OAUTH_REDIRECT_URL} ...")

            callback_result = wait_for_oauth_callback(timeout_seconds=180)

            if safe_get(callback_result, "error"):
                raise RuntimeError(
                    f"OAuth error: {safe_get(callback_result, 'error')} - "
                    f"{safe_get(callback_result, 'error_description')}"
                )

            code = safe_get(callback_result, "code")
            if not code:
                raise RuntimeError(
                    "No se recibio el parametro 'code' en el callback.\n"
                    f"Callback recibido:\n{pretty(callback_result)}"
                )

            set_status("Callback recibido. Intercambiando code por sesion Supabase...")

            exchange_code_for_session(str(code))

            user = get_current_user()
            if not user:
                raise RuntimeError("No se pudo obtener el usuario autenticado con supabase.auth.get_user().")

            auth_user_id = str(safe_get(user, "id", ""))
            email = str(safe_get(user, "email", ""))

            if not auth_user_id:
                raise RuntimeError(
                    "Supabase Auth no devolvio user.id.\n"
                    f"User recibido:\n{pretty(to_dict(user) or str(user))}"
                )

            set_status("Login exitoso. Consultando evp_usr_usuario para validar trigger...")

            usuario_eventplus = buscar_usuario_eventplus_por_auth_uuid(auth_user_id)

            diagnostico = [
                "LOGIN SUPABASE AUTH EXITOSO",
                "",
                f"auth.users.id: {auth_user_id}",
                f"auth.users.email: {email}",
                "",
                "VALIDACION EVENTPLUS POR usr_usuario_auth_uuid",
                formato_usuario_eventplus(usuario_eventplus),
            ]

            if not usuario_eventplus and email:
                usuario_por_email = buscar_usuario_eventplus_por_email(email)
                diagnostico.extend(
                    [
                        "",
                        "BUSQUEDA DE APOYO POR EMAIL",
                        formato_usuario_eventplus(usuario_por_email),
                    ]
                )

                if usuario_por_email and not safe_get(usuario_por_email, "usr_usuario_auth_uuid"):
                    diagnostico.extend(
                        [
                            "",
                            "DIAGNOSTICO:",
                            "El usuario existe por email, pero usr_usuario_auth_uuid sigue vacio.",
                            "Eso sugiere que el trigger de auth.users no actualizo evp_usr_usuario.",
                            "Revisa la funcion/trigger de vinculacion y que el email coincida.",
                        ]
                    )
                elif not usuario_por_email:
                    diagnostico.extend(
                        [
                            "",
                            "DIAGNOSTICO:",
                            "No existe usuario preregistrado con este email en evp_usr_usuario.",
                            "Debes preregistrar el usuario antes de probar la vinculacion.",
                        ]
                    )

            if usuario_eventplus and safe_get(usuario_eventplus, "usr_usuario_auth_uuid") == auth_user_id:
                diagnostico.extend(
                    [
                        "",
                        "RESULTADO:",
                        "Prueba exitosa. El usuario autenticado fue vinculado correctamente con evp_usr_usuario.",
                    ]
                )
            elif usuario_eventplus:
                diagnostico.extend(
                    [
                        "",
                        "RESULTADO:",
                        "Login exitoso, pero la vinculacion no coincide exactamente. Revisa usr_usuario_auth_uuid.",
                    ]
                )

            set_status("Cargando contexto del usuario EventPlus...")
            try:
                contexto_usuario = cargar_contexto_usuario(auth_user_id)
                page.session.store.set("usuario_contexto", contexto_usuario)
                diagnostico.extend(["", formato_resumen_contexto(contexto_usuario)])
                print("[LOGIN] Contexto cargado")
            except UsuarioContextoError as ex:
                page.session.store.set("diagnostico_login", "\n".join(diagnostico))
                set_result(
                    "No se pudo cargar el contexto operativo.\n\n"
                    f"{ex}\n\n"
                    "Contacta al administrador si el problema continua."
                )
                set_status("Acceso no autorizado o contexto incompleto.")
                logout_button.visible = True
                return

            page.session.store.set("diagnostico_login", "\n".join(diagnostico))
            set_status("Acceso concedido. Abriendo Dashboard...")
            try:
                print("[HOME] Construyendo Home")
                from views.home_view import build_home_view

                home_control = build_home_view(
                    page=page,
                    contexto_usuario=contexto_usuario,
                    supabase=None,
                )
                print("[HOME] Tipo devuelto:", type(home_control))

                if home_control is None:
                    raise RuntimeError(
                        "build_home_view devolvio None; se esperaba un control Flet."
                    )

                print("[HOME] Limpiando login")
                page.clean()
                print("[HOME] Agregando Home")
                page.add(home_control)
                page.update()
                start_eventos = None
                if isinstance(home_control.data, dict):
                    start_eventos = home_control.data.get("start_eventos")
                if callable(start_eventos):
                    start_eventos()
                print("[HOME] Home mostrado")
            except Exception:
                traceback.print_exc()
                page.clean()
                build_login_view(
                    page,
                    initial_message="No fue posible abrir la pantalla principal.",
                )
                page.update()

        except Exception as ex:
            set_status("La prueba fallo.")
            page.session.store.set(
                "diagnostico_login",
                "ERROR DURANTE LA PRUEBA\n\n"
                f"{type(ex).__name__}: {ex}\n\n"
                "TRACEBACK COMPLETO:\n"
                f"{traceback.format_exc()}",
            )
            set_result(
                "No pudimos completar el inicio de sesion.\n\n"
                "Puntos a revisar:\n"
                "1. Que SUPABASE_URL y SUPABASE_PUBLISHABLE_KEY esten correctos en .env.\n"
                "2. Que Google este habilitado en Authentication > Providers.\n"
                "3. Que Supabase tenga esta Redirect URL permitida:\n"
                f"   {SUPABASE_OAUTH_REDIRECT_URL}\n"
                "4. Que el usuario este preregistrado en evp_usr_usuario con el mismo email.\n"
                "5. Que el trigger sobre auth.users exista y no tenga errores.\n"
                "6. Que ninguna otra aplicacion este usando el puerto 8765.\n"
            )
        finally:
            login_button.disabled = False
            page.update()

    def login_click(e: ft.ControlEvent) -> None:
        threading.Thread(target=run_login_flow, daemon=True).start()

    def logout_click(e: ft.ControlEvent) -> None:
        try:
            sign_out_local_session()
        except Exception:
            pass

        logout_button.visible = False
        set_status("Sesion local cerrada.")
        set_result("")

    login_button.on_click = login_click
    logout_button.on_click = logout_click

    instructions = ft.Container(
        content=ft.Column(
            [
                ft.Image(
                    src="brand/EventPlus_logo_v2.1_stacked.png",
                    width=240,
                    fit=ft.BoxFit.CONTAIN,
                ),
                ft.Text(
                    "Prueba basica Google OAuth + Supabase Auth",
                    size=24,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Text(
                    "Antes de probar, preregistra en evp_usr_usuario el mismo email "
                    "de Google que usaras para iniciar sesion, con usr_estado='Preregistrado' "
                    "y usr_usuario_auth_uuid=NULL.",
                    size=14,
                ),
                ft.Text(
                    f"Redirect URL usada por esta prueba: {SUPABASE_OAUTH_REDIRECT_URL}",
                    size=14,
                    selectable=True,
                ),
            ],
            spacing=8,
        ),
        padding=16,
        border_radius=12,
        bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.PRIMARY),
    )

    page.add(
        instructions,
        ft.Row([login_button, logout_button], spacing=12),
        status,
        result_box,
    )

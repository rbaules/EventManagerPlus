from __future__ import annotations

import asyncio
import threading
import traceback
import webbrowser
from typing import Any

import flet as ft

from config import (
    ANDROID_OAUTH_REDIRECT_URL,
    APP_VERSION,
    EVENTPLUS_WEB_OAUTH_ATTEMPT_TIMEOUT_SECONDS,
    EVENTPLUS_WEB_OAUTH_REDIRECT_URL,
    SUPABASE_OAUTH_REDIRECT_URL,
    get_oauth_redirect_url,
    is_checkin_mode,
)
from services.auth_service import (
    OAUTH_STRATEGY_ANDROID,
    OAUTH_STRATEGY_DESKTOP,
    OAUTH_STRATEGY_WEB,
    WEB_OAUTH_ATTEMPT_CANCELLED,
    WEB_OAUTH_ATTEMPT_CALLBACK_RECEIVED,
    WEB_OAUTH_ATTEMPT_COMPLETED,
    WEB_OAUTH_ATTEMPT_CONTEXT_BUILDING,
    WEB_OAUTH_ATTEMPT_EXPIRED,
    WEB_OAUTH_ATTEMPT_FAILED,
    WEB_OAUTH_ATTEMPT_HOME_BUILDING,
    WEB_OAUTH_ATTEMPT_SESSION_EXCHANGING,
    WebOAuthAttempt,
    detect_oauth_strategy,
    exchange_code_for_session,
    get_current_user,
    get_oauth_url,
    parse_oauth_callback_url,
    sign_out_local_session,
    start_web_oauth,
    wait_for_oauth_callback,
    web_oauth_error_message,
)
from services.response_utils import pretty, safe_get, to_dict
from services.session_service import (
    PageSessionController,
    SESSION_INVALID_MESSAGE,
)
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


async def wait_for_supabase_session(
    session_controller: PageSessionController,
    attempt: WebOAuthAttempt,
    *,
    retries: int = 5,
    delay_seconds: float = 0.15,
) -> bool:
    for index in range(retries):
        attempt.trace("supabase_session_check_start")
        session_present = await asyncio.to_thread(
            session_controller.has_supabase_session
        )
        attempt.trace(
            "supabase_session_present",
            session_present=session_present,
        )
        if session_present:
            return True
        if index + 1 < retries:
            await asyncio.sleep(delay_seconds)
    return False


def build_login_view(
    page: ft.Page,
    supabase: Any,
    initial_message: str | None = None,
    session_controller: PageSessionController | None = None,
) -> None:
    session_controller = session_controller or PageSessionController(page, supabase)
    page.navigation_bar = None
    print("[APP][INFO] Plataforma detectada:", page.platform)
    status = ft.Text(initial_message or "Listo para iniciar sesion.", size=14, selectable=True, text_align=ft.TextAlign.CENTER)
    progress = ft.ProgressRing(width=22, height=22, visible=False)

    result_box = ft.TextField(
        label="Diagnostico",
        multiline=True,
        min_lines=5,
        max_lines=8,
        read_only=True,
        value="",
        visible=False,
    )

    login_button = ft.Button(
        "Continuar con Google",
        icon=ft.Icons.LOGIN,
        height=48,
    )
    cancel_login_button = ft.TextButton(
        "Cancelar",
        icon=ft.Icons.CANCEL,
        visible=False,
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
        result_box.visible = bool(message)
        page.update()

    def set_loading(is_loading: bool) -> None:
        login_button.disabled = is_loading
        progress.visible = is_loading
        cancel_login_button.visible = False
        page.update()

    def set_web_attempt_ui(is_pending: bool, message: str) -> None:
        login_button.disabled = is_pending
        progress.visible = is_pending
        cancel_login_button.visible = is_pending
        status.value = message
        page.update()

    def set_web_callback_processing_ui() -> None:
        login_button.disabled = True
        progress.visible = True
        cancel_login_button.visible = False
        status.value = (
            "Autenticacion recibida. EventPlus esta preparando tu sesion..."
        )
        page.update()

    async def session_became_invalid(message: str) -> None:
        session_controller.logout(cancel_tasks=False)
        page.navigation_bar = None
        page.clean()
        build_login_view(
            page,
            supabase,
            initial_message=message or SESSION_INVALID_MESSAGE,
            session_controller=session_controller,
        )
        page.update()

    processed_callbacks: set[str] = set()

    def completar_login_con_code(
        code: str | None,
        fase_inicial: str = "obtener_sesion",
        attempt: WebOAuthAttempt | None = None,
    ) -> None:
        fase = fase_inicial
        try:
            if code is not None:
                set_status("Callback recibido. Completando sesion Supabase...")
                fase = "obtener_sesion"
                exchange_code_for_session(supabase, code)

            fase = "obtener_usuario_auth"
            if attempt is not None:
                attempt.trace("supabase_session_check_start")
            validation = session_controller.validate_current_session(
                load_context=True,
                claim_home=True,
            )
            if not validation.ok:
                raise UsuarioContextoError(
                    validation.message or SESSION_INVALID_MESSAGE
                )
            user = validation.user
            contexto_usuario = validation.context
            if attempt is not None:
                attempt.trace(
                    "eventplus_context_success",
                    session_present=True,
                )
            if not user or not contexto_usuario:
                raise RuntimeError("No se pudo validar la sesion autenticada.")

            auth_user_id = str(safe_get(user, "id", ""))
            email = str(safe_get(user, "email", ""))

            if not auth_user_id:
                raise RuntimeError(
                    "Supabase Auth no devolvio user.id.\n"
                    f"User recibido:\n{pretty(to_dict(user) or str(user))}"
                )

            set_status("Login exitoso. Consultando evp_usr_usuario para validar trigger...")

            fase = "cargar_usuario_eventplus"
            usuario_eventplus = buscar_usuario_eventplus_por_auth_uuid(supabase, auth_user_id)

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
                usuario_por_email = buscar_usuario_eventplus_por_email(supabase, email)
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
                fase = "cargar_contexto_usuario"
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

            if not validation.should_build_home:
                print("[LOGIN][INFO] Home ya fue reclamado por esta sesion.")
                return

            if attempt is not None:
                attempt.trace("home_claim_start")
                if not attempt.transition(WEB_OAUTH_ATTEMPT_HOME_BUILDING):
                    attempt.trace("late_event_rejected")
                    session_controller.logout()
                    return

            page.session.store.set("diagnostico_login", "\n".join(diagnostico))
            set_status("Acceso concedido. Abriendo Dashboard...")
            try:
                fase = "construir_dashboard"
                print("[HOME] Construyendo Home")
                from views.home_view import build_home_view

                home_control = build_home_view(
                    page=page,
                    contexto_usuario=contexto_usuario,
                    supabase=supabase,
                    session_controller=session_controller,
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
                session_controller.start_refresh_monitor(session_became_invalid)
                if attempt is not None:
                    attempt.transition(WEB_OAUTH_ATTEMPT_COMPLETED)
                    attempt.trace("home_claim_success", home_claimed=True)
                print("[HOME] Home mostrado")
            except Exception:
                traceback.print_exc()
                if attempt is not None:
                    attempt.transition(WEB_OAUTH_ATTEMPT_FAILED)
                session_controller.logout()
                page.clean()
                build_login_view(
                    page,
                    supabase,
                    initial_message="No fue posible abrir la pantalla principal.",
                    session_controller=session_controller,
                )
                page.update()
        except UsuarioContextoError as ex:
            if attempt is not None:
                attempt.transition(WEB_OAUTH_ATTEMPT_FAILED)
            session_controller.logout()
            set_status("Acceso no autorizado o contexto incompleto.")
            set_result(
                f"{ex}\n\n"
                "La sesion local fue cerrada. Puedes intentarlo nuevamente."
            )
        except Exception as ex:
            if attempt is not None:
                attempt.transition(WEB_OAUTH_ATTEMPT_FAILED)
            print(
                "[LOGIN][ERROR]",
                f"fase={fase}",
                f"tipo={type(ex).__name__}",
                f"mensaje={ex}",
            )
            traceback.print_exc()
            if fase in {
                "obtener_usuario_auth",
                "cargar_usuario_eventplus",
                "cargar_contexto_usuario",
                "construir_dashboard",
            }:
                session_controller.logout()
            set_status("La prueba fallo.")
            page.session.store.set(
                "diagnostico_login",
                "ERROR DURANTE LA PRUEBA\n\n"
                f"Fase: {fase}\n"
                f"{type(ex).__name__}: {ex}\n\n"
                "TRACEBACK COMPLETO:\n"
                f"{traceback.format_exc()}",
            )
            if fase in {"oauth_url", "abrir_navegador", "esperar_callback", "obtener_sesion", "obtener_usuario_auth"}:
                mensaje_principal = "No pudimos completar el inicio de sesion."
            elif fase == "cargar_usuario_eventplus":
                mensaje_principal = "La sesion fue iniciada, pero no fue posible cargar la informacion de tu usuario."
            elif fase == "cargar_contexto_usuario":
                mensaje_principal = "La sesion fue iniciada, pero no fue posible cargar tus cuentas o eventos."
            elif fase == "construir_dashboard":
                mensaje_principal = "La sesion fue iniciada, pero no pudimos preparar el Dashboard."
            else:
                mensaje_principal = "No pudimos completar el proceso de acceso."
            set_result(
                f"{mensaje_principal}\n\n"
                f"Fase detectada: {fase}\n\n"
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
            set_loading(False)

    def procesar_deep_link_android(url: str) -> None:
        if url in processed_callbacks:
            print("[LOGIN][WARNING] Callback OAuth duplicado ignorado.")
            return
        processed_callbacks.add(url)
        print("[LOGIN][INFO] Deep link OAuth recibido.")
        callback_result = parse_oauth_callback_url(url)
        if safe_get(callback_result, "error"):
            set_status("No pudimos completar el inicio de sesion con Google.")
            set_result("El inicio de sesion fue cancelado o no pudo completarse. Intenta nuevamente.")
            set_loading(False)
            return
        code = safe_get(callback_result, "code")
        if not code:
            set_status("No recibimos una respuesta valida del inicio de sesion.")
            set_result("No fue posible completar el inicio de sesion. Intenta nuevamente.")
            set_loading(False)
            return
        threading.Thread(target=lambda: completar_login_con_code(str(code), "obtener_sesion"), daemon=True).start()

    def route_change(e: ft.RouteChangeEvent) -> None:
        route = str(getattr(e, "route", "") or page.route or "")
        is_android_callback = route.startswith(ANDROID_OAUTH_REDIRECT_URL) or (
            "auth-callback" in route and ("code=" in route or "error=" in route)
        )
        if is_android_callback:
            procesar_deep_link_android(route)

    page.on_route_change = route_change

    def run_desktop_login_flow() -> None:
        fase = "inicio"
        try:
            set_loading(True)
            if is_checkin_mode():
                print("[CHECKIN][INFO] Inicio de sesion en modo Check-in.")
            fase = "oauth_url"
            set_status("Solicitando URL OAuth a Supabase...")

            redirect_url = get_oauth_redirect_url()
            oauth_url = get_oauth_url(supabase, redirect_url=redirect_url)

            fase = "abrir_navegador"
            set_status(
                "Se abrira el navegador para iniciar sesion con Google. "
                "Despues del login, vuelve a EventPlus."
            )

            webbrowser.open(oauth_url)

            fase = "esperar_callback"
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

            completar_login_con_code(str(code), "obtener_sesion")
        except Exception as ex:
            print("[LOGIN][ERROR]", f"fase={fase}", f"tipo={type(ex).__name__}", f"mensaje={ex}")
            traceback.print_exc()
            set_status("No pudimos iniciar sesion.")
            set_result("No fue posible abrir o completar el inicio de sesion con Google. Intenta nuevamente.")
            set_loading(False)

    async def run_android_login_flow() -> None:
        try:
            set_loading(True)
            set_status("Solicitando URL OAuth a Supabase...")
            oauth_url = get_oauth_url(
                supabase,
                redirect_url=get_oauth_redirect_url(page.platform),
            )
            set_status(
                "Completa el inicio de sesion en el navegador. "
                "Volveremos automaticamente a EventPlus."
            )
            await page.launch_url(oauth_url)
        except Exception as ex:
            print(
                "[LOGIN][ERROR]",
                "estrategia=android",
                f"tipo={type(ex).__name__}",
            )
            set_status("No pudimos iniciar sesion.")
            set_result(
                "No fue posible abrir el inicio de sesion con Google. "
                "Intenta nuevamente."
            )
            set_loading(False)

    current_web_attempt: WebOAuthAttempt | None = None

    async def web_attempt_timeout(attempt: WebOAuthAttempt) -> None:
        nonlocal current_web_attempt
        await asyncio.sleep(EVENTPLUS_WEB_OAUTH_ATTEMPT_TIMEOUT_SECONDS)
        if not attempt.transition(WEB_OAUTH_ATTEMPT_EXPIRED):
            return
        attempt.trace("timeout_fired", timeout_fired=True)
        attempt.set_timeout_task(None)
        if current_web_attempt is not attempt:
            return
        current_web_attempt = None
        session_controller.clear_oauth_attempt(attempt)
        set_web_attempt_ui(
            False,
            "No se completo la autenticacion. La ventana pudo haberse cerrado "
            "o el tiempo de espera termino. Intenta nuevamente.",
        )

    async def cancel_web_login(e: ft.ControlEvent) -> None:
        del e
        nonlocal current_web_attempt
        attempt = current_web_attempt
        if attempt is None or not attempt.transition(WEB_OAUTH_ATTEMPT_CANCELLED):
            return
        attempt.cancel_timeout()
        session_controller.clear_oauth_attempt(attempt)
        if current_web_attempt is attempt:
            current_web_attempt = None
            set_web_attempt_ui(False, "Inicio de sesion cancelado.")

    async def web_login_completed(e: ft.LoginEvent) -> None:
        nonlocal current_web_attempt
        attempt = current_web_attempt or session_controller.current_oauth_attempt
        if attempt is None:
            return

        error = str(getattr(e, "error", "") or "")
        if not attempt.mark_callback_received(has_error=bool(error)):
            attempt.trace("late_event_rejected", on_login=True)
            if (
                attempt.status == WEB_OAUTH_ATTEMPT_FAILED
                and current_web_attempt is attempt
            ):
                session_controller.clear_oauth_attempt(attempt)
                current_web_attempt = None
                set_web_attempt_ui(
                    False,
                    "Google no pudo completar la autenticacion. "
                    "Intenta nuevamente.",
                )
            return
        attempt.trace(
            "on_login_success_or_error",
            on_login=True,
            has_error=bool(error),
        )
        set_web_callback_processing_ui()
        if error:
            attempt.transition(WEB_OAUTH_ATTEMPT_FAILED)
            attempt.cancel_timeout()
            session_controller.clear_oauth_attempt(attempt)
            if current_web_attempt is not attempt:
                return
            current_web_attempt = None
            description = str(getattr(e, "error_description", "") or "")
            set_status("No pudimos completar el inicio de sesion con Google.")
            set_result(web_oauth_error_message(error, description))
            set_loading(False)
            return

        if attempt.status not in {
            WEB_OAUTH_ATTEMPT_CALLBACK_RECEIVED,
            WEB_OAUTH_ATTEMPT_SESSION_EXCHANGING,
        }:
            attempt.trace("late_event_rejected", on_login=True)
            return
        attempt.cancel_timeout()
        if current_web_attempt is not attempt:
            current_web_attempt = attempt

        session_present = await wait_for_supabase_session(
            session_controller,
            attempt,
        )

        if not session_present:
            attempt.transition(WEB_OAUTH_ATTEMPT_FAILED)
            session_controller.clear_oauth_attempt(attempt)
            current_web_attempt = None
            session_controller.logout()
            set_web_attempt_ui(
                False,
                "La autenticacion fue recibida, pero EventPlus no pudo "
                "completar la sesion. Intenta nuevamente.",
            )
            return

        if not attempt.transition(WEB_OAUTH_ATTEMPT_CONTEXT_BUILDING):
            attempt.trace("late_event_rejected", on_login=True)
            return
        attempt.trace("eventplus_context_start")
        await asyncio.to_thread(
            completar_login_con_code,
            None,
            "obtener_usuario_auth",
            attempt,
        )
        session_controller.clear_oauth_attempt(attempt)
        current_web_attempt = None

    page.on_login = web_login_completed

    async def prepare_server_session_after_exchange() -> None:
        validation = await asyncio.to_thread(
            session_controller.validate_current_session,
            load_context=True,
            claim_home=False,
        )
        if not validation.ok:
            raise UsuarioContextoError(
                validation.message or SESSION_INVALID_MESSAGE
            )
        if not session_controller.persist_server_session():
            raise RuntimeError(
                "No se pudo crear la sesion web server-side."
            )

    async def run_web_login_flow() -> None:
        nonlocal current_web_attempt
        if current_web_attempt is not None and current_web_attempt.pending:
            return

        await asyncio.to_thread(session_controller.clear_residual_session)
        attempt = WebOAuthAttempt(page)
        attempt.trace("login_click")
        current_web_attempt = attempt
        session_controller.register_oauth_attempt(attempt)
        set_result("")
        set_web_attempt_ui(
            True,
            "Esperando autenticacion. Completa el proceso en la ventana de Google "
            "o pulsa Cancelar.",
        )
        try:
            attempt.trace("page_login_called")
            await start_web_oauth(
                page,
                supabase,
                redirect_url=EVENTPLUS_WEB_OAUTH_REDIRECT_URL,
                attempt=attempt,
                on_session_exchanged=prepare_server_session_after_exchange,
            )
            attempt.mark_waiting_callback()
            if attempt.timeout_eligible:
                timeout_task = page.run_task(web_attempt_timeout, attempt)
                attempt.set_timeout_task(timeout_task)
        except Exception as ex:
            if not attempt.transition(WEB_OAUTH_ATTEMPT_CANCELLED):
                return
            attempt.cancel_timeout()
            session_controller.clear_oauth_attempt(attempt)
            if current_web_attempt is not attempt:
                return
            current_web_attempt = None
            print(
                "[LOGIN][ERROR]",
                "estrategia=web",
                f"tipo={type(ex).__name__}",
            )
            set_status("No pudimos iniciar sesion.")
            set_result(
                "No fue posible abrir el inicio de sesion con Google. "
                "Intenta nuevamente."
            )
            set_loading(False)

    async def login_click(e: ft.ControlEvent) -> None:
        del e
        strategy = detect_oauth_strategy(page)
        if strategy == OAUTH_STRATEGY_WEB:
            await run_web_login_flow()
            return
        if strategy == OAUTH_STRATEGY_ANDROID:
            await run_android_login_flow()
            return
        if strategy == OAUTH_STRATEGY_DESKTOP:
            threading.Thread(target=run_desktop_login_flow, daemon=True).start()
            return
        raise RuntimeError("Estrategia OAuth no soportada.")

    def logout_click(e: ft.ControlEvent) -> None:
        del e
        session_controller.logout()

        logout_button.visible = False
        set_status("Sesion local cerrada.")
        set_result("")

    login_button.on_click = login_click
    cancel_login_button.on_click = cancel_web_login
    logout_button.on_click = logout_click

    modo_texto = "Modo Check-in" if is_checkin_mode() else "Modo completo"
    instructions = ft.Container(
        content=ft.Column(
            [
                ft.Image(
                    src="brand/EventPlus_logo_v2.1_stacked.png",
                    width=220,
                    fit=ft.BoxFit.CONTAIN,
                ),
                ft.Text(
                    "EventPlus",
                    size=28,
                    weight=ft.FontWeight.BOLD,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Control de acceso y consulta de invitados",
                    size=15,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    f"Beta interna - {APP_VERSION} - {modo_texto}",
                    size=12,
                    color=ft.Colors.ON_SURFACE_VARIANT,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Row(
                    [login_button, progress],
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=12,
                ),
                cancel_login_button,
                logout_button,
                status,
                result_box,
            ],
            spacing=12,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        padding=24,
        border_radius=12,
        bgcolor=ft.Colors.SURFACE,
        border=ft.Border.all(width=1, color=ft.Colors.OUTLINE_VARIANT),
        width=460,
    )

    page.add(
        ft.SafeArea(
            content=ft.Container(
                content=instructions,
                alignment=ft.Alignment.CENTER,
                expand=True,
                padding=ft.Padding.symmetric(horizontal=16, vertical=24),
                bgcolor=ft.Colors.with_opacity(0.04, ft.Colors.PRIMARY),
            ),
            expand=True,
        )
    )

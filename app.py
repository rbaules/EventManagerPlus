from __future__ import annotations

import flet as ft

from config import APP_MODE, APP_VERSION
from db import create_supabase_client
from services.session_service import PageSessionController
from services.kiosk_e2e_service import KioskE2EProfiler
from services.web_reliability import PageWebTelemetry
from views.login_view import build_login_view
from views.authenticated_router import AuthenticatedViewRouter
from views.kiosk_router import KioskStandaloneRouter, is_kiosk_standalone_route


def main(
    page: ft.Page,
    *,
    server_session_binding: object = None,
) -> None:
    web_telemetry = PageWebTelemetry(page)
    web_telemetry.page_created()
    standalone_kiosk_requested = is_kiosk_standalone_route(
        getattr(page, "route", None)
    )
    kiosk_e2e_profiler = KioskE2EProfiler() if standalone_kiosk_requested else None
    if kiosk_e2e_profiler is not None:
        setattr(page, "_kiosk_e2e_profiler", kiosk_e2e_profiler)
    supabase = create_supabase_client()
    print("[APP][INFO] Modo de aplicacion:", APP_MODE)
    page.title = f"EVKOR - {APP_MODE} {APP_VERSION}"
    page.window.width = 950
    page.window.height = 760
    page.scroll = ft.ScrollMode.AUTO
    page.adaptive = True

    session_controller = PageSessionController(
        page,
        supabase,
        server_session_binding=server_session_binding,
        kiosk_e2e_profiler=kiosk_e2e_profiler,
    )
    web_telemetry.bind_session(
        lambda: session_controller.authenticated,
        lambda: session_controller.context,
    )

    def notify_home(callback_name: str) -> None:
        for control in list(page.controls):
            callback = control.data.get(callback_name) if isinstance(control.data, dict) else None
            if callable(callback):
                callback()

    def log_kiosk_lifecycle(stage: str) -> None:
        """Registra transiciones de transporte sin datos de sesión o usuario."""
        print(
            "[KIOSK-LIFECYCLE] "
            f"stage={stage} route={getattr(page, 'route', None)} "
            f"page_python_id={id(page)}"
        )

    def log_route_event(event_route: object) -> None:
        """Expone correlacion de rutas al handler efectivo de cada vista."""
        event_path = str(event_route or "/").split("?", 1)[0]
        page_path = str(getattr(page, "route", None) or "/").split("?", 1)[0]
        print(
            "[APP-ROUTE] "
            f"event_route={event_path} page_route={page_path} "
            f"authenticated={'yes' if session_controller.authenticated else 'no'} "
            f"standalone_kiosk_requested={str(standalone_kiosk_requested).lower()} "
            f"page_python_id={id(page)}"
        )

    # Flet expone un solo callback on_route_change; cada vista instala el suyo.
    # Se comparte este logger sin reemplazar el handler de la vista activa.
    setattr(page, "_evkor_log_route_event", log_route_event)

    def disconnected(_event: ft.Event[ft.Page]) -> None:
        log_kiosk_lifecycle("page_disconnect")
        web_telemetry.disconnect()
        session_controller.set_connected(False)
        notify_home("pause_dashboard")

    async def connected(_event: ft.Event[ft.Page]) -> None:
        log_kiosk_lifecycle("page_connect")
        web_telemetry.connect()
        if not session_controller.authenticated:
            session_controller.set_connected(True)
            web_telemetry.ready(restored_session=False)
            return
        result = await session_controller.validate_after_reconnect()
        if result.ok:
            notify_home("resume_dashboard")
            web_telemetry.ready(restored_session=True)
            return
        await _show_login_after_invalid_session(
            page,
            supabase,
            session_controller,
            result.message,
        )
        web_telemetry.ready(restored_session=False)

    def closed(_event: ft.Event[ft.Page]) -> None:
        log_kiosk_lifecycle("page_close")
        web_telemetry.close()
        notify_home("pause_dashboard")
        session_controller.close()

    def page_error(event: ft.Event[ft.Page]) -> None:
        web_telemetry.error(event)

    page.on_disconnect = disconnected
    page.on_connect = connected
    page.on_close = closed
    page.on_error = page_error

    if bool(getattr(page, "web", False)):
        restore_started = web_telemetry.restore_start()
        if session_controller.has_server_session:
            validation = session_controller.validate_current_session(
                load_context=True,
                claim_home=True,
            )
            web_telemetry.restore_result(
                "OK" if validation.ok else "FAILED",
                restore_started,
            )
        else:
            validation = None
            web_telemetry.restore_result("NONE", restore_started)
    else:
        validation = None

    if validation is not None:
        if validation.ok and validation.context and standalone_kiosk_requested:
            kiosk_router = KioskStandaloneRouter(
                page=page,
                contexto_usuario=validation.context,
                supabase=supabase,
                session_controller=session_controller,
                e2e_profiler=kiosk_e2e_profiler,
            )
            kiosk_router.mount_current_route()
            session_controller.start_refresh_monitor(kiosk_router.on_session_invalid)
            web_telemetry.ready(restored_session=True)
            return
        if validation.ok and validation.should_build_home and validation.context:
            authenticated_router = AuthenticatedViewRouter(
                page=page,
                contexto_usuario=validation.context,
                supabase=supabase,
                session_controller=session_controller,
            )
            authenticated_router.mount_current_route()
            session_controller.start_refresh_monitor(
                lambda message: _show_login_after_invalid_session(
                    page,
                    supabase,
                    session_controller,
                    message,
                )
            )
            web_telemetry.ready(restored_session=True)
            return

    if standalone_kiosk_requested:
        KioskStandaloneRouter(
            page=page,
            supabase=supabase,
            session_controller=session_controller,
        ).mount_current_route()
        web_telemetry.ready(restored_session=False)
        return

    build_login_view(page, supabase, session_controller=session_controller)
    web_telemetry.ready(restored_session=False)


async def _show_login_after_invalid_session(
    page: ft.Page,
    supabase: object,
    session_controller: PageSessionController,
    message: str,
) -> None:
    session_controller.logout()
    page.navigation_bar = None
    print(
        "[PAGE-CLEAN] source=app._show_login_after_invalid_session "
        f"route={str(getattr(page, 'route', None) or '/').split('?', 1)[0]}"
    )
    page.clean()
    if is_kiosk_standalone_route(getattr(page, "route", None)):
        KioskStandaloneRouter(
            page=page,
            supabase=supabase,
            session_controller=session_controller,
        ).mount_current_route()
        page.update()
        return
    build_login_view(
        page,
        supabase,
        initial_message=message,
        session_controller=session_controller,
    )
    page.update()


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")

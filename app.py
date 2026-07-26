from __future__ import annotations

import flet as ft

from config import APP_MODE, APP_VERSION
from db import create_supabase_client
from services.session_service import PageSessionController
from views.login_view import build_login_view


def main(page: ft.Page) -> None:
    supabase = create_supabase_client()
    print("[APP][INFO] Modo de aplicacion:", APP_MODE)
    page.title = f"EventPlus - {APP_MODE} {APP_VERSION}"
    page.window.width = 950
    page.window.height = 760
    page.scroll = ft.ScrollMode.AUTO
    page.adaptive = True

    session_controller = PageSessionController(page, supabase)

    def disconnected(_event: ft.ControlEvent) -> None:
        session_controller.set_connected(False)

    async def connected(_event: ft.ControlEvent) -> None:
        if not session_controller.authenticated:
            session_controller.set_connected(True)
            return
        result = await session_controller.validate_after_reconnect()
        if result.ok:
            return
        await _show_login_after_invalid_session(
            page,
            supabase,
            session_controller,
            result.message,
        )

    def closed(_event: ft.ControlEvent) -> None:
        session_controller.close()

    page.on_disconnect = disconnected
    page.on_connect = connected
    page.on_close = closed
    build_login_view(page, supabase, session_controller=session_controller)


async def _show_login_after_invalid_session(
    page: ft.Page,
    supabase: object,
    session_controller: PageSessionController,
    message: str,
) -> None:
    session_controller.logout()
    page.navigation_bar = None
    page.clean()
    build_login_view(
        page,
        supabase,
        initial_message=message,
        session_controller=session_controller,
    )
    page.update()


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")

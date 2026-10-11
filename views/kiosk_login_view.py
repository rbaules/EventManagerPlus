from __future__ import annotations

from collections.abc import Callable
from typing import Any

import flet as ft

from views.login_view import build_login_view


def build_kiosk_login_view(
    *,
    page: ft.Page,
    supabase: Any,
    session_controller: Any,
    on_authenticated: Callable[[dict[str, Any]], None],
    on_session_invalid: Callable[[str], Any],
    on_post_authentication_error: Callable[[Exception], None],
    initial_message: str | None = None,
) -> None:
    """Render the standalone Kiosk entry point using the shared Google OAuth flow."""
    build_login_view(
        page,
        supabase,
        initial_message=initial_message,
        session_controller=session_controller,
        on_authenticated=on_authenticated,
        on_session_invalid=on_session_invalid,
        on_post_authentication_error=on_post_authentication_error,
        title="EVKOR Kiosco",
        subtitle="Inicia sesión para operar el Kiosco",
        login_label="Ingresar con Google",
    )

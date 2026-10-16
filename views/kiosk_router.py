from __future__ import annotations

import asyncio
from collections.abc import Callable
from time import perf_counter
from typing import Any

import flet as ft

from services.authorization_service import (
    ROL_ADMINISTRADOR,
    ROL_CONSULTA,
    ROL_MASTER,
    ROL_OPERADOR,
    evento_autorizado,
    rol_contexto,
)
from services.kiosk_asset_service import KioskVisualAssetCache
from views.kiosk_login_view import build_kiosk_login_view
from views.kiosk_view import build_kiosk_view


KIOSK_STANDALONE_ROUTE = "/kiosk"
KIOSK_STANDALONE_LOGIN_ROUTE = "/kiosk/login"


def is_kiosk_standalone_route(route: str | None) -> bool:
    clean = str(route or "").split("?", 1)[0].rstrip("/") or "/"
    return clean in {KIOSK_STANDALONE_ROUTE, KIOSK_STANDALONE_LOGIN_ROUTE}


def kiosk_standalone_access_message(contexto_usuario: dict[str, Any] | None) -> str | None:
    """Return a controlled message when the standalone Kiosk cannot operate."""
    if not contexto_usuario or not evento_autorizado(contexto_usuario):
        return "No hay un evento seleccionado para operar el Kiosco."
    rol = rol_contexto(contexto_usuario)
    if rol == ROL_CONSULTA:
        return "Tu rol de Consulta no tiene permiso para operar el Kiosco."
    if rol not in {ROL_MASTER, ROL_ADMINISTRADOR, ROL_OPERADOR}:
        return "Tu usuario no tiene permiso para operar el Kiosco."
    return None


class KioskStandaloneRouter:
    """Route only the standalone Kiosk: never mounts Home or its shell."""

    def __init__(
        self,
        *,
        page: ft.Page,
        supabase: Any,
        session_controller: Any,
        contexto_usuario: dict[str, Any] | None = None,
        kiosk_builder: Callable[..., ft.Control] | None = None,
        kiosk_login_builder: Callable[..., None] | None = None,
        e2e_profiler: Any = None,
    ) -> None:
        self.page = page
        self.supabase = supabase
        self.session_controller = session_controller
        self.contexto_usuario = contexto_usuario
        self._kiosk_builder = kiosk_builder or build_kiosk_view
        self._kiosk_login_builder = kiosk_login_builder or build_kiosk_login_view
        self._e2e_profiler = e2e_profiler or getattr(page, "_kiosk_e2e_profiler", None)
        self._visual_asset_cache = KioskVisualAssetCache()
        self._asset_context_ready_at: float | None = None
        self._asset_prefetch_key: tuple[int, int] | None = None
        self.active_control: ft.Control | None = None
        self._navigation_target: str | None = None

    def _start_asset_prefetch(self, context: dict[str, Any]) -> None:
        """Begin artwork loading without holding up standalone route navigation."""
        event = context.get("evento_actual")
        if not isinstance(event, dict):
            return
        try:
            key = (int(event["cuenta_id"]), int(event["evento_id"]))
        except (KeyError, TypeError, ValueError):
            return
        self._visual_asset_cache.activate(*key)
        if self._asset_prefetch_key == key:
            return
        self._asset_prefetch_key = key
        if self._asset_context_ready_at is None:
            self._asset_context_ready_at = perf_counter()
            print("[KIOSK-STARTUP][PERF] stage=T0_context_ready source=session_restore")
        if self._e2e_profiler is not None:
            self._e2e_profiler.mark("E7_KIOSK_BUILD_BEGIN")
        print(f"[KIOSK-ASSET][PERF] stage=context_ready account_id={key[0]} event_id={key[1]}")

        async def prefetch() -> None:
            try:
                await asyncio.gather(
                    asyncio.to_thread(self._visual_asset_cache.get_or_load, self.supabase, *key, "background"),
                    asyncio.to_thread(self._visual_asset_cache.get_or_load, self.supabase, *key, "panel"),
                )
            except Exception as ex:
                # Individual asset failures are already handled by the cache; this
                # guard makes prefetch strictly non-fatal to Kiosk navigation.
                print(f"[KIOSK-ASSET] prefetch unavailable type={type(ex).__name__}")

        self.page.run_task(prefetch)

    def _navigate(self, route: str) -> None:
        """Schedule standalone navigation on the Page loop, even from OAuth threads."""
        if self._navigation_target == route:
            return
        self._navigation_target = route
        if route == KIOSK_STANDALONE_ROUTE and self._asset_context_ready_at is not None:
            print(
                "[KIOSK-STARTUP][PERF] stage=T1_navigation_scheduled "
                f"total_ms={(perf_counter() - self._asset_context_ready_at) * 1000:.1f}"
            )
        self.page.run_task(self._push_route, route)

    async def _push_route(self, route: str) -> None:
        try:
            await self.page.push_route(route)
            if route == KIOSK_STANDALONE_ROUTE and self._asset_context_ready_at is not None:
                print(
                    "[KIOSK-STARTUP][PERF] stage=T2_route_active "
                    f"total_ms={(perf_counter() - self._asset_context_ready_at) * 1000:.1f}"
                )
            self.mount_current_route()
        finally:
            if self._navigation_target == route:
                self._navigation_target = None

    def _mount(self, control: ft.Control) -> ft.Control:
        route = str(getattr(self.page, "route", None) or "/").split("?", 1)[0]
        print(
            "[KIOSK-ROUTER] mount_begin "
            f"route_requested={route} page_route={route} "
            f"router_python_id={id(self)} active_control_python_id="
            f"{id(self.active_control) if self.active_control is not None else None}"
        )
        self.page.navigation_bar = None
        print(f"[PAGE-CLEAN] source=kiosk_router._mount route={route}")
        self.page.clean()
        self.page.add(control)
        self.page.update()
        self.active_control = control
        print(
            "[KIOSK-ROUTER] mount_end "
            f"route_requested={route} page_route="
            f"{str(getattr(self.page, 'route', None) or '/').split('?', 1)[0]} "
            f"router_python_id={id(self)} active_control_python_id={id(control)}"
        )
        return control

    def _show_login(self, message: str | None = None) -> None:
        self.page.navigation_bar = None
        print(
            "[PAGE-CLEAN] source=kiosk_router._show_login "
            f"route={str(getattr(self.page, 'route', None) or '/').split('?', 1)[0]}"
        )
        self.page.clean()
        self._kiosk_login_builder(
            page=self.page,
            supabase=self.supabase,
            session_controller=self.session_controller,
            on_authenticated=self.on_login_authenticated,
            on_session_invalid=self.on_session_invalid,
            on_post_authentication_error=self.on_post_authentication_error,
            initial_message=message,
        )
        self.page.update()
        self.active_control = self.page.controls[0] if self.page.controls else None

    def _unavailable_view(self, message: str) -> ft.Control:
        return ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=ft.Column(
                [
                    ft.Text("Kiosco", size=32, weight=ft.FontWeight.BOLD),
                    ft.Text(message, size=18, text_align=ft.TextAlign.CENTER),
                ],
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=16,
            ),
            data={"kiosk": "standalone_unavailable", "message": message},
        )

    def mount_current_route(self) -> ft.Control | None:
        route = str(getattr(self.page, "route", "") or "")
        authenticated = bool(getattr(self.session_controller, "authenticated", False))
        if not authenticated:
            if route != KIOSK_STANDALONE_LOGIN_ROUTE:
                self._navigate(KIOSK_STANDALONE_LOGIN_ROUTE)
                return self.active_control
            self._show_login()
            return self.active_control

        if route.rstrip("/") == KIOSK_STANDALONE_LOGIN_ROUTE:
            self._navigate(KIOSK_STANDALONE_ROUTE)
            return self.active_control

        context = self.contexto_usuario or getattr(self.session_controller, "context", None)
        message = kiosk_standalone_access_message(context)
        if message:
            return self._mount(self._unavailable_view(message))
        assert isinstance(context, dict)
        if self._asset_context_ready_at is None:
            self._asset_context_ready_at = perf_counter()
            print("[KIOSK-STARTUP][PERF] stage=T0_context_ready source=session_restore")
        control = self._mount(
            self._kiosk_builder(
                page=self.page,
                contexto_usuario=context,
                supabase=self.supabase,
                on_authenticated_route_change=self.mount_current_route,
                on_kiosk_logout=self.logout,
                visual_asset_cache=self._visual_asset_cache,
                asset_context_ready_at=self._asset_context_ready_at,
                e2e_profiler=self._e2e_profiler,
            )
        )
        # The scanner startup is scheduled during the view build. Start visual
        # prefetch only after the Kiosk has been mounted, then coalesce with its
        # in-flight asset requests.
        self._start_asset_prefetch(context)
        return control

    def on_login_authenticated(self, contexto_usuario: dict[str, Any]) -> None:
        self.contexto_usuario = contexto_usuario
        self._asset_context_ready_at = perf_counter()
        print("[KIOSK-STARTUP][PERF] stage=T0_context_ready source=oauth")
        if self._e2e_profiler is not None:
            self._e2e_profiler.mark("E6_CONTEXT_RESOLVED", source="oauth_callback")
        self._navigate(KIOSK_STANDALONE_ROUTE)

    async def on_session_invalid(self, message: str) -> None:
        self.session_controller.logout()
        self.contexto_usuario = None
        self._navigate(KIOSK_STANDALONE_LOGIN_ROUTE)

    def on_post_authentication_error(self, error: Exception) -> None:
        print(
            "[KIOSK][NAVIGATION][ERROR]",
            f"type={type(error).__name__}",
            f"message={error}",
        )
        self._mount(
            self._unavailable_view(
                "No fue posible abrir el Kiosco. Intenta nuevamente o cierra sesión."
            )
        )

    def logout(self) -> None:
        control = self.active_control
        callbacks = getattr(control, "data", {}) if control is not None else {}
        pause = callbacks.get("pause_dashboard") if isinstance(callbacks, dict) else None
        if callable(pause):
            pause()
        self.session_controller.logout()
        self.contexto_usuario = None
        self._visual_asset_cache.clear()
        self._asset_prefetch_key = None
        self._asset_context_ready_at = None
        self._navigate(KIOSK_STANDALONE_LOGIN_ROUTE)

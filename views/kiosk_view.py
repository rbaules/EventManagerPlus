from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from time import monotonic, perf_counter
from typing import Any, Callable

import flet as ft

from components.kiosk_qr_scanner import KioskQrScanner
from components.kiosk_route_map import build_kiosk_route_map, build_route_overlay_data_url
from components.kiosk_route_map_viewer import MAX_ZOOM, MIN_ZOOM, build_kiosk_route_map_viewer
from components.evkor_brand import build_evkor_brand
from services.invitado_service import (
    cargar_grupo_invitacion,
    confirmar_llegadas_invitados,
    resolver_invitacion_qr,
)
from services.kiosk_asset_service import (
    KioskVisualAssetCache,
)
from services.kiosk_map_service import ResultadoRuta, calcular_ruta
from services.kiosk_admin_service import validar_pin_administrativo
from services.kiosk_route_map_service import (
    MapAssetCache,
    load_kiosk_route_map_data_url,
    resolve_kiosk_route_map_url,
)
from services.navigation_service import parse_app_route


KIOSK_WINE = "#971B1F"
KIOSK_WINE_DARK = "#731116"
KIOSK_IVORY = "#F8F1E8"
KIOSK_BLUSH = "#F3D9D0"
KIOSK_TEXT = "#4B241C"
KIOSK_BORDER = "#D9C7BC"
# CONTAIN preserves the full event composition. This warm neutral extends it
# when the viewport aspect ratio differs without introducing white bands.
KIOSK_BACKGROUND_EXTENSION = "#5E4A43"
KIOSK_WIDE_LAYOUT_MIN_WIDTH = 1180
KIOSK_WIDE_PANEL_MIN_WIDTH = 624
KIOSK_WIDE_PANEL_MAX_WIDTH = 640
KIOSK_WIDE_PANEL_ALIGNMENT_X = 0.1
# Future debt: background composition contract / configurable safe zone per event.
KIOSK_SUCCESS_RESET_SECONDS = 10
KIOSK_ADMIN_TAP_COUNT = 6
KIOSK_ADMIN_TAP_WINDOW_SECONDS = 5.0

class KioskPhase(str, Enum):
    WELCOME_SCAN = "WELCOME_SCAN"
    RESOLVING = "RESOLVING"
    SELECT_GUESTS = "SELECT_GUESTS"
    CONFIRMING = "CONFIRMING"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"


@dataclass
class KioskGuest:
    guest_id: int
    name: str
    mesa_id: int | None
    mesa_texto: str
    llegada_confirmada: bool
    estado_llegada: str
    fecha_hora_conf_llegada: Any
    selected: bool = False

    @property
    def selectable(self) -> bool:
        return not self.llegada_confirmada


@dataclass
class KioskState:
    phase: KioskPhase = KioskPhase.WELCOME_SCAN
    qr_code: str | None = None
    cuenta_id: int | None = None
    evento_id: int | None = None
    invitation_id: int | None = None
    destinatario: str | None = None
    guests: list[KioskGuest] = field(default_factory=list)
    selected_guest_ids: set[int] = field(default_factory=set)
    error_message: str | None = None
    resolution_id: int = 0
    confirmation_id: int = 0
    confirmed_count: int = 0
    success_name: str | None = None
    route_map_generation: int = 0
    route_result: ResultadoRuta | None = None
    map_signed_url: str | None = None
    map_preview_src: str | None = None
    map_preview_overlay_src: str | None = None
    map_preview_ready: bool = False
    map_loading: bool = False

    def clear_route_map(self) -> None:
        self.route_map_generation += 1
        self.route_result = None
        self.map_signed_url = None
        self.map_preview_src = None
        self.map_preview_overlay_src = None
        self.map_preview_ready = False
        self.map_loading = False

    def _clear_invitation(self) -> None:
        self.cuenta_id = None
        self.evento_id = None
        self.invitation_id = None
        self.destinatario = None
        self.guests.clear()
        self.selected_guest_ids.clear()

    def invalidate_resolution(self) -> None:
        self.resolution_id += 1

    def invalidate_confirmation(self) -> None:
        self.confirmation_id += 1

    def reset_kiosk(self) -> None:
        self.invalidate_resolution()
        self.invalidate_confirmation()
        self.phase = KioskPhase.WELCOME_SCAN
        self.qr_code = None
        self._clear_invitation()
        self.error_message = None
        self.confirmed_count = 0
        self.success_name = None
        self.clear_route_map()

    def accept_scanned_qr(self, codigo_qr: str) -> int | None:
        if self.phase != KioskPhase.WELCOME_SCAN:
            return None
        self.invalidate_resolution()
        self.invalidate_confirmation()
        self.qr_code = codigo_qr
        self._clear_invitation()
        self.error_message = None
        self.confirmed_count = 0
        self.success_name = None
        self.clear_route_map()
        self.phase = KioskPhase.RESOLVING
        return self.resolution_id

    def _apply_guests(self, invitados: list[dict[str, Any]]) -> None:
        self.guests = [
            KioskGuest(
                guest_id=int(item["invitado_id"]),
                name=str(item["nombre_completo"]),
                mesa_id=item.get("mesa_id"),
                mesa_texto=str(item.get("mesa_texto") or "Sin mesa"),
                llegada_confirmada=bool(item.get("llegada_confirmada")),
                estado_llegada=str(item.get("estado_llegada") or "Pendiente"),
                fecha_hora_conf_llegada=item.get("fecha_hora_conf_llegada"),
            )
            for item in invitados
        ]

    def apply_group(self, invitacion: dict[str, Any], invitados: list[dict[str, Any]]) -> None:
        self.cuenta_id = int(invitacion["cuenta_id"])
        self.evento_id = int(invitacion["evento_id"])
        self.invitation_id = int(invitacion["invitacion_id"])
        self.destinatario = str(invitacion["destinatario"])
        self._apply_guests(invitados)
        self.selected_guest_ids.clear()
        self.qr_code = None
        self.error_message = None
        self.phase = KioskPhase.SELECT_GUESTS

    def apply_confirmation_result(
        self,
        invitados: list[dict[str, Any]],
        confirmed_count: int,
        confirmed_guest_ids: set[int],
    ) -> None:
        self._apply_guests(invitados)
        self.selected_guest_ids.clear()
        self.error_message = None
        self.confirmed_count = confirmed_count
        self.success_name = format_kiosk_success_name(
            self.destinatario,
            self.guests,
            confirmed_guest_ids,
        )
        self.phase = KioskPhase.SUCCESS

    def success_mesa_id(self) -> int | None:
        mesa_ids = {guest.mesa_id for guest in self.guests}
        if len(mesa_ids) != 1:
            return None
        mesa_id = next(iter(mesa_ids))
        if isinstance(mesa_id, bool):
            return None
        try:
            normalized_mesa_id = int(mesa_id)
        except (TypeError, ValueError):
            return None
        return normalized_mesa_id if normalized_mesa_id > 0 else None

    def success_table_message(self) -> str:
        """Return a single safe table heading from the confirmed group state."""
        resolved_tables: set[tuple[int, str]] = set()
        for guest in self.guests:
            if isinstance(guest.mesa_id, bool):
                return "Su mesa aún no está asignada."
            try:
                mesa_id = int(guest.mesa_id)
            except (TypeError, ValueError):
                return "Su mesa aún no está asignada."
            mesa_texto = str(guest.mesa_texto or "").strip()
            if mesa_id <= 0 or not mesa_texto or mesa_texto.casefold() == "sin mesa":
                return "Su mesa aún no está asignada."
            resolved_tables.add((mesa_id, mesa_texto))

        if len(resolved_tables) != 1:
            return "Su mesa aún no está asignada."
        _mesa_id, mesa_texto = next(iter(resolved_tables))
        return f"Su mesa es: {mesa_texto}"

    def set_guest_selected(self, guest_id: int, selected: bool) -> None:
        for guest in self.guests:
            if guest.guest_id != guest_id:
                continue
            if not guest.selectable:
                guest.selected = False
                self.selected_guest_ids.discard(guest_id)
                return
            guest.selected = selected
            if selected:
                self.selected_guest_ids.add(guest_id)
            else:
                self.selected_guest_ids.discard(guest_id)
            return

    def select_all_guests(self) -> None:
        for guest in self.guests:
            if guest.selectable:
                guest.selected = True
                self.selected_guest_ids.add(guest.guest_id)

    def show_error(self, message: str = "No pudimos leer esta invitacion.") -> None:
        self.clear_route_map()
        self.qr_code = None
        self._clear_invitation()
        self.error_message = message
        self.phase = KioskPhase.ERROR

    def table_heading(self) -> str:
        mesa_ids = {guest.mesa_id for guest in self.guests}
        if len(mesa_ids) == 1:
            only_mesa = next(iter(mesa_ids))
            if only_mesa is not None:
                return f"Mesa: {self.guests[0].mesa_texto}"
            return "Mesa: Sin asignar"
        return "Mesa: Asignada por integrante"


def _kiosk_first_name(value: Any) -> str | None:
    words = str(value or "").strip().split()
    return words[0] if words else None


def format_kiosk_success_name(
    destinatario: str | None,
    guests: list[KioskGuest],
    confirmed_guest_ids: set[int],
) -> str | None:
    """Choose the approved SUCCESS greeting without changing arrival state."""
    if guests and not any(not guest.llegada_confirmada for guest in guests):
        resolved_destinatario = str(destinatario or "").strip()
        if resolved_destinatario:
            return resolved_destinatario

    names = [
        first_name
        for guest in guests
        if guest.guest_id in confirmed_guest_ids
        if (first_name := _kiosk_first_name(guest.name)) is not None
    ]
    if not names:
        return None
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} y {names[1]}"
    return f"{', '.join(names[:-1])} y {names[-1]}"


def kiosk_success_copy(confirmed_count: int) -> tuple[str, str]:
    """Return the SUCCESS wording for the guests confirmed in this operation."""
    if confirmed_count == 1:
        return (
            "Esperamos que disfrutes lo que hemos preparado para ti.",
            "¡Bienvenido(a)!",
        )
    return (
        "Esperamos que disfruten lo que hemos preparado para ustedes.",
        "¡Bienvenidos!",
    )


def kiosk_success_detail(confirmed_count: int) -> str:
    """Return only the guest-facing SUCCESS detail, not its table heading."""
    if confirmed_count == 1:
        return "Esperamos que disfrutes lo que hemos preparado para ti."
    return "Esperamos que disfruten lo que hemos preparado para ustedes."


def is_kiosk_route(route: str | None) -> bool:
    clean = str(route or "").split("?", 1)[0].rstrip("/") or "/"
    return clean == "/kiosk" or parse_app_route(clean)[0] == "kiosk"


def build_kiosk_view(
    *,
    page: ft.Page,
    contexto_usuario: dict[str, Any],
    supabase: Any = None,
    on_authenticated_route_change: Callable[[], None] | None = None,
    on_kiosk_logout: Callable[[], None] | None = None,
    visual_asset_cache: KioskVisualAssetCache | None = None,
    asset_context_ready_at: float | None = None,
    e2e_profiler: Any = None,
) -> ft.Control:
    """Build the Kiosk shell and resolve accepted QR codes through existing read services."""
    # A scrollable Page sizes its direct children from their contents. Kiosk is a
    # viewport surface, so constrain this route and restore the caller's setting
    # when its route is left.
    previous_page_scroll = getattr(page, "scroll", None)
    page.scroll = None
    page_scroll_restored = False

    def restore_page_scroll() -> None:
        nonlocal page_scroll_restored
        if page_scroll_restored:
            return
        page.scroll = previous_page_scroll
        page_scroll_restored = True

    build_started = perf_counter()
    if e2e_profiler is not None:
        e2e_profiler.mark("E7_KIOSK_BUILD_ENTERED")
    if asset_context_ready_at is not None:
        print(
            "[KIOSK-STARTUP][PERF] stage=T3_build_begin "
            f"total_ms={(build_started - asset_context_ready_at) * 1000:.1f}"
        )
    state = KioskState()
    screen_content = ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=20)
    resolution_task: Any = None
    resolution_owner: object | None = None
    confirmation_task: Any = None
    confirmation_owner: object | None = None
    background_task: Any = None
    background_owner: object | None = None
    panel_task: Any = None
    panel_owner: object | None = None
    kiosk_asset_cache = visual_asset_cache or KioskVisualAssetCache()
    route_map_task: Any = None
    route_map_owner: object | None = None
    map_asset_cache = MapAssetCache()
    viewer_timeout_task: Any = None
    viewer_owner: object | None = None
    viewer_overlay: ft.Control | None = None
    viewer_zoom = MIN_ZOOM
    success_timer_task: Any = None
    success_timer_owner: object | None = None
    has_rendered = False
    admin_tap_count = 0
    admin_tap_started_at: float | None = None
    admin_dialog: ft.AlertDialog | None = None
    admin_modal: str | None = None
    admin_validation_task: Any = None
    admin_validation_owner: object | None = None
    admin_scanner_task: Any = None
    admin_scanner_owner: object | None = None

    # The real Flet Page exposes this list.  The small test Page deliberately
    # mirrors it so the viewer is verified without any browser or camera.
    if not hasattr(page, "overlay"):
        page.overlay = []

    def reset_admin_taps() -> None:
        nonlocal admin_tap_count, admin_tap_started_at
        admin_tap_count = 0
        admin_tap_started_at = None

    def close_admin_dialog(*, update: bool = True) -> None:
        nonlocal admin_dialog
        if admin_dialog is not None:
            admin_dialog.open = False
        admin_dialog = None
        if update:
            page.update()

    def resume_scanner_after_admin() -> None:
        nonlocal admin_scanner_task, admin_scanner_owner
        if state.phase != KioskPhase.WELCOME_SCAN or admin_modal is not None:
            return
        owner = object()
        admin_scanner_owner = owner

        async def resume() -> None:
            nonlocal admin_scanner_task
            try:
                await scanner.resume_after_admin()
            finally:
                if admin_scanner_owner is owner:
                    admin_scanner_task = None

        admin_scanner_task = page.run_task(resume)

    def suspend_scanner_for_admin() -> None:
        nonlocal admin_scanner_task, admin_scanner_owner
        owner = object()
        admin_scanner_owner = owner

        async def suspend() -> None:
            nonlocal admin_scanner_task
            try:
                await scanner.suspend_for_admin()
            finally:
                if admin_scanner_owner is owner:
                    admin_scanner_task = None

        admin_scanner_task = page.run_task(suspend)

    def cleanup_admin_access(*, resume_scanner: bool, update: bool = False) -> None:
        nonlocal admin_modal, admin_validation_owner, admin_validation_task, admin_scanner_owner, admin_scanner_task
        reset_admin_taps()
        admin_modal = None
        admin_validation_owner = None
        task = admin_validation_task
        admin_validation_task = None
        if task is not None and not task.done():
            task.cancel()
        admin_scanner_owner = None
        scanner_task = admin_scanner_task
        admin_scanner_task = None
        if not resume_scanner and scanner_task is not None and not scanner_task.done():
            scanner_task.cancel()
        close_admin_dialog(update=False)
        if resume_scanner:
            resume_scanner_after_admin()
        if update:
            page.update()

    def show_admin_panel() -> None:
        nonlocal admin_dialog, admin_modal
        if state.phase != KioskPhase.WELCOME_SCAN:
            cleanup_admin_access(resume_scanner=False)
            return
        admin_modal = "panel"

        def restart_kiosk(_event: Any = None) -> None:
            cleanup_admin_access(resume_scanner=False, update=False)
            reset_kiosk()
            resume_scanner_after_admin()

        def close_panel(_event: Any = None) -> None:
            cleanup_admin_access(resume_scanner=True)

        def logout_kiosk(_event: Any = None) -> None:
            cleanup_admin_access(resume_scanner=False, update=False)
            if on_kiosk_logout is not None:
                on_kiosk_logout()

        admin_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Administración Kiosco", color=KIOSK_WINE),
            content=ft.Column(
                [ft.Text("Selecciona una acción administrativa.", color=KIOSK_TEXT)],
                tight=True,
            ),
            actions=[
                ft.OutlinedButton("Reiniciar Kiosco", on_click=restart_kiosk),
                ft.ElevatedButton(
                    "Cerrar sesión",
                    on_click=logout_kiosk,
                    style=ft.ButtonStyle(bgcolor=KIOSK_WINE, color=ft.Colors.WHITE),
                ),
                ft.OutlinedButton("Volver", on_click=close_panel),
            ],
            bgcolor=KIOSK_IVORY,
            data={"kiosk": "admin_panel"},
        )
        page.show_dialog(admin_dialog)

    def show_admin_pin_dialog() -> None:
        nonlocal admin_dialog, admin_modal, admin_validation_task, admin_validation_owner
        if state.phase != KioskPhase.WELCOME_SCAN or admin_modal is not None:
            return
        reset_admin_taps()
        admin_modal = "pin"
        suspend_scanner_for_admin()
        pin_field = ft.TextField(
            label="PIN administrativo",
            password=True,
            can_reveal_password=False,
            keyboard_type=ft.KeyboardType.NUMBER,
            max_length=6,
            autofocus=True,
            width=280,
            data={"kiosk": "admin_pin_input"},
        )
        feedback = ft.Text("", color=ft.Colors.ERROR, visible=False, data={"kiosk": "admin_pin_feedback"})
        submit = ft.ElevatedButton(
            "Acceder",
            style=ft.ButtonStyle(bgcolor=KIOSK_WINE, color=ft.Colors.WHITE),
            data={"kiosk": "admin_pin_submit"},
        )

        def cancel_pin(_event: Any = None) -> None:
            cleanup_admin_access(resume_scanner=True)

        def submit_pin(_event: Any = None) -> None:
            nonlocal admin_validation_task, admin_validation_owner
            if admin_modal != "pin" or admin_validation_owner is not None:
                return
            pin = str(pin_field.value or "")
            if len(pin) != 6 or not pin.isdigit():
                feedback.value = "Ingresa un PIN de 6 dígitos."
                feedback.visible = True
                page.update()
                return
            submit.disabled = True
            feedback.value = "Validando..."
            feedback.color = KIOSK_TEXT
            feedback.visible = True
            owner = object()
            admin_validation_owner = owner
            page.update()

            async def validate() -> None:
                nonlocal admin_validation_task, admin_validation_owner, admin_modal
                try:
                    result = await asyncio.to_thread(
                        validar_pin_administrativo, contexto_usuario, pin, supabase
                    )
                    if admin_validation_owner is not owner or admin_modal != "pin":
                        return
                    admin_validation_owner = None
                    admin_validation_task = None
                    pin_field.value = ""
                    if result.ok:
                        close_admin_dialog(update=False)
                        show_admin_panel()
                        return
                    submit.disabled = False
                    feedback.value = "No fue posible validar el PIN."
                    feedback.color = ft.Colors.ERROR
                    feedback.visible = True
                    page.update()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    if admin_validation_owner is owner and admin_modal == "pin":
                        admin_validation_owner = None
                        admin_validation_task = None
                        pin_field.value = ""
                        submit.disabled = False
                        feedback.value = "No fue posible validar el PIN."
                        feedback.color = ft.Colors.ERROR
                        feedback.visible = True
                        page.update()

            admin_validation_task = page.run_task(validate)

        submit.on_click = submit_pin
        pin_field.on_submit = submit_pin
        admin_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Acceso administrativo", color=KIOSK_WINE),
            content=ft.Column([pin_field, feedback], tight=True),
            actions=[ft.TextButton("Cancelar", on_click=cancel_pin), submit],
            bgcolor=KIOSK_IVORY,
            data={"kiosk": "admin_pin_dialog"},
        )
        page.show_dialog(admin_dialog)

    def register_admin_logo_tap(_event: Any = None) -> None:
        nonlocal admin_tap_count, admin_tap_started_at
        if state.phase != KioskPhase.WELCOME_SCAN or admin_modal is not None:
            return
        now = monotonic()
        if admin_tap_started_at is None or now - admin_tap_started_at > KIOSK_ADMIN_TAP_WINDOW_SECONDS:
            admin_tap_count = 0
            admin_tap_started_at = now
        admin_tap_count += 1
        if admin_tap_count >= KIOSK_ADMIN_TAP_COUNT:
            show_admin_pin_dialog()

    def active_event() -> tuple[dict[str, Any], tuple[int, int]] | None:
        evento = contexto_usuario.get("evento_actual")
        if not isinstance(evento, dict):
            return None
        try:
            key = (int(evento["cuenta_id"]), int(evento["evento_id"]))
        except (KeyError, TypeError, ValueError):
            return None
        return dict(evento), key

    def resolution_is_current(owner: object, resolution_id: int, event_key: tuple[int, int]) -> bool:
        current = active_event()
        return (
            resolution_owner is owner
            and state.resolution_id == resolution_id
            and state.phase == KioskPhase.RESOLVING
            and current is not None
            and current[1] == event_key
        )

    def cancel_resolution() -> None:
        nonlocal resolution_owner, resolution_task
        state.invalidate_resolution()
        resolution_owner = None
        task = resolution_task
        resolution_task = None
        if task is not None and not task.done():
            task.cancel()

    def confirmation_is_current(
        owner: object,
        confirmation_id: int,
        event_key: tuple[int, int],
        invitation_id: int,
    ) -> bool:
        current = active_event()
        return (
            confirmation_owner is owner
            and state.confirmation_id == confirmation_id
            and state.phase == KioskPhase.CONFIRMING
            and state.cuenta_id == event_key[0]
            and state.evento_id == event_key[1]
            and state.invitation_id == invitation_id
            and current is not None
            and current[1] == event_key
        )

    def cancel_confirmation() -> None:
        nonlocal confirmation_owner, confirmation_task
        state.invalidate_confirmation()
        confirmation_owner = None
        task = confirmation_task
        confirmation_task = None
        if task is not None and not task.done():
            task.cancel()

    def cancel_success_timer() -> None:
        """Cancel the SUCCESS idle timer without affecting the scanner lifecycle."""
        nonlocal success_timer_owner, success_timer_task
        success_timer_owner = None
        task = success_timer_task
        success_timer_task = None
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            current_task = None
        if task is not None and not task.done() and task is not current_task:
            task.cancel()

    def success_timer_is_current(owner: object) -> bool:
        return (
            success_timer_owner is owner
            and viewer_owner is None
            and state.phase == KioskPhase.SUCCESS
            and is_kiosk_route(getattr(page, "route", None))
        )

    def start_success_timer() -> None:
        """Start one fresh idle window for the current SUCCESS screen."""
        nonlocal success_timer_owner, success_timer_task
        if state.phase != KioskPhase.SUCCESS or viewer_owner is not None:
            return
        cancel_success_timer()
        owner = object()
        success_timer_owner = owner

        async def auto_reset_success() -> None:
            nonlocal success_timer_owner, success_timer_task
            try:
                await asyncio.sleep(KIOSK_SUCCESS_RESET_SECONDS)
                if success_timer_is_current(owner):
                    reset_kiosk(for_next_guest=True)
            except asyncio.CancelledError:
                raise
            finally:
                if success_timer_owner is owner:
                    success_timer_owner = None
                    success_timer_task = None

        task = page.run_task(auto_reset_success)
        if success_timer_owner is owner:
            success_timer_task = task

    def route_map_is_current(
        owner: object,
        route_map_generation: int,
        event_key: tuple[int, int],
        invitation_id: int,
    ) -> bool:
        current = active_event()
        return (
            route_map_owner is owner
            and state.route_map_generation == route_map_generation
            and state.phase in {KioskPhase.SELECT_GUESTS, KioskPhase.CONFIRMING, KioskPhase.SUCCESS}
            and state.cuenta_id == event_key[0]
            and state.evento_id == event_key[1]
            and state.invitation_id == invitation_id
            and current is not None
            and current[1] == event_key
        )

    def cancel_route_map() -> None:
        nonlocal route_map_owner, route_map_task
        route_map_owner = None
        task = route_map_task
        route_map_task = None
        state.clear_route_map()
        close_route_map_viewer(reason="cleanup", update=False)
        if task is not None and not task.done():
            task.cancel()

    def viewer_dimensions() -> int:
        try:
            page_width = float(getattr(page, "width", 0) or 0)
        except (TypeError, ValueError, RuntimeError):
            page_width = 0
        return min(1000, max(320, round(page_width - 32))) if page_width else 900

    def viewer_is_current(owner: object) -> bool:
        return (
            viewer_owner is owner
            and state.phase == KioskPhase.SUCCESS
            and state.route_result is not None
            and state.map_preview_ready
            and state.map_preview_src is not None
        )

    def replace_viewer_overlay() -> None:
        nonlocal viewer_overlay
        if viewer_owner is None or state.route_result is None or not state.map_preview_ready or not state.map_preview_src:
            return
        overlay = getattr(page, "overlay", None)
        if not isinstance(overlay, list):
            return
        if viewer_overlay is not None and viewer_overlay in overlay:
            overlay.remove(viewer_overlay)
        viewer_overlay = build_kiosk_route_map_viewer(
            image_url=state.map_preview_src,
            points=state.route_result.points,
            width=viewer_dimensions(),
            zoom=viewer_zoom,
            on_close=lambda _event: close_route_map_viewer(reason="manual"),
            on_zoom_out=lambda _event: set_route_map_viewer_zoom(viewer_zoom - 0.5),
            on_zoom_reset=lambda _event: set_route_map_viewer_zoom(MIN_ZOOM),
            on_zoom_in=lambda _event: set_route_map_viewer_zoom(viewer_zoom + 0.5),
        )
        overlay.append(viewer_overlay)

    def set_route_map_viewer_zoom(target_zoom: float) -> None:
        nonlocal viewer_zoom
        if viewer_owner is None:
            return
        viewer_zoom = max(MIN_ZOOM, min(MAX_ZOOM, round(target_zoom * 2) / 2))
        try:
            replace_viewer_overlay()
        except (TypeError, ValueError) as ex:
            print(f"[KIOSK-MAP] viewer unavailable type={type(ex).__name__}")
            close_route_map_viewer(reason="cleanup", update=False)
            return
        page.update()

    def close_route_map_viewer(*, reason: str, update: bool = True) -> None:
        nonlocal viewer_owner, viewer_timeout_task, viewer_overlay, viewer_zoom
        owner = viewer_owner
        viewer_owner = None
        viewer_zoom = MIN_ZOOM
        timeout_task = viewer_timeout_task
        viewer_timeout_task = None
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            current_task = None
        if timeout_task is not None and not timeout_task.done() and timeout_task is not current_task:
            timeout_task.cancel()
        overlay = getattr(page, "overlay", None)
        if isinstance(overlay, list) and viewer_overlay is not None and viewer_overlay in overlay:
            overlay.remove(viewer_overlay)
        viewer_overlay = None
        if owner is not None and reason in {"manual", "timeout"}:
            print(f"[KIOSK-MAP] viewer closed {reason}")
            if state.phase == KioskPhase.SUCCESS and is_kiosk_route(getattr(page, "route", None)):
                start_success_timer()
        if update:
            page.update()

    def open_route_map_viewer() -> None:
        nonlocal viewer_owner, viewer_timeout_task, viewer_zoom
        if viewer_owner is not None or state.phase != KioskPhase.SUCCESS:
            return
        if state.route_result is None or not state.map_preview_ready or not state.map_preview_src:
            return
        cancel_success_timer()
        viewer_owner = object()
        viewer_zoom = MIN_ZOOM
        owner = viewer_owner
        try:
            replace_viewer_overlay()
        except (TypeError, ValueError) as ex:
            print(f"[KIOSK-MAP] viewer unavailable type={type(ex).__name__}")
            close_route_map_viewer(reason="cleanup", update=False)
            return
        print("[KIOSK-MAP] viewer opened")
        page.update()

        async def auto_close_viewer() -> None:
            nonlocal viewer_timeout_task
            try:
                await asyncio.sleep(15)
                if not viewer_is_current(owner):
                    print("[KIOSK-MAP] viewer stale timeout ignored")
                    return
                close_route_map_viewer(reason="timeout")
            except asyncio.CancelledError:
                raise
            finally:
                if viewer_timeout_task is asyncio.current_task():
                    viewer_timeout_task = None

        viewer_timeout_task = page.run_task(auto_close_viewer)

    def button(label: str, handler: Any, *, primary: bool = True, disabled: bool = False) -> ft.Control:
        control_type = ft.ElevatedButton if primary else ft.OutlinedButton
        style = ft.ButtonStyle(
            text_style=ft.TextStyle(size=18),
            color=ft.Colors.WHITE if primary else KIOSK_WINE,
            bgcolor=KIOSK_WINE if primary else KIOSK_IVORY,
            side=None if primary else ft.BorderSide(width=1, color=KIOSK_WINE),
            shape=ft.RoundedRectangleBorder(radius=16),
        )
        return control_type(
            label,
            on_click=handler,
            disabled=disabled,
            height=56,
            style=style,
        )

    def render() -> None:
        nonlocal has_rendered
        phase = state.phase
        controls: list[ft.Control] = []
        if phase == KioskPhase.WELCOME_SCAN:
            scanner.set_preview_visible(True)
            qr_guide.visible = True
            controls = [
                ft.GestureDetector(
                    content=build_evkor_brand(width=150, text_size=28),
                    on_tap=register_admin_logo_tap,
                    data={"kiosk": "admin_logo_activator"},
                ),
                ft.Text("¡Bienvenidos!", size=34, weight=ft.FontWeight.BOLD, color=KIOSK_WINE),
                ft.Text(
                    "Escanea el código QR de tu invitación",
                    size=22,
                    color=KIOSK_TEXT,
                    text_align=ft.TextAlign.CENTER,
                ),
            ]
        elif phase == KioskPhase.RESOLVING:
            scanner.set_preview_visible(False)
            qr_guide.visible = False
            controls = [
                ft.ProgressRing(width=48, height=48),
                ft.Text("Estamos buscando tu invitación...", size=24, color=KIOSK_TEXT, text_align=ft.TextAlign.CENTER),
            ]
        elif phase == KioskPhase.SELECT_GUESTS:
            scanner.set_preview_visible(False)
            qr_guide.visible = False
            guest_cards_available_width = content_width - 64
            guest_card_width = (
                guest_cards_available_width
                if guest_cards_available_width <= 420
                else round(guest_cards_available_width * 2 / 3)
            )
            guest_controls = []
            for guest in state.guests:
                label = guest.name
                if guest.llegada_confirmada:
                    label = f"{label} — Ya llegó"
                selected = guest.selected
                selectable = guest.selectable
                guest_controls.append(
                    ft.Container(
                        width=guest_card_width,
                        padding=ft.Padding(left=12, top=4, right=12, bottom=4),
                        bgcolor=(KIOSK_BLUSH if selected else KIOSK_IVORY),
                        border=ft.Border.all(
                            width=1,
                            color=(KIOSK_WINE if selected else KIOSK_BORDER),
                        ),
                        border_radius=12,
                        ink=selectable,
                        ink_color=KIOSK_BLUSH,
                        on_click=(
                            (
                                lambda _event, guest_id=guest.guest_id, target_selected=not selected: toggle_guest(
                                    guest_id, target_selected
                                )
                            )
                            if selectable
                            else None
                        ),
                        content=ft.Checkbox(
                            label=label,
                            value=selected,
                            disabled=not selectable,
                            label_style=ft.TextStyle(
                                size=20,
                                color=(KIOSK_WINE if selected else KIOSK_TEXT),
                            ),
                            active_color=KIOSK_WINE,
                            check_color=ft.Colors.WHITE,
                            border_side=ft.BorderSide(width=1, color=KIOSK_BORDER),
                            semantics_label=label,
                            on_change=lambda event, guest_id=guest.guest_id: toggle_guest(
                                guest_id, bool(event.control.value)
                            ),
                        ),
                        data={
                            "kiosk": "guest_card",
                            "guest_id": guest.guest_id,
                            "selectable": selectable,
                        },
                    )
                )
            guest_actions = ft.Row(
                [
                    button("Seleccionar a todos", lambda _event: transition(state.select_all_guests), primary=False),
                    button(
                        "Confirmar llegada",
                        lambda _event: start_confirmation(),
                        disabled=not can_confirm_selection(),
                    ),
                    button(
                        "Volver a escanear",
                        lambda _event: reset_kiosk(for_next_guest=True),
                        primary=False,
                    ),
                ],
                width=content_width - 64,
                alignment=ft.MainAxisAlignment.CENTER,
                wrap=True,
                spacing=12,
                run_spacing=12,
                run_alignment=ft.MainAxisAlignment.CENTER,
                data={"kiosk": "guest_actions"},
            )
            controls = [
                ft.Text(state.destinatario or "Invitación", size=30, weight=ft.FontWeight.BOLD, color=KIOSK_WINE),
                ft.Text(state.table_heading(), size=22, color=KIOSK_TEXT),
                ft.Text(
                    "Selecciona los invitados que te acompañan y confirma su llegada",
                    size=20,
                    color=KIOSK_TEXT,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Column(
                    guest_controls,
                    width=guest_cards_available_width,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    spacing=8,
                    data={"kiosk": "guest_cards"},
                ),
                guest_actions,
            ]
            if state.error_message:
                controls.insert(3, ft.Text(state.error_message, size=18, color=ft.Colors.ERROR, text_align=ft.TextAlign.CENTER))
        elif phase == KioskPhase.CONFIRMING:
            scanner.set_preview_visible(False)
            qr_guide.visible = False
            controls = [
                ft.ProgressRing(width=48, height=48),
                ft.Text(
                    f"Confirmando {len(state.selected_guest_ids)} invitados...",
                    size=24,
                    color=KIOSK_TEXT,
                    text_align=ft.TextAlign.CENTER,
                ),
            ]
        elif phase == KioskPhase.SUCCESS:
            scanner.set_preview_visible(False)
            qr_guide.visible = False
            success_detail = kiosk_success_detail(state.confirmed_count)
            success_controls = [
                *(
                    [ft.Text(f"{state.success_name}:", size=30, weight=ft.FontWeight.BOLD, color=KIOSK_WINE)]
                    if state.success_name
                    else []
                ),
                ft.Text("¡Gracias por acompañarnos!", size=28, weight=ft.FontWeight.BOLD, color=KIOSK_WINE),
                ft.Text(
                    success_detail,
                    size=20,
                    color=KIOSK_TEXT,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    state.success_table_message(),
                    size=32,
                    weight=ft.FontWeight.BOLD,
                    color=KIOSK_WINE,
                    text_align=ft.TextAlign.CENTER,
                    data={"kiosk": "success_table_heading"},
                ),
            ]
            if state.map_preview_ready and state.route_result is not None and state.map_preview_src:
                try:
                    thumbnail_width = min(340, max(200, content_width - 64))
                    success_controls.append(
                        ft.Text(
                            "¿Cómo llegar a su mesa? (toque el mapa)",
                            size=20,
                            color=KIOSK_TEXT,
                            text_align=ft.TextAlign.CENTER,
                            semantics_label="¿Cómo llegar a su mesa? (toque el mapa)",
                            data={"kiosk": "route_map_instruction"},
                        )
                    )
                    success_controls.append(
                        build_kiosk_route_map(
                            image_url=state.map_preview_src,
                            points=state.route_result.points,
                            width=thumbnail_width,
                            overlay_url=state.map_preview_overlay_src,
                            on_click=lambda _event: open_route_map_viewer(),
                            data={"kiosk": "route_map_thumbnail", "width": thumbnail_width},
                        )
                    )
                except (TypeError, ValueError) as ex:
                    print(f"[KIOSK-MAP] unavailable code=MAP_RENDER_ERROR type={type(ex).__name__}")
            success_controls.append(
                button(
                    "Volver a escanear",
                    lambda _event: reset_kiosk(for_next_guest=True),
                    primary=False,
                )
            )
            controls = [
                ft.Container(
                    padding=ft.Padding(left=0, top=48, right=0, bottom=0),
                    content=ft.Column(
                        success_controls,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=12,
                    ),
                    data={"kiosk": "success_content"},
                )
            ]
        else:
            scanner.set_preview_visible(False)
            qr_guide.visible = False
            controls = [
                ft.Icon(ft.Icons.ERROR_OUTLINE, size=64, color=ft.Colors.ERROR),
                ft.Text("No pudimos leer esta invitacion.", size=26, text_align=ft.TextAlign.CENTER),
                ft.Text(state.error_message or "Intenta nuevamente.", size=18, text_align=ft.TextAlign.CENTER),
                button("Intentar nuevamente", lambda _event: reset_kiosk()),
            ]
        screen_content.controls = controls
        if has_rendered:
            page.update()
        has_rendered = True

    def transition(action: Any) -> None:
        action()
        render()

    def toggle_guest(guest_id: int, selected: bool) -> None:
        state.set_guest_selected(guest_id, selected)
        render()

    def selected_guests_for_confirmation(
        *, emit_error: bool = False,
    ) -> tuple[dict[str, Any], tuple[int, int], int, list[dict[str, Any]]] | None:
        if state.phase != KioskPhase.SELECT_GUESTS:
            return None
        if not contexto_usuario.get("puede_registrar_llegadas"):
            if emit_error:
                state.error_message = "Su perfil permite consultar, pero no confirmar llegadas."
            return None
        captured = active_event()
        if captured is None or state.cuenta_id is None or state.evento_id is None or state.invitation_id is None:
            if emit_error:
                state.error_message = "La invitacion actual no es valida. Vuelve a escanear."
            return None
        evento_actual, event_key = captured
        if (
            evento_actual.get("fase_evento") != "En_proceso"
            or evento_actual.get("estado") != "Activo"
        ):
            if emit_error:
                state.error_message = "El evento ya no permite confirmar llegadas."
            return None
        if event_key != (state.cuenta_id, state.evento_id):
            if emit_error:
                state.error_message = "El evento activo cambio. Vuelve a escanear la invitacion."
            return None
        selected = [guest for guest in state.guests if guest.guest_id in state.selected_guest_ids]
        if not selected:
            if emit_error:
                state.error_message = "Selecciona al menos un invitado pendiente para confirmar."
            return None
        if len({guest.guest_id for guest in selected}) != len(state.selected_guest_ids) or any(
            not guest.selectable for guest in selected
        ):
            if emit_error:
                state.selected_guest_ids = {guest.guest_id for guest in selected if guest.selectable}
                for guest in state.guests:
                    guest.selected = guest.guest_id in state.selected_guest_ids
                state.error_message = "La seleccion contiene invitados que ya llegaron. Revisa los pendientes."
            return None
        invitation = {
            "cuenta_id": state.cuenta_id,
            "evento_id": state.evento_id,
            "invitacion_id": state.invitation_id,
            "destinatario": state.destinatario or "",
        }
        invitados = [
            {
                "cuenta_id": state.cuenta_id,
                "evento_id": state.evento_id,
                "invitacion_id": state.invitation_id,
                "invitado_id": guest.guest_id,
            }
            for guest in selected
        ]
        return evento_actual, event_key, state.invitation_id, invitados

    def can_confirm_selection() -> bool:
        return selected_guests_for_confirmation() is not None and confirmation_owner is None

    def start_confirmation() -> None:
        nonlocal confirmation_owner, confirmation_task
        if confirmation_owner is not None or confirmation_task is not None:
            return
        selection = selected_guests_for_confirmation(emit_error=True)
        if selection is None:
            render()
            return
        evento_actual, event_key, invitation_id, invitados = selection
        state.invalidate_confirmation()
        confirmation_id = state.confirmation_id
        owner = object()
        confirmation_owner = owner
        state.error_message = None
        state.phase = KioskPhase.CONFIRMING
        print(
            f"[KIOSK][CONFIRM] confirmation_id={confirmation_id} begin "
            f"invitation_id={invitation_id} selected_count={len(invitados)}"
        )
        render()

        async def confirm() -> None:
            nonlocal confirmation_owner, confirmation_task
            try:
                resultado = await asyncio.to_thread(
                    confirmar_llegadas_invitados,
                    contexto_usuario,
                    {
                        "cuenta_id": event_key[0],
                        "evento_id": event_key[1],
                        "invitacion_id": invitation_id,
                        "destinatario": state.destinatario or "",
                    },
                    invitados,
                    supabase,
                )
                if not confirmation_is_current(owner, confirmation_id, event_key, invitation_id):
                    print(f"[KIOSK][CONFIRM] confirmation_id={confirmation_id} stale_result_discarded")
                    return
                if resultado.ok:
                    state.apply_confirmation_result(
                        resultado.invitados,
                        resultado.confirmados,
                        {int(item["invitado_id"]) for item in invitados},
                    )
                    print(
                        f"[KIOSK][CONFIRM] confirmation_id={confirmation_id} completed "
                        f"confirmed_count={resultado.confirmados}"
                    )
                else:
                    if resultado.invitados:
                        state._apply_guests(resultado.invitados)
                    state.selected_guest_ids.clear()
                    state.confirmed_count = 0
                    if resultado.estado == "connection_error" and not resultado.invitados:
                        state.show_error(resultado.mensaje)
                    else:
                        state.error_message = resultado.mensaje
                        state.phase = KioskPhase.SELECT_GUESTS
                    print(f"[KIOSK][CONFIRM] confirmation_id={confirmation_id} failed code={resultado.estado}")
                render()
                if state.phase == KioskPhase.SUCCESS:
                    start_success_route_map()
                    start_success_timer()
            except asyncio.CancelledError:
                raise
            except Exception as ex:
                if confirmation_is_current(owner, confirmation_id, event_key, invitation_id):
                    state.error_message = "No fue posible confirmar las llegadas. Intenta nuevamente."
                    state.selected_guest_ids.clear()
                    state.phase = KioskPhase.SELECT_GUESTS
                    print(f"[KIOSK][CONFIRM] confirmation_id={confirmation_id} failed code={type(ex).__name__}")
                    render()
            finally:
                if confirmation_owner is owner:
                    confirmation_owner = None
                    confirmation_task = None

        task = page.run_task(confirm)
        if confirmation_owner is owner:
            confirmation_task = task

    def start_resolution(codigo_qr: str, resolution_id: int) -> None:
        nonlocal resolution_owner, resolution_task
        captured = active_event()
        if captured is None:
            state.show_error("Selecciona un evento antes de consultar la invitacion.")
            state.invalidate_resolution()
            render()
            return
        evento_actual, event_key = captured
        owner = object()
        resolution_owner = owner

        async def resolve() -> None:
            nonlocal resolution_owner, resolution_task
            try:
                if not resolution_is_current(owner, resolution_id, event_key):
                    print(f"[KIOSK][RESOLVE] resolution_id={resolution_id} stale_discarded")
                    return
                print(
                    f"[KIOSK][RESOLVE] resolution_id={resolution_id} begin "
                    f"account_id={event_key[0]} event_id={event_key[1]}"
                )
                resolved = await asyncio.to_thread(
                    resolver_invitacion_qr,
                    event_key[0],
                    event_key[1],
                    codigo_qr,
                    supabase,
                )
                if not resolution_is_current(owner, resolution_id, event_key):
                    print(f"[KIOSK][RESOLVE] resolution_id={resolution_id} stale_discarded")
                    return
                if not resolved.ok or resolved.invitacion is None:
                    print(f"[KIOSK][RESOLVE] resolution_id={resolution_id} failed code={resolved.estado}")
                    state.show_error(resolved.mensaje)
                    state.invalidate_resolution()
                    render()
                    return
                print(
                    f"[KIOSK][RESOLVE] resolution_id={resolution_id} qr_resolved "
                    f"invitation_id={resolved.invitacion['invitacion_id']}"
                )
                group = await asyncio.to_thread(
                    cargar_grupo_invitacion,
                    evento_actual,
                    resolved.invitacion,
                    supabase,
                )
                if not resolution_is_current(owner, resolution_id, event_key):
                    print(f"[KIOSK][RESOLVE] resolution_id={resolution_id} stale_discarded")
                    return
                if not group.ok or group.invitacion is None:
                    print(f"[KIOSK][RESOLVE] resolution_id={resolution_id} failed code={group.estado}")
                    state.show_error(group.mensaje)
                    state.invalidate_resolution()
                    render()
                    return
                print(
                    f"[KIOSK][RESOLVE] resolution_id={resolution_id} group_loaded "
                    f"guests={len(group.invitados)}"
                )
                state.apply_group(group.invitacion, group.invitados)
                print(f"[KIOSK][RESOLVE] resolution_id={resolution_id} completed")
                render()
                start_route_map_prefetch()
            except asyncio.CancelledError:
                raise
            except Exception as ex:
                if resolution_is_current(owner, resolution_id, event_key):
                    print(f"[KIOSK][RESOLVE] resolution_id={resolution_id} failed code={type(ex).__name__}")
                    state.show_error("No fue posible consultar la invitacion.")
                    state.invalidate_resolution()
                    render()
            finally:
                if resolution_owner is owner:
                    resolution_owner = None
                    resolution_task = None

        task = page.run_task(resolve)
        if resolution_owner is owner:
            resolution_task = task

    def on_kiosk_qr_finalized(codigo_qr: str) -> None:
        if confirmation_owner is not None:
            return
        resolution_id = state.accept_scanned_qr(codigo_qr)
        if resolution_id is None:
            return
        scanner.set_preview_visible(False)
        render()
        start_resolution(codigo_qr, resolution_id)

    def on_kiosk_camera_error(message: str) -> None:
        cancel_resolution()
        cancel_confirmation()
        cancel_route_map()
        state.show_error(message)
        scanner.set_preview_visible(False)
        render()

    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=on_kiosk_qr_finalized,
        on_camera_error=on_kiosk_camera_error,
        startup_origin=asset_context_ready_at,
        e2e_profiler=e2e_profiler,
    )
    qr_guide = ft.Container(
        width=560,
        height=300,
        alignment=ft.Alignment.CENTER,
        ignore_interactions=True,
        content=ft.Container(
            width=200,
            height=200,
            border=ft.Border.all(width=3, color=KIOSK_WINE),
            border_radius=16,
            ignore_interactions=True,
            data={"kiosk": "qr_distance_guide"},
        ),
        data={"kiosk": "qr_distance_guide_layer"},
    )
    camera_stage = ft.Stack(
        [scanner.host, qr_guide],
        width=560,
        height=300,
        alignment=ft.Alignment.CENTER,
        data={"kiosk": "camera_stage"},
    )
    content = ft.Column(
        [screen_content, camera_stage],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=20,
    )
    try:
        page_width = float(getattr(page, "width", 0) or 0)
    except (TypeError, ValueError, RuntimeError):
        page_width = 0
    is_wide_landscape = page_width >= KIOSK_WIDE_LAYOUT_MIN_WIDTH
    if is_wide_landscape:
        # Preserve both edges of a landscape event background: make the panel
        # modestly narrower and shift it only slightly right of centre.
        content_width = min(
            KIOSK_WIDE_PANEL_MAX_WIDTH,
            max(KIOSK_WIDE_PANEL_MIN_WIDTH, round(page_width * 0.42)),
        )
        foreground_alignment = ft.Alignment(KIOSK_WIDE_PANEL_ALIGNMENT_X, 0)
        layout_variant = "landscape_safe_zone"
    else:
        content_width = min(680, max(280, page_width - 32)) if page_width else 680
        foreground_alignment = ft.Alignment.CENTER
        layout_variant = "centered"
    content_box = ft.Container(
        width=content_width,
        # Keep every screen's functional column clear of the floral art in the
        # panel's upper-right corner without changing individual controls.
        padding=ft.Padding(left=32, top=64, right=32, bottom=32),
        border_radius=24,
        bgcolor=KIOSK_IVORY,
        border=ft.Border.all(width=1, color=KIOSK_BORDER),
        shadow=ft.BoxShadow(
            blur_radius=16,
            spread_radius=0,
            color="#24000000",
            offset=ft.Offset(0, 4),
        ),
        content=content,
        data={"kiosk": "content_box", "width": content_width, "layout": layout_variant},
    )
    foreground = ft.Container(
        expand=True,
        alignment=foreground_alignment,
        content=content_box,
        data={"kiosk": "foreground", "layout": layout_variant},
    )
    root = ft.Container(
        expand=True,
        bgcolor=KIOSK_BACKGROUND_EXTENSION,
        alignment=ft.Alignment.CENTER,
        content=foreground,
        data={"kiosk": "root"},
    )

    def start_background_resolution() -> None:
        nonlocal background_owner, background_task
        captured = active_event()
        if captured is None or supabase is None:
            return
        try:
            storage = supabase.storage
        except (AttributeError, RuntimeError):
            return
        if storage is None:
            return
        _evento, event_key = captured
        kiosk_asset_cache.activate(*event_key)
        owner = object()
        background_owner = owner

        async def resolve_background() -> None:
            nonlocal background_task
            asset = await asyncio.to_thread(
                kiosk_asset_cache.get_or_load,
                supabase,
                event_key[0],
                event_key[1],
                "background",
            )
            current = active_event()
            if asset is None:
                return
            if background_owner is not owner:
                print("[KIOSK-ASSET] stale result ignored asset=background reason=stale_owner")
                return
            if current is None or current[1] != event_key:
                print("[KIOSK-ASSET] stale result ignored asset=background reason=event_changed")
                return
            if not is_kiosk_route(getattr(page, "route", None)):
                print("[KIOSK-ASSET] stale result ignored asset=background reason=route_exit")
                return
            update_started = perf_counter()
            root.image = ft.DecorationImage(
                src=asset.data_url,
                fit=ft.BoxFit.CONTAIN,
                alignment=ft.Alignment.CENTER,
            )
            print(
                "[KIOSK-ASSET] background applied "
                f"account_id={event_key[0]} event_id={event_key[1]} "
                "target=root_container mode=decoration_image fit=contain"
            )
            page.update()
            print(
                "[KIOSK-ASSET][PERF] stage=decoration_update asset=background "
                f"duration_ms={(perf_counter() - update_started) * 1000:.1f} cache_hit={asset.cache_hit}"
            )

        task = page.run_task(resolve_background)
        if background_owner is owner:
            background_task = task

    def start_panel_resolution() -> None:
        nonlocal panel_owner, panel_task
        captured = active_event()
        if captured is None or supabase is None:
            return
        try:
            storage = supabase.storage
        except (AttributeError, RuntimeError):
            return
        if storage is None:
            return
        _evento, event_key = captured
        owner = object()
        panel_owner = owner

        async def resolve_panel() -> None:
            nonlocal panel_task
            asset = await asyncio.to_thread(
                kiosk_asset_cache.get_or_load,
                supabase,
                event_key[0],
                event_key[1],
                "panel",
            )
            current = active_event()
            if asset is None:
                return
            if panel_owner is not owner:
                print("[KIOSK-ASSET] stale result ignored asset=panel reason=stale_owner")
                return
            if current is None or current[1] != event_key:
                print("[KIOSK-ASSET] stale result ignored asset=panel reason=event_changed")
                return
            if not is_kiosk_route(getattr(page, "route", None)):
                print("[KIOSK-ASSET] stale result ignored asset=panel reason=route_exit")
                return
            update_started = perf_counter()
            content_box.image = ft.DecorationImage(
                src=asset.data_url,
                fit=ft.BoxFit.COVER,
                alignment=ft.Alignment.CENTER,
            )
            print(
                "[KIOSK-ASSET] panel applied "
                f"account_id={event_key[0]} event_id={event_key[1]}"
            )
            page.update()
            print(
                "[KIOSK-ASSET][PERF] stage=decoration_update asset=panel "
                f"duration_ms={(perf_counter() - update_started) * 1000:.1f} cache_hit={asset.cache_hit}"
            )

        task = page.run_task(resolve_panel)
        if panel_owner is owner:
            panel_task = task

    def start_route_map_prefetch() -> None:
        """Prepare an invitation route while SELECT_GUESTS remains interactive."""
        nonlocal route_map_owner, route_map_task
        if route_map_owner is not None or route_map_task is not None or state.map_preview_ready:
            return
        mesa_id = state.success_mesa_id()
        captured = active_event()
        if mesa_id is None:
            print("[KIOSK-MAP] unavailable code=MAP_MESA_UNAVAILABLE")
            return
        if captured is None or supabase is None:
            print("[KIOSK-MAP] unavailable code=MAP_CONTEXT_UNAVAILABLE")
            return
        _evento, event_key = captured
        if event_key != (state.cuenta_id, state.evento_id):
            print("[KIOSK-MAP] unavailable code=MAP_CONTEXT_MISMATCH")
            return
        if state.invitation_id is None:
            print("[KIOSK-MAP] unavailable code=MAP_INVITATION_UNAVAILABLE")
            return
        owner = object()
        route_map_owner = owner
        route_map_generation = state.route_map_generation
        invitation_id = state.invitation_id
        state.map_loading = True

        async def prefetch_route_map() -> None:
            nonlocal route_map_owner, route_map_task
            try:
                route_started = perf_counter()
                route_result = await asyncio.to_thread(
                    calcular_ruta,
                    account_id=event_key[0],
                    event_id=event_key[1],
                    mesa_id=mesa_id,
                )
                print(
                    "[KIOSK-MAP][PERF] stage=calcular_ruta "
                    f"duration_ms={(perf_counter() - route_started) * 1000:.1f}"
                )
                if not route_map_is_current(owner, route_map_generation, event_key, invitation_id):
                    print("[KIOSK-MAP] stale task ignored")
                    return
                if not route_result.ok:
                    state.map_loading = False
                    print(f"[KIOSK-MAP] unavailable code={route_result.codigo}")
                    render()
                    return
                if not route_result.storage_bucket or not route_result.storage_path:
                    state.map_loading = False
                    print("[KIOSK-MAP] unavailable code=MAP_STORAGE_PATH_UNAVAILABLE")
                    render()
                    return
                asset = await asyncio.to_thread(
                    map_asset_cache.get_or_load,
                    supabase,
                    route_result.storage_bucket,
                    route_result.storage_path,
                    resolve_url=resolve_kiosk_route_map_url,
                    load_data_url=load_kiosk_route_map_data_url,
                )
                if not route_map_is_current(owner, route_map_generation, event_key, invitation_id):
                    print("[KIOSK-MAP] stale task ignored")
                    return
                if asset is None:
                    state.map_loading = False
                    print("[KIOSK-MAP] unavailable code=MAP_IMAGE_UNAVAILABLE")
                    render()
                    return
                thumbnail_width = min(340, max(200, content_width - 64))
                svg_started = perf_counter()
                overlay_src = build_route_overlay_data_url(
                    route_result.points,
                    width=thumbnail_width,
                    height=round(thumbnail_width * 1535 / 2750),
                )
                print(
                    "[KIOSK-MAP][PERF] stage=generate_svg "
                    f"duration_ms={(perf_counter() - svg_started) * 1000:.1f}"
                )
                if not route_map_is_current(owner, route_map_generation, event_key, invitation_id):
                    print("[KIOSK-MAP] stale task ignored")
                    return
                state.map_loading = False
                publish_started = perf_counter()
                state.route_result = route_result
                state.map_signed_url = asset.signed_url
                state.map_preview_src = asset.data_url
                state.map_preview_overlay_src = overlay_src
                state.map_preview_ready = True
                print(
                    "[KIOSK-MAP][PERF] stage=publish_preview "
                    f"duration_ms={(perf_counter() - publish_started) * 1000:.1f}"
                )
                print(f"[KIOSK-MAP] prefetch ready mesa_id={mesa_id}")
                render()
            except asyncio.CancelledError:
                raise
            except Exception as ex:
                if route_map_is_current(owner, route_map_generation, event_key, invitation_id):
                    state.map_loading = False
                    print(f"[KIOSK-MAP] unavailable code=MAP_LOOKUP_ERROR type={type(ex).__name__}")
                    render()
            finally:
                if route_map_owner is owner:
                    route_map_owner = None
                    route_map_task = None

        task = page.run_task(prefetch_route_map)
        if route_map_owner is owner:
            route_map_task = task

    def start_success_route_map() -> None:
        """Consume SELECT_GUESTS prefetch, or keep its single in-flight task."""
        if state.phase != KioskPhase.SUCCESS:
            return
        if state.map_preview_ready:
            print("[KIOSK-MAP] success using prefetched map")
            return
        if route_map_task is not None or route_map_owner is not None:
            print("[KIOSK-MAP] success awaiting existing prefetch")
            return
        start_route_map_prefetch()

    def reset_kiosk(*, for_next_guest: bool = False) -> None:
        """Reset UI state, choosing fast resume only for a normal guest transition."""
        if confirmation_owner is not None:
            return
        cancel_success_timer()
        cancel_resolution()
        cancel_confirmation()
        cancel_route_map()
        state.reset_kiosk()
        scanner.set_preview_visible(True)
        render()
        if for_next_guest:
            scanner.resume_for_next_guest()
        else:
            scanner.restart()

    def resume_kiosk_after_reconnect() -> None:
        if state.phase != KioskPhase.WELCOME_SCAN:
            print(f"[KIOSK-QR][RECONNECT] skipped phase={state.phase.value}")
            return
        scanner.recover_after_reconnect()

    def pause_kiosk() -> None:
        nonlocal background_owner, background_task, panel_owner, panel_task
        cleanup_admin_access(resume_scanner=False, update=False)
        cancel_success_timer()
        cancel_resolution()
        cancel_confirmation()
        cancel_route_map()
        map_asset_cache.clear()
        kiosk_asset_cache.clear()
        background_owner = None
        task = background_task
        background_task = None
        if task is not None and not task.done():
            task.cancel()
        panel_owner = None
        task = panel_task
        panel_task = None
        if task is not None and not task.done():
            task.cancel()
        scanner.close(disconnected=True)

    def on_route_change(event: ft.RouteChangeEvent) -> None:
        nonlocal background_owner, background_task, panel_owner, panel_task
        if not is_kiosk_route(getattr(event, "route", None) or page.route):
            cleanup_admin_access(resume_scanner=False, update=False)
            restore_page_scroll()
            cancel_success_timer()
            cancel_resolution()
            cancel_confirmation()
            cancel_route_map()
            kiosk_asset_cache.clear()
            map_asset_cache.clear()
            background_owner = None
            task = background_task
            background_task = None
            if task is not None and not task.done():
                task.cancel()
            panel_owner = None
            panel = panel_task
            panel_task = None
            if panel is not None and not panel.done():
                panel.cancel()

            async def leave_kiosk() -> None:
                await scanner.stop_scan()
                if on_authenticated_route_change is not None:
                    on_authenticated_route_change()

            page.run_task(leave_kiosk)

    page.on_route_change = on_route_change
    root.data = {
        "kiosk_state": state,
        "kiosk_scanner": scanner,
        "reset_kiosk": reset_kiosk,
        "retry_camera": reset_kiosk,
        "pause_dashboard": pause_kiosk,
        "resume_dashboard": resume_kiosk_after_reconnect,
        "cancel_resolution": cancel_resolution,
        "cancel_confirmation": cancel_confirmation,
        "cancel_success_timer": cancel_success_timer,
        "start_success_timer": start_success_timer,
        "success_timer_active": lambda: success_timer_owner is not None,
        "cancel_route_map": cancel_route_map,
        "map_asset_cache": map_asset_cache,
        "kiosk_asset_cache": kiosk_asset_cache,
        "open_route_map_viewer": open_route_map_viewer,
        "close_route_map_viewer": close_route_map_viewer,
        "set_route_map_viewer_zoom": set_route_map_viewer_zoom,
        "start_confirmation": start_confirmation,
        "logout_kiosk": on_kiosk_logout,
        "contexto_usuario": contexto_usuario,
        "kiosk_root": root,
        "kiosk_content_box": content_box,
        "kiosk_qr_guide": qr_guide,
        "kiosk_camera_stage": camera_stage,
        "open_admin_pin": show_admin_pin_dialog,
        "admin_logo_tap": register_admin_logo_tap,
        "close_admin_access": cleanup_admin_access,
    }
    render()
    if e2e_profiler is not None:
        e2e_profiler.mark("E7_KIOSK_BUILD_COMPLETE")
    if asset_context_ready_at is not None:
        print(
            "[KIOSK-STARTUP][PERF] stage=T4_build_complete "
            f"total_ms={(perf_counter() - asset_context_ready_at) * 1000:.1f}"
        )
    print(
        "[KIOSK-ASSET][PERF] stage=build_initial "
        f"duration_ms={(perf_counter() - build_started) * 1000:.1f}"
    )
    if asset_context_ready_at is not None:
        print(
            "[KIOSK-ASSET][PERF] stage=context_ready_to_build "
            f"duration_ms={(perf_counter() - asset_context_ready_at) * 1000:.1f}"
        )
    # Scanner startup gets the first scheduled task. Decorative assets are
    # independent and may finish later without changing ready-to-scan.
    scanner.start()
    start_background_resolution()
    start_panel_resolution()
    return root

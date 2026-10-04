from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import flet as ft

from components.kiosk_qr_scanner import KioskQrScanner
from services.navigation_service import parse_app_route


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
    selected: bool = False


@dataclass
class KioskState:
    phase: KioskPhase = KioskPhase.WELCOME_SCAN
    qr_code: str | None = None
    invitation_id: int | None = None
    invitation_name: str | None = None
    table: str | None = None
    guests: list[KioskGuest] = field(default_factory=list)
    selected_guest_ids: set[int] = field(default_factory=set)
    error_message: str | None = None

    def reset_kiosk(self) -> None:
        self.phase = KioskPhase.WELCOME_SCAN
        self.qr_code = None
        self.invitation_id = None
        self.invitation_name = None
        self.table = None
        self.guests.clear()
        self.selected_guest_ids.clear()
        self.error_message = None

    def start_simulated_resolution(self) -> None:
        self.error_message = None
        self.phase = KioskPhase.RESOLVING

    def accept_scanned_qr(self, codigo_qr: str) -> bool:
        if self.phase != KioskPhase.WELCOME_SCAN:
            return False
        self.qr_code = codigo_qr
        self.error_message = None
        self.phase = KioskPhase.RESOLVING
        return True

    def load_demo_invitation(self) -> None:
        self.qr_code = "KIOSK-DEMO"
        self.invitation_id = 1
        self.invitation_name = "Familia Gonzalez"
        self.table = "12"
        self.guests = [
            KioskGuest(1, "Carlos Gonzalez", True),
            KioskGuest(2, "Maria Gonzalez", True),
            KioskGuest(3, "Ana Gonzalez"),
            KioskGuest(4, "Luis Gonzalez"),
        ]
        self.selected_guest_ids = {guest.guest_id for guest in self.guests if guest.selected}
        self.phase = KioskPhase.SELECT_GUESTS

    def set_guest_selected(self, guest_id: int, selected: bool) -> None:
        for guest in self.guests:
            if guest.guest_id == guest_id:
                guest.selected = selected
                if selected:
                    self.selected_guest_ids.add(guest_id)
                else:
                    self.selected_guest_ids.discard(guest_id)
                break

    def select_all_guests(self) -> None:
        for guest in self.guests:
            guest.selected = True
            self.selected_guest_ids.add(guest.guest_id)

    def continue_to_confirmation(self) -> bool:
        if not self.selected_guest_ids:
            self.error_message = "Selecciona al menos una persona para continuar."
            return False
        self.error_message = None
        self.phase = KioskPhase.CONFIRMING
        return True

    def finish_simulated_confirmation(self) -> None:
        self.phase = KioskPhase.SUCCESS

    def show_error(self, message: str = "No pudimos leer esta invitacion.") -> None:
        self.error_message = message
        self.phase = KioskPhase.ERROR


def is_kiosk_route(route: str | None) -> bool:
    return parse_app_route(route)[0] == "kiosk"


def build_kiosk_view(
    *,
    page: ft.Page,
    contexto_usuario: dict[str, Any],
    on_authenticated_route_change: Callable[[], None] | None = None,
) -> ft.Control:
    """Build the self-contained kiosk shell; camera and backend integration come later."""
    state = KioskState()
    screen_content = ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=20)

    def on_kiosk_qr_finalized(codigo_qr: str) -> None:
        if not state.accept_scanned_qr(codigo_qr):
            return
        scanner.set_preview_visible(False)
        render()

    def on_kiosk_camera_error(message: str) -> None:
        state.show_error(message)
        scanner.set_preview_visible(False)
        render()

    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=on_kiosk_qr_finalized,
        on_camera_error=on_kiosk_camera_error,
    )
    content = ft.Column(
        [screen_content, scanner.host],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=20,
    )
    root = ft.Container(
        expand=True,
        padding=32,
        bgcolor=ft.Colors.SURFACE,
        alignment=ft.Alignment.CENTER,
        content=ft.Container(
            width=720,
            padding=32,
            border_radius=24,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            content=content,
        ),
    )
    has_rendered = False

    def button(label: str, handler: Any, *, primary: bool = True) -> ft.Control:
        control_type = ft.ElevatedButton if primary else ft.OutlinedButton
        return control_type(
            label,
            on_click=handler,
            height=56,
            style=ft.ButtonStyle(text_style=ft.TextStyle(size=18)),
        )

    def render() -> None:
        nonlocal has_rendered
        phase = state.phase
        controls: list[ft.Control] = []
        if phase == KioskPhase.WELCOME_SCAN:
            scanner.set_preview_visible(True)
            controls = [
                ft.Text("Bienvenido", size=34, weight=ft.FontWeight.BOLD),
                ft.Text("Escanea el codigo QR de tu invitacion", size=22, text_align=ft.TextAlign.CENTER),
                ft.TextButton("Ayuda", on_click=lambda _event: None),
            ]
        elif phase == KioskPhase.RESOLVING:
            scanner.set_preview_visible(False)
            controls = [
                ft.ProgressRing(width=48, height=48),
                ft.Text("Estamos buscando tu invitacion...", size=24, text_align=ft.TextAlign.CENTER),
                button("Continuar demo (simulacion)", lambda _event: transition(state.load_demo_invitation)),
            ]
        elif phase == KioskPhase.SELECT_GUESTS:
            scanner.set_preview_visible(False)
            guest_controls = [
                ft.Checkbox(
                    label=guest.name,
                    value=guest.selected,
                    label_style=ft.TextStyle(size=20),
                    on_change=lambda event, guest_id=guest.guest_id: toggle_guest(guest_id, bool(event.control.value)),
                )
                for guest in state.guests
            ]
            controls = [
                ft.Text(state.invitation_name or "Invitacion", size=30, weight=ft.FontWeight.BOLD),
                ft.Text(f"Mesa {state.table or '-'}", size=22),
                ft.Text("Quienes llegaron?", size=20),
                *guest_controls,
                ft.Text(state.error_message or "", color=ft.Colors.ERROR, visible=bool(state.error_message)),
                button("Todos llegaron", lambda _event: transition(state.select_all_guests), primary=False),
                button("Continuar", lambda _event: continue_confirmation()),
            ]
        elif phase == KioskPhase.CONFIRMING:
            scanner.set_preview_visible(False)
            controls = [
                ft.ProgressRing(width=48, height=48),
                ft.Text("Confirmando llegada...", size=24),
                button("Completar simulacion", lambda _event: transition(state.finish_simulated_confirmation)),
            ]
        elif phase == KioskPhase.SUCCESS:
            scanner.set_preview_visible(False)
            controls = [
                ft.Icon(ft.Icons.CHECK_CIRCLE_OUTLINE, size=72, color=ft.Colors.GREEN),
                ft.Text("Bienvenidos!", size=34, weight=ft.FontWeight.BOLD),
                ft.Text(f"Mesa {state.table or '-'}", size=26),
                ft.Text("Que disfruten el evento.", size=20),
                button("Finalizar / Volver al inicio", lambda _event: reset_kiosk()),
            ]
        else:
            scanner.set_preview_visible(False)
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

    def continue_confirmation() -> None:
        state.continue_to_confirmation()
        render()

    def reset_kiosk() -> None:
        state.reset_kiosk()
        scanner.set_preview_visible(True)
        render()
        scanner.restart()

    def on_route_change(event: ft.RouteChangeEvent) -> None:
        if not is_kiosk_route(getattr(event, "route", None) or page.route):
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
        "pause_dashboard": scanner.close,
        "contexto_usuario": contexto_usuario,
    }
    render()
    scanner.start()
    return root

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

import flet as ft

from components.kiosk_qr_scanner import KioskQrScanner
from services.invitado_service import cargar_grupo_invitacion, resolver_invitacion_qr
from services.navigation_service import parse_app_route


class KioskPhase(str, Enum):
    WELCOME_SCAN = "WELCOME_SCAN"
    RESOLVING = "RESOLVING"
    SELECT_GUESTS = "SELECT_GUESTS"
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

    def _clear_invitation(self) -> None:
        self.cuenta_id = None
        self.evento_id = None
        self.invitation_id = None
        self.destinatario = None
        self.guests.clear()
        self.selected_guest_ids.clear()

    def invalidate_resolution(self) -> None:
        self.resolution_id += 1

    def reset_kiosk(self) -> None:
        self.invalidate_resolution()
        self.phase = KioskPhase.WELCOME_SCAN
        self.qr_code = None
        self._clear_invitation()
        self.error_message = None

    def accept_scanned_qr(self, codigo_qr: str) -> int | None:
        if self.phase != KioskPhase.WELCOME_SCAN:
            return None
        self.invalidate_resolution()
        self.qr_code = codigo_qr
        self._clear_invitation()
        self.error_message = None
        self.phase = KioskPhase.RESOLVING
        return self.resolution_id

    def apply_group(self, invitacion: dict[str, Any], invitados: list[dict[str, Any]]) -> None:
        self.cuenta_id = int(invitacion["cuenta_id"])
        self.evento_id = int(invitacion["evento_id"])
        self.invitation_id = int(invitacion["invitacion_id"])
        self.destinatario = str(invitacion["destinatario"])
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
        self.selected_guest_ids.clear()
        self.qr_code = None
        self.error_message = None
        self.phase = KioskPhase.SELECT_GUESTS

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


def is_kiosk_route(route: str | None) -> bool:
    return parse_app_route(route)[0] == "kiosk"


def build_kiosk_view(
    *,
    page: ft.Page,
    contexto_usuario: dict[str, Any],
    supabase: Any = None,
    on_authenticated_route_change: Callable[[], None] | None = None,
) -> ft.Control:
    """Build the Kiosk shell and resolve accepted QR codes through existing read services."""
    state = KioskState()
    screen_content = ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=20)
    resolution_task: Any = None
    resolution_owner: object | None = None
    has_rendered = False

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
            ]
        elif phase == KioskPhase.SELECT_GUESTS:
            scanner.set_preview_visible(False)
            guest_controls = []
            for guest in state.guests:
                label = guest.name
                if guest.llegada_confirmada:
                    label = f"{label} — Ya llegó"
                guest_controls.append(
                    ft.Checkbox(
                        label=label,
                        value=guest.selected,
                        disabled=not guest.selectable,
                        label_style=ft.TextStyle(size=20),
                        on_change=lambda event, guest_id=guest.guest_id: toggle_guest(
                            guest_id, bool(event.control.value)
                        ),
                    )
                )
            controls = [
                ft.Text(state.destinatario or "Invitacion", size=30, weight=ft.FontWeight.BOLD),
                ft.Text(state.table_heading(), size=22),
                ft.Text("Selecciona los integrantes pendientes", size=20),
                *guest_controls,
                button("Seleccionar pendientes", lambda _event: transition(state.select_all_guests), primary=False),
                button("Volver a escanear", lambda _event: reset_kiosk(), primary=False),
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
        resolution_id = state.accept_scanned_qr(codigo_qr)
        if resolution_id is None:
            return
        scanner.set_preview_visible(False)
        render()
        start_resolution(codigo_qr, resolution_id)

    def on_kiosk_camera_error(message: str) -> None:
        cancel_resolution()
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

    def reset_kiosk() -> None:
        cancel_resolution()
        state.reset_kiosk()
        scanner.set_preview_visible(True)
        render()
        scanner.restart()

    def resume_kiosk_after_reconnect() -> None:
        if state.phase != KioskPhase.WELCOME_SCAN:
            print(f"[KIOSK-QR][RECONNECT] skipped phase={state.phase.value}")
            return
        scanner.recover_after_reconnect()

    def pause_kiosk() -> None:
        cancel_resolution()
        scanner.close(disconnected=True)

    def on_route_change(event: ft.RouteChangeEvent) -> None:
        if not is_kiosk_route(getattr(event, "route", None) or page.route):
            cancel_resolution()

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
        "contexto_usuario": contexto_usuario,
    }
    render()
    scanner.start()
    return root

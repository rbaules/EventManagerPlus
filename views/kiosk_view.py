from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable
from urllib.parse import urlparse

import flet as ft

from components.kiosk_qr_scanner import KioskQrScanner
from services.invitado_service import (
    cargar_grupo_invitacion,
    confirmar_llegadas_invitados,
    resolver_invitacion_qr,
)
from services.kiosk_background_service import resolve_kiosk_background_url
from services.navigation_service import parse_app_route


KIOSK_WINE = "#971B1F"
KIOSK_WINE_DARK = "#731116"
KIOSK_IVORY = "#F8F1E8"
KIOSK_BLUSH = "#F3D9D0"
KIOSK_TEXT = "#4B241C"
KIOSK_BORDER = "#D9C7BC"

# This path is relative to Flet's configured ``assets_dir="assets"``. Keep the
# panel decoration independent from the signed, event-level background image.
KIOSK_PANEL_FLORAL_ASSET = "kiosk_panel_floral.png"


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

    state = KioskState()
    screen_content = ft.Column(horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=20)
    resolution_task: Any = None
    resolution_owner: object | None = None
    confirmation_task: Any = None
    confirmation_owner: object | None = None
    background_task: Any = None
    background_owner: object | None = None
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
                    button("Volver a escanear", lambda _event: reset_kiosk(), primary=False),
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
            success_detail, success_welcome = kiosk_success_copy(state.confirmed_count)
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
                ft.Text(success_welcome, size=32, weight=ft.FontWeight.BOLD, color=KIOSK_WINE),
                ft.Text(state.table_heading(), size=18, color=KIOSK_TEXT),
                button("Volver a escanear", lambda _event: reset_kiosk(), primary=False),
            ]
            controls = [
                ft.Container(
                    padding=ft.Padding(left=0, top=96, right=0, bottom=0),
                    content=ft.Column(
                        success_controls,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=20,
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
        state.show_error(message)
        scanner.set_preview_visible(False)
        render()

    scanner = KioskQrScanner(
        page=page,
        on_qr_finalized=on_kiosk_qr_finalized,
        on_camera_error=on_kiosk_camera_error,
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
    content_width = min(680, max(280, page_width - 32)) if page_width else 680
    content_box = ft.Container(
        width=content_width,
        # Keep every screen's functional column clear of the floral art in the
        # panel's upper-right corner without changing individual controls.
        padding=ft.Padding(left=32, top=64, right=32, bottom=32),
        border_radius=24,
        bgcolor=KIOSK_IVORY,
        image=ft.DecorationImage(
            src=KIOSK_PANEL_FLORAL_ASSET,
            fit=ft.BoxFit.COVER,
            alignment=ft.Alignment.CENTER,
        ),
        border=ft.Border.all(width=1, color=KIOSK_BORDER),
        shadow=ft.BoxShadow(
            blur_radius=16,
            spread_radius=0,
            color="#24000000",
            offset=ft.Offset(0, 4),
        ),
        content=content,
        data={"kiosk": "content_box", "width": content_width},
    )
    foreground = ft.Container(
        expand=True,
        alignment=ft.Alignment.CENTER,
        content=content_box,
    )
    root = ft.Container(
        expand=True,
        bgcolor=ft.Colors.SURFACE,
        padding=16,
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
        owner = object()
        background_owner = owner

        async def resolve_background() -> None:
            nonlocal background_task
            url = await asyncio.to_thread(
                resolve_kiosk_background_url,
                supabase,
                event_key[0],
                event_key[1],
            )
            current = active_event()
            if url is None:
                print(
                    "[KIOSK-BG] fallback reason=signed_url_unavailable "
                    f"account_id={event_key[0]} event_id={event_key[1]}"
                )
                return
            if background_owner is not owner:
                print("[KIOSK-BG] result_discarded reason=stale_owner")
                return
            if current is None or current[1] != event_key:
                print("[KIOSK-BG] result_discarded reason=event_changed")
                return
            if not is_kiosk_route(getattr(page, "route", None)):
                print("[KIOSK-BG] result_discarded reason=route_exit")
                return
            parsed_url = urlparse(url)
            path_parts = [part for part in parsed_url.path.split("/") if part]
            path_suffix = (
                "/" + "/".join(path_parts[-2:])
                if len(path_parts) >= 2
                else parsed_url.path or "/"
            )
            print(
                "[KIOSK-BG] url_metadata "
                f"scheme={parsed_url.scheme or '<missing>'} "
                f"host={parsed_url.hostname or '<missing>'} "
                f"path_suffix={path_suffix} url_length={len(url)}"
            )
            root.image = ft.DecorationImage(
                src=url,
                fit=ft.BoxFit.CONTAIN,
                alignment=ft.Alignment.CENTER,
            )
            print(
                "[KIOSK-BG] applied "
                f"account_id={event_key[0]} event_id={event_key[1]} "
                "target=root_container mode=decoration_image fit=contain"
            )
            print("[KIOSK-BG] update_begin")
            page.update()
            print("[KIOSK-BG] update_complete")

        task = page.run_task(resolve_background)
        if background_owner is owner:
            background_task = task

    def reset_kiosk() -> None:
        if confirmation_owner is not None:
            return
        cancel_resolution()
        cancel_confirmation()
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
        cancel_confirmation()
        scanner.close(disconnected=True)

    def on_route_change(event: ft.RouteChangeEvent) -> None:
        nonlocal background_owner, background_task
        if not is_kiosk_route(getattr(event, "route", None) or page.route):
            restore_page_scroll()
            cancel_resolution()
            cancel_confirmation()
            background_owner = None
            task = background_task
            background_task = None
            if task is not None and not task.done():
                task.cancel()

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
        "start_confirmation": start_confirmation,
        "contexto_usuario": contexto_usuario,
        "kiosk_root": root,
        "kiosk_content_box": content_box,
        "kiosk_qr_guide": qr_guide,
        "kiosk_camera_stage": camera_stage,
    }
    render()
    start_background_resolution()
    scanner.start()
    return root

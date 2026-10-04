from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.navigation_service import parse_app_route
from views.kiosk_view import KioskPhase, KioskState, is_kiosk_route


def test_route() -> None:
    assert is_kiosk_route("/app/kiosk")
    assert is_kiosk_route("/app/kiosk?demo=1")
    assert parse_app_route("/app/kiosk")[0] == "kiosk"
    assert not is_kiosk_route("/app/dashboard")


def test_simulated_happy_path_and_selection() -> None:
    state = KioskState()
    assert state.phase == KioskPhase.WELCOME_SCAN
    state.start_simulated_resolution()
    assert state.phase == KioskPhase.RESOLVING
    state.load_demo_invitation()
    assert state.phase == KioskPhase.SELECT_GUESTS
    assert state.invitation_name == "Familia Gonz\\u00e1lez"
    assert state.table == "12"
    assert state.selected_guest_ids == {1, 2}
    state.set_guest_selected(1, False)
    assert state.selected_guest_ids == {2}
    state.select_all_guests()
    assert state.selected_guest_ids == {1, 2, 3, 4}
    assert state.continue_to_confirmation()
    assert state.phase == KioskPhase.CONFIRMING
    state.finish_simulated_confirmation()
    assert state.phase == KioskPhase.SUCCESS
    state.reset_kiosk()
    assert state.phase == KioskPhase.WELCOME_SCAN


def test_cannot_continue_without_guests() -> None:
    state = KioskState()
    state.load_demo_invitation()
    for guest in state.guests:
        state.set_guest_selected(guest.guest_id, False)
    assert not state.continue_to_confirmation()
    assert state.phase == KioskPhase.SELECT_GUESTS
    assert state.error_message == "Selecciona al menos una persona para continuar."


def test_error_and_reset() -> None:
    state = KioskState()
    state.show_error()
    assert state.phase == KioskPhase.ERROR
    state.reset_kiosk()
    assert state.phase == KioskPhase.WELCOME_SCAN
    state.load_demo_invitation()
    state.reset_kiosk()
    assert state.phase == KioskPhase.WELCOME_SCAN
    assert state.qr_code is None
    assert state.invitation_id is None
    assert state.invitation_name is None
    assert state.table is None
    assert state.guests == []
    assert state.selected_guest_ids == set()
    assert state.error_message is None


def main() -> None:
    test_route()
    test_simulated_happy_path_and_selection()
    test_cannot_continue_without_guests()
    test_error_and_reset()
    print("Kiosk view tests passed.")


if __name__ == "__main__":
    main()

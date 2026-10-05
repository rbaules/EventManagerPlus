from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.navigation_service import parse_app_route
import views.kiosk_view as kiosk_view
from views.kiosk_view import KioskPhase, KioskState, is_kiosk_route


class FakePage:
    def __init__(self) -> None:
        self.route = "/app/kiosk"
        self.on_route_change = None
        self.update_calls = 0

    def update(self) -> None:
        self.update_calls += 1


class FakeKioskScanner:
    def __init__(self, **_kwargs) -> None:
        self.host = None
        self.start_calls = 0
        self.restart_calls = 0
        self.recover_calls = 0
        self.preview_visible: list[bool] = []

    def set_preview_visible(self, visible: bool) -> None:
        self.preview_visible.append(visible)

    def start(self) -> None:
        self.start_calls += 1

    def restart(self) -> None:
        self.restart_calls += 1

    def recover_after_reconnect(self) -> None:
        self.recover_calls += 1

    def close(self) -> None:
        pass


def test_route() -> None:
    assert is_kiosk_route("/app/kiosk")
    assert is_kiosk_route("/app/kiosk?demo=1")
    assert parse_app_route("/app/kiosk")[0] == "kiosk"
    assert not is_kiosk_route("/app/dashboard")


def test_simulated_happy_path_and_selection() -> None:
    state = KioskState()
    assert state.phase == KioskPhase.WELCOME_SCAN
    assert state.accept_scanned_qr("T3A1")
    assert state.phase == KioskPhase.RESOLVING
    assert state.qr_code == "T3A1"
    assert not state.accept_scanned_qr("T3A2")
    state.load_demo_invitation()
    assert state.phase == KioskPhase.SELECT_GUESTS
    assert state.invitation_name == "Familia Gonzalez"
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


def test_reconnect_is_limited_to_welcome_scan() -> None:
    original_scanner = kiosk_view.KioskQrScanner
    kiosk_view.KioskQrScanner = FakeKioskScanner
    try:
        root = kiosk_view.build_kiosk_view(page=FakePage(), contexto_usuario={})
        state = root.data["kiosk_state"]
        scanner = root.data["kiosk_scanner"]
        resume = root.data["resume_dashboard"]

        resume()
        assert scanner.recover_calls == 1
        assert state.accept_scanned_qr("T3A1")
        assert state.phase == KioskPhase.RESOLVING
        resume()
        assert scanner.recover_calls == 1
    finally:
        kiosk_view.KioskQrScanner = original_scanner


def main() -> None:
    test_route()
    test_simulated_happy_path_and_selection()
    test_cannot_continue_without_guests()
    test_error_and_reset()
    test_reconnect_is_limited_to_welcome_scan()
    print("Kiosk view tests passed.")


if __name__ == "__main__":
    main()

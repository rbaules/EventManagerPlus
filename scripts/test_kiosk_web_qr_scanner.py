from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from components.kiosk_scanner_factory import create_kiosk_scanner, kiosk_scanner_mode
from components.kiosk_web_qr_scanner import KioskWebQrScanner


class FakePage:
    route = "/kiosk"

    def update(self) -> None:
        pass


def _scanner() -> tuple[KioskWebQrScanner, list[str], list[str]]:
    accepted: list[str] = []
    errors: list[str] = []
    scanner = KioskWebQrScanner(
        page=FakePage(),
        on_qr_finalized=accepted.append,
        on_camera_error=errors.append,
    )
    return scanner, accepted, errors


def test_mode_defaults_to_legacy_and_web_is_explicit() -> None:
    assert kiosk_scanner_mode("") == "legacy"
    assert kiosk_scanner_mode("legacy") == "legacy"
    assert kiosk_scanner_mode("web") == "web"


def test_factory_creates_web_adapter_only_when_selected() -> None:
    scanner = create_kiosk_scanner(
        mode="web", page=FakePage(), on_qr_finalized=lambda _: None, on_camera_error=lambda _: None
    )
    assert isinstance(scanner, KioskWebQrScanner)


def test_first_web_qr_closes_gate_and_duplicate_is_ignored() -> None:
    scanner, accepted, _ = _scanner()
    scanner.start()
    scanner._on_qr_detected(SimpleNamespace(data="QR-ONE"))
    scanner._on_qr_detected(SimpleNamespace(data="QR-LATE"))
    assert accepted == ["QR-ONE"]
    assert scanner.active is True
    assert scanner.detector_enabled is False


def test_next_guest_admin_and_close_follow_persistent_lifecycle() -> None:
    scanner, _, _ = _scanner()
    identity = (id(scanner), id(scanner.probe), id(scanner.host))
    scanner.start()
    scanner.pause_detection()
    assert scanner.active is True and scanner.detector_enabled is False
    scanner.resume_for_next_guest()
    assert (scanner.generation, scanner.active, scanner.detector_enabled, scanner.preview_visible) == (1, True, True, True)
    asyncio.run(scanner.suspend_for_admin())
    assert scanner.active is True and scanner.detector_enabled is False and scanner.preview_visible is False
    assert scanner._gate_open is False
    assert (scanner.host.width, scanner.host.height, scanner.host.opacity, scanner.host.ignore_interactions) == (560, 300, 0, True)
    asyncio.run(scanner.resume_after_admin())
    assert scanner.active is True and scanner.detector_enabled is True and scanner.preview_visible is True
    assert scanner._gate_open is True
    assert scanner.generation == 1
    assert (scanner.host.width, scanner.host.height, scanner.host.opacity, scanner.host.ignore_interactions) == (560, 300, 1, False)
    assert (id(scanner), id(scanner.probe), id(scanner.host)) == identity
    scanner.close()
    assert scanner.active is False and scanner.detector_enabled is False

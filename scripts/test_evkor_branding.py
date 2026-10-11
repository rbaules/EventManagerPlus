from __future__ import annotations

import sys
from pathlib import Path

import flet as ft


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from components.evkor_brand import (
    EVKOR_LOGO_ASSET,
    EVKOR_TRANSPARENT_LOGO_ASSET,
    build_evkor_brand,
)


def test_brand_control_uses_only_the_approved_evkor_paths() -> None:
    assert EVKOR_LOGO_ASSET == "brand/evkor_logo.png"
    assert EVKOR_TRANSPARENT_LOGO_ASSET == "brand/evkor_logo_transparent.png"

    control = build_evkor_brand(width=220)
    approved_logo = ROOT / "assets" / EVKOR_TRANSPARENT_LOGO_ASSET
    if approved_logo.is_file():
        assert isinstance(control, ft.Image)
        assert control.src == EVKOR_TRANSPARENT_LOGO_ASSET
    else:
        assert isinstance(control, ft.Text)
        assert control.value == "EVKOR"


def test_visible_entry_points_do_not_reference_the_old_logo() -> None:
    login_source = (ROOT / "views" / "login_view.py").read_text(encoding="utf-8")
    header_source = (ROOT / "components" / "event_header.py").read_text(encoding="utf-8")
    kiosk_login_source = (ROOT / "views" / "kiosk_login_view.py").read_text(encoding="utf-8")
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")

    assert "EventPlus_logo" not in login_source
    assert "EventPlus_logo" not in header_source
    assert "build_evkor_brand" in login_source
    assert "build_evkor_brand" in header_source
    assert 'title="EVKOR Kiosco"' in kiosk_login_source
    assert 'page.title = f"EVKOR - {APP_MODE} {APP_VERSION}"' in app_source


def test_visible_oauth_callback_and_user_messages_use_evkor() -> None:
    callback_source = (ROOT / "services" / "auth_service.py").read_text(encoding="utf-8")
    login_source = (ROOT / "views" / "login_view.py").read_text(encoding="utf-8")

    assert "<title>EVKOR - Login completado</title>" in callback_source
    assert "volver a EVKOR" in callback_source
    assert "EventPlus esta preparando" not in login_source
    assert "EVKOR esta preparando" in login_source


def main() -> None:
    test_brand_control_uses_only_the_approved_evkor_paths()
    test_visible_entry_points_do_not_reference_the_old_logo()
    test_visible_oauth_callback_and_user_messages_use_evkor()
    print("EVKOR branding tests passed.")


if __name__ == "__main__":
    main()

from __future__ import annotations

import os
from typing import Any

from components.kiosk_qr_scanner import KioskQrScanner


def kiosk_scanner_mode(value: str | None = None) -> str:
    mode = (value if value is not None else os.getenv("KIOSK_SCANNER_MODE", "legacy")).strip().lower()
    return mode if mode in {"legacy", "web"} else "legacy"


def create_kiosk_scanner(*, mode: str | None = None, **kwargs: Any) -> Any:
    if kiosk_scanner_mode(mode) == "web":
        from components.kiosk_web_qr_scanner import KioskWebQrScanner
        return KioskWebQrScanner(**kwargs)
    return KioskQrScanner(**kwargs)

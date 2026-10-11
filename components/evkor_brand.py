"""Reusable visual identity control for EVKOR-facing screens."""

from __future__ import annotations

from pathlib import Path

import flet as ft


EVKOR_LOGO_ASSET = "brand/evkor_logo.png"
EVKOR_TRANSPARENT_LOGO_ASSET = "brand/evkor_logo_transparent.png"
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


def _asset_is_available(asset_path: str) -> bool:
    """Use approved artwork only when it is packaged with the application."""
    return (_ASSETS_DIR / asset_path).is_file()


def build_evkor_brand(
    *,
    width: float | int | None = None,
    text_size: float | int = 32,
) -> ft.Control:
    """Build EVKOR branding, preferring its approved transparent logo.

    Until the approved artwork is supplied, plain text avoids reusing the
    former EventPlus artwork or fabricating a replacement logo.
    """
    if _asset_is_available(EVKOR_TRANSPARENT_LOGO_ASSET):
        return ft.Image(
            src=EVKOR_TRANSPARENT_LOGO_ASSET,
            width=width,
            fit=ft.BoxFit.CONTAIN,
            data={"brand": "evkor", "asset": EVKOR_TRANSPARENT_LOGO_ASSET},
        )

    return ft.Text(
        "EVKOR",
        size=text_size,
        weight=ft.FontWeight.BOLD,
        color="#971B1F",
        text_align=ft.TextAlign.CENTER,
        data={"brand": "evkor", "asset": None},
    )

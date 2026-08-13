from __future__ import annotations

from enum import StrEnum
from math import isfinite
from typing import Any


PHONE_LARGE_MIN_WIDTH = 600
TABLET_PORTRAIT_MIN_WIDTH = 768
TABLET_LANDSCAPE_MIN_WIDTH = 992
DESKTOP_WIDE_MIN_WIDTH = 1200
DEFAULT_LAYOUT_WIDTH = DESKTOP_WIDE_MIN_WIDTH


class LayoutMode(StrEnum):
    PHONE = "phone"
    PHONE_LARGE = "phone_large"
    TABLET_PORTRAIT = "tablet_portrait"
    TABLET_LANDSCAPE = "tablet_landscape"
    DESKTOP_WIDE = "desktop_wide"


def normalized_width(width: Any) -> float:
    try:
        value = float(width)
    except (TypeError, ValueError):
        return float(DEFAULT_LAYOUT_WIDTH)
    if not isfinite(value):
        return float(DEFAULT_LAYOUT_WIDTH)
    return value if value >= 0 else 0.0


def layout_mode(width: Any) -> LayoutMode:
    value = normalized_width(width)
    if value < PHONE_LARGE_MIN_WIDTH:
        return LayoutMode.PHONE
    if value < TABLET_PORTRAIT_MIN_WIDTH:
        return LayoutMode.PHONE_LARGE
    if value < TABLET_LANDSCAPE_MIN_WIDTH:
        return LayoutMode.TABLET_PORTRAIT
    if value < DESKTOP_WIDE_MIN_WIDTH:
        return LayoutMode.TABLET_LANDSCAPE
    return LayoutMode.DESKTOP_WIDE


def uses_operational_cards(mode: LayoutMode) -> bool:
    return mode in {LayoutMode.PHONE, LayoutMode.PHONE_LARGE}

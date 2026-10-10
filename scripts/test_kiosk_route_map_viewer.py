from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import flet as ft

from components.kiosk_route_map_viewer import MAX_ZOOM, MIN_ZOOM, build_kiosk_route_map_viewer


def walk(control: object) -> list[object]:
    nodes = [control]
    content = getattr(control, "content", None)
    if content is not None:
        nodes.extend(walk(content))
    for child in getattr(control, "controls", None) or []:
        nodes.extend(walk(child))
    return nodes


def test_viewer_uses_installed_interactive_viewer_and_explicit_controls() -> None:
    calls: list[str] = []
    viewer = build_kiosk_route_map_viewer(
        image_url="https://example.invalid/floorplan.jpg",
        points=((0.1, 0.2), (0.9, 0.8)),
        width=900,
        zoom=MIN_ZOOM,
        on_close=lambda _event: calls.append("close"),
        on_zoom_out=lambda _event: calls.append("out"),
        on_zoom_reset=lambda _event: calls.append("reset"),
        on_zoom_in=lambda _event: calls.append("in"),
    )
    nodes = walk(viewer)
    interactive = next(node for node in nodes if isinstance(node, ft.InteractiveViewer))
    assert interactive.pan_enabled and interactive.scale_enabled
    assert (interactive.min_scale, interactive.max_scale) == (MIN_ZOOM, MAX_ZOOM)
    zoom_controls = next(
        node
        for node in nodes
        if getattr(node, "data", None) == {"kiosk": "route_map_viewer_zoom_controls", "zoom": 1.0}
    )
    assert len(zoom_controls.controls) == 3
    close = next(node for node in nodes if getattr(node, "data", None) == {"kiosk": "route_map_viewer_close"})
    close.on_click(SimpleNamespace())
    assert calls == ["close"]
    assert any(
        getattr(node, "data", None) == {"kiosk": "route_map_viewer_map", "width": 900}
        for node in nodes
    )
    stack = next(node for node in nodes if getattr(node, "data", None) == {"kiosk": "route_map_viewer_stack"})
    assert interactive in stack.controls
    close_anchor = next(node for node in stack.controls if getattr(node, "data", None) == {"kiosk": "route_map_viewer_close_anchor"})
    assert close_anchor is not interactive and close_anchor.width == 48 and close_anchor.height == 48


def test_viewer_rejects_invalid_zoom() -> None:
    try:
        build_kiosk_route_map_viewer(
            image_url="https://example.invalid/floorplan.jpg",
            points=((0.1, 0.2), (0.9, 0.8)),
            width=900,
            zoom=3.0,
            on_close=lambda _event: None,
            on_zoom_out=lambda _event: None,
            on_zoom_reset=lambda _event: None,
            on_zoom_in=lambda _event: None,
        )
    except ValueError:
        return
    raise AssertionError("El visor debe limitar el zoom")


def main() -> None:
    test_viewer_uses_installed_interactive_viewer_and_explicit_controls()
    test_viewer_rejects_invalid_zoom()
    print("Kiosk route-map viewer tests passed.")


if __name__ == "__main__":
    main()

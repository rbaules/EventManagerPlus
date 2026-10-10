from __future__ import annotations

import base64
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from components.kiosk_route_map import build_kiosk_route_map, build_route_overlay_svg


def test_overlay_scales_normalized_points_and_preserves_aspect_ratio() -> None:
    svg = build_route_overlay_svg(((0.1, 0.2), (0.5, 0.5), (0.9, 0.8)), width=550, height=307)
    assert 'viewBox="0 0 550 307"' in svg
    assert "M 55.000 61.400" in svg
    assert " Q 275.000 153.500" in svg
    assert "495.000" in svg
    assert "#E53935" in svg
    assert 'stroke-linecap="round"' in svg and 'stroke-linejoin="round"' in svg
    assert 'stroke-dasharray="7.500 6.750"' in svg
    assert svg.count("<circle") == 2
    assert "Usted está aquí" not in svg and "Mesa " not in svg


def test_map_0d3_regression_thumbnail_keeps_visible_base_and_route_layers() -> None:
    control = build_kiosk_route_map(
        image_url="data:image/jpeg;base64,ZmFrZQ==",
        points=((0.1, 0.2), (0.9, 0.8)),
        width=420,
    )
    assert (control.width, control.height) == (420, 234)
    assert len(control.content.controls) == 2
    base_layer, overlay_layer = control.content.controls
    assert base_layer.src == "data:image/jpeg;base64,ZmFrZQ=="
    assert (base_layer.width, base_layer.height) == (overlay_layer.width, overlay_layer.height) == (420, 234)
    assert overlay_layer.src.startswith("data:image/svg+xml;base64,")
    encoded = overlay_layer.src.split(",", 1)[1]
    decoded = base64.b64decode(encoded).decode("utf-8")
    assert "<path" in decoded and decoded.count("<circle") == 2
    assert "data:image/jpeg" not in decoded


def test_overlay_metrics_follow_the_rendered_width() -> None:
    miniature = build_route_overlay_svg(((0.1, 0.2), (0.9, 0.8)), width=320, height=179)
    viewer = build_route_overlay_svg(((0.1, 0.2), (0.9, 0.8)), width=900, height=502)
    assert 'stroke-width="3.000"' in miniature
    assert 'stroke-width="8.000"' in viewer
    assert 'r="5.000"' in miniature
    assert 'r="10.000"' in viewer


def test_invalid_points_do_not_build_renderer() -> None:
    try:
        build_route_overlay_svg(((0.1, 0.2),), width=420, height=234)
    except ValueError:
        pass
    else:
        raise AssertionError("Una ruta de un punto no debe renderizarse")
    try:
        build_route_overlay_svg(((0.1, 0.2), (1.1, 0.8)), width=420, height=234)
    except ValueError:
        pass
    else:
        raise AssertionError("Un punto fuera de rango no debe renderizarse")


def main() -> None:
    test_overlay_scales_normalized_points_and_preserves_aspect_ratio()
    test_map_0d3_regression_thumbnail_keeps_visible_base_and_route_layers()
    test_overlay_metrics_follow_the_rendered_width()
    test_invalid_points_do_not_build_renderer()
    print("Kiosk route-map component tests passed.")


if __name__ == "__main__":
    main()

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.preview_kiosk_route import (
    PreviewError,
    PreviewData,
    build_preview_document,
    normalized_to_pixel,
    prepare_preview,
    read_jpeg_dimensions,
)
from services.kiosk_map_service import MAP_ROUTE_NOT_FOUND, MAP_TABLE_NOT_FOUND, ResultadoRuta


def minimal_jpeg(width: int, height: int) -> bytes:
    return b"\xff\xd8\xff\xc0\x00\x11\x08" + height.to_bytes(2, "big") + width.to_bytes(2, "big") + (b"\x00" * 10) + b"\xff\xd9"


def test_normalized_to_pixel() -> None:
    assert normalized_to_pixel(0.25, 0.5, 1200, 800) == (300.0, 400.0)
    try:
        normalized_to_pixel(1.1, 0.5, 1200, 800)
    except PreviewError:
        pass
    else:
        raise AssertionError("Coordenada fuera de rango no fue rechazada")


def test_jpeg_read_only_and_preview_for_valid_tables() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        image_path = Path(temporary) / "floorplan.jpg"
        image_path.write_bytes(minimal_jpeg(1200, 800))
        before = hashlib.sha256(image_path.read_bytes()).digest()
        assert read_jpeg_dimensions(image_path) == (1200, 800)
        assert hashlib.sha256(image_path.read_bytes()).digest() == before

    for mesa_id in range(1, 5):
        preview = prepare_preview(2, 10, mesa_id, (1200, 800))
        assert preview.route.ok
        assert preview.route.node_ids[0] == "KIOSK"
        assert preview.route.node_ids[-1] == f"MESA_{mesa_id}"
        assert len(preview.pixel_points) == len(preview.route.points)
        assert all(0.0 <= x <= 1200.0 and 0.0 <= y <= 800.0 for x, y in preview.pixel_points)
        document = build_preview_document(preview)
        assert preview.route.node_ids == prepare_preview(2, 10, mesa_id, (1200, 800)).route.node_ids
        assert preview.route.points == prepare_preview(2, 10, mesa_id, (1200, 800)).route.points
        assert "Usted está aquí" not in document
        assert f"Mesa {preview.route.mesa_texto}" not in document
        assert "#E53935" in document
        assert "ctx.lineCap='round'" in document
        assert "ctx.lineJoin='round'" in document
        assert "quadraticCurveTo" in document
        assert "CURVE_FACTOR=0.20" in document
        assert "ctx.lineWidth=Math.max(11,Math.min(13,image.naturalWidth/250))" in document
        assert "ctx.setLineDash([dashUnit*1.5,dashUnit*1.35])" in document
        assert "ctx.setLineDash([])" in document
        assert "markerRadius=Math.max(14,Math.min(16,image.naturalWidth/200))" in document
        assert "drawEndpoint(route.points[0])" in document
        assert "drawEndpoint(route.points.at(-1))" in document
        assert document.index("ctx.setLineDash([])") < document.index("drawEndpoint(route.points[0])")


def test_two_point_route_renders_without_a_curve_error() -> None:
    route = ResultadoRuta(
        ok=True,
        codigo="OK",
        mensaje="Ruta calculada.",
        account_id=2,
        event_id=10,
        mesa_id=99,
        mesa_texto="Prueba",
        node_ids=("KIOSK", "MESA_TEST"),
        points=((0.1, 0.1), (0.9, 0.9)),
        total_distance=1.0,
    )
    preview = PreviewData(
        route=route,
        image_width=1000,
        image_height=500,
        pixel_points=((100.0, 50.0), (900.0, 450.0)),
    )
    document = build_preview_document(preview)
    assert "if(points.length===2)" in document
    assert "ctx.lineTo(...points[1]);return" in document


def test_missing_table_and_missing_route_are_controlled() -> None:
    try:
        prepare_preview(2, 10, 99, (1200, 800))
    except PreviewError as exc:
        assert str(exc).startswith(MAP_TABLE_NOT_FOUND)
    else:
        raise AssertionError("Mesa inexistente no fue rechazada")

    missing_route = ResultadoRuta(
        ok=False,
        codigo=MAP_ROUTE_NOT_FOUND,
        mensaje="No existe ruta.",
        account_id=2,
        event_id=10,
        mesa_id=1,
    )
    with patch("scripts.preview_kiosk_route.calcular_ruta", return_value=missing_route):
        try:
            prepare_preview(2, 10, 1, (1200, 800))
        except PreviewError as exc:
            assert str(exc).startswith(MAP_ROUTE_NOT_FOUND)
        else:
            raise AssertionError("Ruta inexistente no fue rechazada")


def main() -> None:
    test_normalized_to_pixel()
    test_jpeg_read_only_and_preview_for_valid_tables()
    test_two_point_route_renders_without_a_curve_error()
    test_missing_table_and_missing_route_are_controlled()
    print("Kiosk route preview tests passed.")


if __name__ == "__main__":
    main()

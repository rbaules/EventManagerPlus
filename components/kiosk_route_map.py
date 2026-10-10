"""Pure Flet presentation for an already-resolved Kiosk floor-plan route."""

from __future__ import annotations

import base64
import math
from typing import Iterable

import flet as ft


ROUTE_COLOR = "#E53935"
CURVE_FACTOR = 0.20
SOURCE_WIDTH = 2750
SOURCE_HEIGHT = 1535


def _point_toward(
    source: tuple[float, float], target: tuple[float, float], distance: float
) -> tuple[float, float]:
    length = math.dist(source, target)
    if not length:
        return source
    return (
        source[0] + (target[0] - source[0]) * distance / length,
        source[1] + (target[1] - source[1]) * distance / length,
    )


def _pixel_points(
    points: Iterable[tuple[float, float]], width: int, height: int
) -> tuple[tuple[float, float], ...]:
    normalized = tuple(points)
    if len(normalized) < 2:
        raise ValueError("La ruta requiere al menos dos puntos.")
    if width <= 0 or height <= 0:
        raise ValueError("Las dimensiones visibles deben ser positivas.")
    if any(not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0) for x, y in normalized):
        raise ValueError("La ruta contiene puntos normalizados fuera de rango.")
    return tuple((x * width, y * height) for x, y in normalized)


def _smoothed_path(points: tuple[tuple[float, float], ...]) -> str:
    path = [f"M {points[0][0]:.3f} {points[0][1]:.3f}"]
    if len(points) == 2:
        path.append(f"L {points[1][0]:.3f} {points[1][1]:.3f}")
        return " ".join(path)
    for index in range(1, len(points) - 1):
        previous, current, following = points[index - 1], points[index], points[index + 1]
        curve_distance = min(math.dist(previous, current), math.dist(current, following)) * CURVE_FACTOR
        entry = _point_toward(current, previous, curve_distance)
        exit_point = _point_toward(current, following, curve_distance)
        path.append(f"L {entry[0]:.3f} {entry[1]:.3f}")
        path.append(
            f"Q {current[0]:.3f} {current[1]:.3f} {exit_point[0]:.3f} {exit_point[1]:.3f}"
        )
    path.append(f"L {points[-1][0]:.3f} {points[-1][1]:.3f}")
    return " ".join(path)


def build_route_overlay_svg(
    points: Iterable[tuple[float, float]], *, width: int, height: int
) -> str:
    """Render the approved MAP-0C geometry without labels or route mutations."""
    pixel_points = _pixel_points(points, width, height)
    # This renderer is used at the dimensions that are actually shown by
    # Flet.  Do not derive these values from the source image's natural size:
    # the same route is intentionally compact in SUCCESS and larger in its
    # viewer.
    line_width = max(3.0, min(8.0, width / 110.0))
    marker_radius = max(5.0, min(10.0, width / 70.0))
    dash_length, gap_length = line_width * 1.5, line_width * 1.35
    path = _smoothed_path(pixel_points)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="{width}" height="{height}" preserveAspectRatio="none">'
        f'<path d="{path}" fill="none" stroke="{ROUTE_COLOR}" '
        f'stroke-width="{line_width:.3f}" stroke-linecap="round" stroke-linejoin="round" '
        f'stroke-dasharray="{dash_length:.3f} {gap_length:.3f}"/>'
        f'<circle cx="{pixel_points[0][0]:.3f}" cy="{pixel_points[0][1]:.3f}" '
        f'r="{marker_radius:.3f}" fill="{ROUTE_COLOR}"/>'
        f'<circle cx="{pixel_points[-1][0]:.3f}" cy="{pixel_points[-1][1]:.3f}" '
        f'r="{marker_radius:.3f}" fill="{ROUTE_COLOR}"/>'
        "</svg>"
    )


def build_route_overlay_data_url(
    points: Iterable[tuple[float, float]], *, width: int, height: int
) -> str:
    """Return the transparent route layer independently from the floor-plan."""
    svg = build_route_overlay_svg(points, width=width, height=height)
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")


def build_kiosk_route_map(
    *,
    image_url: str,
    points: Iterable[tuple[float, float]],
    width: int,
    overlay_url: str | None = None,
    on_click: object | None = None,
    data: object | None = None,
) -> ft.Control:
    """Present prepared local base-map and SVG layers in one mounted Stack."""
    if width <= 0:
        raise ValueError("El ancho del mapa debe ser positivo.")
    height = round(width * SOURCE_HEIGHT / SOURCE_WIDTH)
    svg_url = overlay_url or build_route_overlay_data_url(points, width=width, height=height)
    return ft.Container(
        width=width,
        height=height,
        border_radius=16,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        ink=on_click is not None,
        on_click=on_click,
        tooltip="Abrir mapa" if on_click is not None else None,
        content=ft.Stack(
            width=width,
            height=height,
            controls=[
                ft.Image(
                    src=image_url,
                    width=width,
                    height=height,
                    fit=ft.BoxFit.CONTAIN,
                    data={"kiosk": "route_map_base", "width": width, "height": height},
                ),
                ft.Image(
                    src=svg_url,
                    width=width,
                    height=height,
                    fit=ft.BoxFit.FILL,
                    data={"kiosk": "route_map_overlay", "width": width, "height": height},
                ),
            ],
            data={"kiosk": "route_map_layers", "width": width, "height": height},
        ),
        data=data or {"kiosk": "route_map", "width": width, "height": height},
    )

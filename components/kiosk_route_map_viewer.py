"""Pure Flet presentation for the temporary full-screen Kiosk map viewer."""

from __future__ import annotations

from typing import Callable, Iterable

import flet as ft

from components.kiosk_route_map import SOURCE_HEIGHT, SOURCE_WIDTH, build_kiosk_route_map


MIN_ZOOM = 1.0
MAX_ZOOM = 2.5


def build_kiosk_route_map_viewer(
    *,
    image_url: str,
    points: Iterable[tuple[float, float]],
    width: int,
    zoom: float,
    on_close: Callable[[object], None],
    on_zoom_out: Callable[[object], None],
    on_zoom_reset: Callable[[object], None],
    on_zoom_in: Callable[[object], None],
) -> ft.Control:
    """Build an overlay only; callers own Kiosk state, timeout, and storage."""
    if width <= 0:
        raise ValueError("El visor requiere un ancho positivo.")
    if not MIN_ZOOM <= zoom <= MAX_ZOOM:
        raise ValueError("El zoom del visor está fuera de rango.")

    height = round(width * SOURCE_HEIGHT / SOURCE_WIDTH)
    rendered_width = round(width * zoom)
    rendered_map = build_kiosk_route_map(
        image_url=image_url,
        points=points,
        width=rendered_width,
        data={"kiosk": "route_map_viewer_map", "width": rendered_width},
    )
    # InteractiveViewer is available in the installed Flet 0.85.3 and gives
    # Web/tablet users native pan and pinch/trackpad scaling. The three
    # explicit controls remain a reliable alternative for mouse-only clients.
    viewer = ft.InteractiveViewer(
        content=rendered_map,
        width=width,
        height=height,
        pan_enabled=True,
        scale_enabled=True,
        min_scale=1.0,
        max_scale=2.5,
        constrained=False,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
        data={"kiosk": "route_map_interactive_viewer", "zoom": zoom},
    )
    close_button = ft.Container(
        width=48,
        height=48,
        right=12,
        top=12,
        bgcolor="#F8F1E8",
        border=ft.Border.all(width=1, color="#971B1F"),
        border_radius=24,
        alignment=ft.Alignment.CENTER,
        content=ft.IconButton(
            icon=ft.Icons.CLOSE,
            icon_color="#971B1F",
            icon_size=28,
            tooltip="Cerrar",
            on_click=on_close,
            data={"kiosk": "route_map_viewer_close"},
        ),
        data={"kiosk": "route_map_viewer_close_anchor"},
    )
    map_layer = ft.Stack(
        width=width,
        height=height,
        controls=[viewer, close_button],
        data={"kiosk": "route_map_viewer_stack"},
    )
    controls = ft.Column(
        [
            map_layer,
            ft.Row(
                [
                    ft.OutlinedButton("−", on_click=on_zoom_out, disabled=zoom <= MIN_ZOOM),
                    ft.OutlinedButton("Restablecer", on_click=on_zoom_reset),
                    ft.OutlinedButton("+", on_click=on_zoom_in, disabled=zoom >= MAX_ZOOM),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=12,
                data={"kiosk": "route_map_viewer_zoom_controls", "zoom": zoom},
            ),
        ],
        horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        spacing=12,
    )
    return ft.Container(
        expand=True,
        bgcolor="#EED82A2A",
        alignment=ft.Alignment.CENTER,
        padding=16,
        content=ft.Container(
            width=width + 32,
            padding=16,
            bgcolor="#F8F1E8",
            border_radius=20,
            content=controls,
        ),
        data={"kiosk": "route_map_viewer", "zoom": zoom},
    )

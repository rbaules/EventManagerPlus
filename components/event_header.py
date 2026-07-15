from __future__ import annotations

from typing import Any

import flet as ft


def _get(source: dict[str, Any] | None, key: str, default: str = "-") -> Any:
    if not source:
        return default
    value = source.get(key)
    return default if value in (None, "") else value


def event_header(contexto: dict[str, Any]) -> ft.Container:
    cuenta = contexto.get("cuenta_actual") or {}
    evento = contexto.get("evento_actual") or {}
    fase = _get(evento, "fase_evento", "")
    evento_nombre = _get(evento, "nombre_evento", "Ningun evento seleccionado")

    details = [
        ft.Text(
            evento_nombre,
            size=18,
            weight=ft.FontWeight.BOLD,
            overflow=ft.TextOverflow.ELLIPSIS,
        ),
        ft.Text(
            f"Cuenta: {_get(cuenta, 'nombre_cuenta', 'Sin cuenta actual')}",
            size=13,
            color=ft.Colors.ON_SURFACE_VARIANT,
            overflow=ft.TextOverflow.ELLIPSIS,
        ),
    ]
    if fase:
        details.append(
            ft.Container(
                content=ft.Text(fase, size=12, weight=ft.FontWeight.W_600),
                padding=ft.Padding.symmetric(
                    horizontal=10,
                    vertical=4,
                ),
                border_radius=16,
                bgcolor=ft.Colors.SECONDARY_CONTAINER,
            )
        )

    return ft.Container(
        content=ft.ResponsiveRow(
            [
                ft.Container(
                    content=ft.Image(
                        src="brand/EventPlus_logo_v2.0_horizontal.png",
                        width=180,
                        fit=ft.BoxFit.CONTAIN,
                    ),
                    col={"xs": 12, "sm": 4, "md": 3},
                    padding=ft.Padding.only(bottom=8),
                ),
                ft.Container(
                    content=ft.Column(details, spacing=6, tight=True),
                    col={"xs": 12, "sm": 8, "md": 5},
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                _get(contexto, "usr_nombre_usuario", "Usuario"),
                                size=14,
                                weight=ft.FontWeight.W_600,
                                overflow=ft.TextOverflow.ELLIPSIS,
                            ),
                            ft.Text(
                                _get(contexto, "rol_global_calculado", "Sin rol"),
                                size=13,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        horizontal_alignment=ft.CrossAxisAlignment.END,
                        spacing=4,
                        tight=True,
                    ),
                    col={"xs": 12, "md": 4},
                    alignment=ft.Alignment.CENTER_RIGHT,
                ),
            ],
            spacing=12,
            run_spacing=8,
        ),
        padding=16,
        border=ft.Border.only(
            bottom=ft.BorderSide(width=1, color=ft.Colors.OUTLINE_VARIANT),
        ),
        bgcolor=ft.Colors.SURFACE,
    )

from __future__ import annotations

import flet as ft


def stat_card(title: str, value: str, subtitle: str | None = None) -> ft.Container:
    content: list[ft.Control] = [
        ft.Text(title, size=13, color=ft.Colors.ON_SURFACE_VARIANT),
        ft.Text(value or "-", size=22, weight=ft.FontWeight.BOLD),
    ]
    if subtitle:
        content.append(ft.Text(subtitle, size=12, color=ft.Colors.ON_SURFACE_VARIANT))

    return ft.Container(
        content=ft.Column(content, spacing=6, tight=True),
        padding=16,
        border_radius=8,
        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border=ft.Border.all(
            width=1,
            color=ft.Colors.OUTLINE_VARIANT,
        ),
    )

from __future__ import annotations

import flet as ft

from views.login_view import build_login_view


def main(page: ft.Page) -> None:
    page.title = "EventPlus - Prueba Google OAuth + Supabase"
    page.window.width = 950
    page.window.height = 760
    page.scroll = ft.ScrollMode.AUTO
    page.adaptive = True

    build_login_view(page)


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")

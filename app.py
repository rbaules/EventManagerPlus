from __future__ import annotations

import flet as ft

from config import APP_MODE, APP_VERSION
from db import create_supabase_client
from views.login_view import build_login_view


def main(page: ft.Page) -> None:
    supabase = create_supabase_client()
    print("[APP][INFO] Modo de aplicacion:", APP_MODE)
    page.title = f"EventPlus - {APP_MODE} {APP_VERSION}"
    page.window.width = 950
    page.window.height = 760
    page.scroll = ft.ScrollMode.AUTO
    page.adaptive = True

    build_login_view(page, supabase)


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")

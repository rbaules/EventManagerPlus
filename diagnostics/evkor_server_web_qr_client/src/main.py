"""Build-only host; EVKOR's server-side Python provides the real Page."""

import flet as ft


def main(page: ft.Page) -> None:
    page.add(ft.Text("This Python entry point is not used by the server-side client."))

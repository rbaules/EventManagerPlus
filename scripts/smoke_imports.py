from __future__ import annotations

import importlib
import sys
from pathlib import Path


MODULES = [
    "asgi",
    "app",
    "config",
    "db",
    "services.auth_service",
    "services.authorization_service",
    "services.evento_context_service",
    "services.evento_service",
    "services.invitado_service",
    "services.lugar_service",
    "services.response_utils",
    "services.server_session_service",
    "services.session_service",
    "services.usuario_service",
    "components.app_shell",
    "components.bottom_navigation",
    "components.event_header",
    "components.stat_card",
    "views.arrivals_view",
    "views.dashboard_view",
    "views.home_view",
    "views.invitados_view",
    "views.login_view",
    "views.lugares_view",
]


class DummyPage:
    def __init__(self) -> None:
        self.navigation_bar = None


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    print("EventPlus smoke import/build test")
    print("=" * 35)

    for module_name in MODULES:
        importlib.import_module(module_name)
        print(f"import OK: {module_name}")

    import flet as ft
    from components.app_shell import app_shell
    from components.bottom_navigation import bottom_navigation
    from components.event_header import event_header
    from components.stat_card import stat_card
    from views.arrivals_view import arrivals_view
    from views.dashboard_view import dashboard_view
    from views.home_view import build_home_view
    from views.invitados_view import invitados_view
    from views.lugares_view import lugares_view

    contexto = {
        "usr_nombre_usuario": "Usuario Demo",
        "rol_global_calculado": "Administrador",
        "cuenta_actual": {"nombre_cuenta": "Cuenta Demo"},
        "evento_actual": {
            "cuenta_id": 1,
            "evento_id": 1,
            "nombre_evento": "Evento Demo",
            "fase_evento": "En_proceso",
        },
        "cuentas_permitidas": [{"cuenta_id": 1}],
        "eventos_permitidos": [{"cuenta_id": 1, "evento_id": 1}],
        "puede_registrar_llegadas": True,
    }

    controls: list[ft.Control] = [
        stat_card("Estado", "OK"),
        event_header(contexto, lambda: None, lambda: None),
        bottom_navigation("dashboard", True, True, lambda tab: None),
        arrivals_view(
            contexto,
            "idle",
            "",
            "",
            [],
            None,
            [],
            set(),
            True,
            False,
            False,
            lambda value=None: None,
            lambda: None,
            lambda value=None: None,
            lambda item=None, selected=False: None,
            lambda: None,
            lambda: None,
            lambda value=None: None,
            lambda: None,
        ),
        dashboard_view(contexto),
        invitados_view(
            contexto,
            "empty",
            [],
            "Este evento todavia no tiene invitados registrados.",
            "invitado",
            "",
            "todos",
            False,
            False,
            None,
            False,
            False,
            False,
            False,
            False,
            [],
            None,
            "",
            False,
            lambda value=None: None,
            lambda value=None: None,
            lambda: None,
            lambda value=None: None,
            lambda: None,
            lambda: None,
            lambda value=None: None,
            lambda: None,
            lambda: None,
            lambda value=None: None,
            lambda value=None: None,
            lambda value=None: None,
            lambda value=None: None,
            lambda value=None: None,
            lambda value=None: None,
            lambda value=None: None,
            lambda: None,
        ),
        lugares_view(
            contexto,
            "empty",
            "",
            [],
            None,
            [],
            [],
            None,
            "",
            False,
            True,
            lambda: None,
            lambda value=None: None,
            lambda value=None: None,
            lambda value=None: None,
            lambda value=None: None,
            lambda value=None: None,
            lambda value=None: None,
            lambda value=None: None,
            lambda value=None: None,
            lambda: None,
        ),
        app_shell(
            contexto,
            "dashboard",
            dashboard_view(contexto),
            lambda tab: None,
            lambda: None,
        ),
        build_home_view(DummyPage(), contexto),
    ]

    for control in controls:
        if control is None:
            raise RuntimeError("A Flet control builder returned None.")
        print(f"control OK: {type(control).__name__}")

    print("OK - imports and control construction succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

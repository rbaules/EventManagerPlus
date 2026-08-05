from __future__ import annotations

import asyncio
import inspect
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from components.event_header import calcular_iniciales_usuario, event_header
from services.evento_context_service import (
    construir_contexto_evento_activo,
    evento_key,
    limpiar_evento_activo,
    sincronizar_evento_activo,
    establecer_evento_activo,
)
from services.evento_service import normalizar_evento, obtener_eventos_disponibles
from views.dashboard_view import dashboard_view
from views.home_view import build_home_view
import views.home_view as home_view_module
from views.event_selection_view import event_selection_view


class Response:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, rows: list[dict[str, Any]], fail: bool = False) -> None:
        self.rows = rows
        self.fail = fail
        self.filters: dict[str, Any] = {}

    def select(self, _columns: str) -> "FakeQuery":
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.filters[column] = value
        return self

    def limit(self, _count: int) -> "FakeQuery":
        return self

    def execute(self) -> Response:
        if self.fail:
            raise RuntimeError("network unavailable")
        data = [
            row
            for row in self.rows
            if all(row.get(column) == value for column, value in self.filters.items())
        ]
        return Response(data)


class FakeSupabase:
    def __init__(self, rows: list[dict[str, Any]], fail: bool = False) -> None:
        self.rows = rows
        self.fail = fail

    def table(self, name: str) -> FakeQuery:
        if name == "evp_eve_evento":
            return FakeQuery(self.rows, self.fail)
        if name in {"evp_ivt_invitado", "evp_mes_mesa"}:
            return FakeQuery([], self.fail)
        raise AssertionError(name)


class DummyPage:
    pass


class SelectionPage:
    def __init__(self) -> None:
        self.dialog = None

    def show_dialog(self, dialog: Any) -> None:
        self.dialog = dialog


class SessionStore:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}

    def set(self, key: str, value: Any) -> None:
        self.values[key] = value


class InteractivePage(SelectionPage):
    def __init__(self, fail_on_update: int | None = None) -> None:
        super().__init__()
        self.route = "/app/eventos/seleccionar"
        self.navigation_bar = None
        self.session = type("Session", (), {"store": SessionStore()})()
        self.pushes: list[str] = []
        self.thread_handlers: list[Any] = []
        self.update_count = 0
        self.fail_on_update = fail_on_update

    async def push_route(self, route: str) -> None:
        self.pushes.append(route)
        self.route = route

    def clean(self) -> None: pass
    def add(self, _control: Any) -> None: pass
    def update(self) -> None:
        self.update_count += 1
        if self.update_count == self.fail_on_update:
            raise RuntimeError("refresh failed")
    def run_thread(self, handler: Any, *args: Any) -> None:
        self.thread_handlers.append((handler, args))
    def run_task(self, handler: Any, *args: Any) -> Any:
        class Future:
            def done(self) -> bool: return False
            def cancel(self) -> None: pass
        return Future()


def base_context(eventos: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "usr_usuario_id": "user-1",
        "usr_evento_id_default": None,
        "usr_nombre_usuario": "Usuario Demo",
        "rol_global_calculado": "Operador",
        "cuenta_actual": {"cuenta_id": 1, "nombre_cuenta": "Cuenta Demo"},
        "cuentas_permitidas": [{"cuenta_id": 1, "nombre_cuenta": "Cuenta Demo", "rol": "Operador"}],
        "evento_actual": None,
        "eventos_permitidos": eventos or [],
        "puede_registrar_llegadas": False,
        "puede_administrar_usuarios": False,
    }


ROWS = [
    {
        "eve_cuenta_id": 1,
        "eve_evento_id": 10,
        "eve_nombre_evento": "Evento Uno",
        "eve_nombre_evento_abrev": "E1",
        "eve_fase_evento": "Pre_evento",
        "eve_lugar_id": None,
        "eve_salon_id": None,
        "eve_fecha_hora_inicio": None,
        "eve_fecha_hora_fin": None,
        "eve_estado": "Activo",
    },
    {
        "eve_cuenta_id": 1,
        "eve_evento_id": 11,
        "eve_nombre_evento": "Evento Dos",
        "eve_nombre_evento_abrev": "E2",
        "eve_fase_evento": "En_proceso",
        "eve_lugar_id": 2,
        "eve_salon_id": 3,
        "eve_fecha_hora_inicio": "2026-07-20T19:30:00+00:00",
        "eve_fecha_hora_fin": None,
        "eve_estado": "Activo",
    },
]


def assert_service_multiple_events() -> None:
    contexto = base_context(
        [
            {"cuenta_id": 1, "evento_id": 10, "rol": "Consulta"},
            {"cuenta_id": 1, "evento_id": 11, "rol": "Operador"},
        ]
    )
    result = obtener_eventos_disponibles(contexto, FakeSupabase(ROWS))
    assert result.ok
    assert result.estado == "ready"
    assert len(result.eventos) == 2
    assert result.eventos[1]["rol"] == "Operador"


def assert_service_single_empty_error_and_invalid_session() -> None:
    contexto = base_context([{"cuenta_id": 1, "evento_id": 10, "rol": "Consulta"}])
    single = obtener_eventos_disponibles(contexto, FakeSupabase(ROWS))
    assert single.ok and len(single.eventos) == 1

    empty = obtener_eventos_disponibles(base_context([]), FakeSupabase(ROWS))
    assert empty.ok and empty.estado == "empty"

    invalid = obtener_eventos_disponibles(None, FakeSupabase(ROWS))
    assert not invalid.ok and invalid.estado == "session_invalid"

    error = obtener_eventos_disponibles(contexto, FakeSupabase(ROWS, fail=True))
    assert not error.ok and error.estado == "connection_error"


def assert_null_normalization() -> None:
    evento = normalizar_evento(ROWS[0], {"rol": "Consulta"})
    assert evento is not None
    assert evento["lugar_id"] is None
    assert evento["fecha_hora_inicio_legible"] is None


def assert_active_event_context() -> None:
    contexto = base_context()
    evento_uno = normalizar_evento(ROWS[0], {"rol": "Consulta"})
    evento_dos = normalizar_evento(ROWS[1], {"rol": "Operador"})
    assert evento_uno and evento_dos

    establecer_evento_activo(contexto, evento_uno)
    assert evento_key(contexto["evento_actual"]) == (1, 10)

    establecer_evento_activo(contexto, evento_dos)
    assert evento_key(contexto["evento_actual"]) == (1, 11)
    assert contexto["puede_registrar_llegadas"]

    limpiar_evento_activo(contexto)
    assert contexto["evento_actual"] is None
    assert not contexto["puede_registrar_llegadas"]

    contexto["evento_actual"] = {"cuenta_id": 9, "evento_id": 99}
    sincronizar_evento_activo(contexto, [evento_uno, evento_dos])
    assert contexto["evento_actual"] is None


def assert_atomic_context_and_real_key() -> None:
    evento_uno = normalizar_evento(ROWS[0], {"rol": "Consulta"})
    evento_dos = normalizar_evento(ROWS[1], {"rol": "Operador"})
    assert evento_uno and evento_dos
    contexto = base_context([evento_uno, evento_dos])
    establecer_evento_activo(contexto, evento_uno)
    nuevo = construir_contexto_evento_activo(contexto, [evento_uno, evento_dos], (1, 11))
    assert evento_key(contexto["evento_actual"]) == (1, 10)
    assert evento_key(nuevo["evento_actual"]) == (1, 11)
    assert nuevo["capacidades"] != contexto.get("capacidades")
    try:
        construir_contexto_evento_activo(contexto, [evento_uno], (9, 99))
    except LookupError:
        pass
    else:
        raise AssertionError("Un evento inexistente debe rechazarse.")
    assert evento_key(contexto["evento_actual"]) == (1, 10)


def assert_selection_callbacks_capture_each_event() -> None:
    eventos = [normalizar_evento(ROWS[0], {"rol": "Consulta"}), normalizar_evento(ROWS[1], {"rol": "Operador"})]
    assert all(eventos)
    selected: list[tuple[int, int] | None] = []
    view = event_selection_view(eventos, None, "ready", "", lambda event: selected.append(evento_key(event)), lambda: None, lambda: None)
    buttons = [container.content.controls[-1] for container in view.controls[1:]]
    assert inspect.iscoroutinefunction(buttons[0].on_click)
    first = buttons[0].on_click(None)
    second = buttons[1].on_click(None)
    asyncio.run(first)
    asyncio.run(second)
    assert selected == [(1, 10), (1, 11)]
    assert callable(home_view_module.evento_key)


def assert_async_selection_without_navigation_and_rollback() -> None:
    eventos = [normalizar_evento(ROWS[0], {"rol": "Consulta"}), normalizar_evento(ROWS[1], {"rol": "Operador"})]
    assert all(eventos)
    contexto = base_context(eventos)
    establecer_evento_activo(contexto, eventos[0])
    page = InteractivePage()
    home = build_home_view(page, contexto, FakeSupabase(ROWS))
    home.data["state"]["eventos"] = eventos
    assert inspect.iscoroutinefunction(home.data["select_event"])
    asyncio.run(home.data["select_event"](eventos[1]))
    assert evento_key(contexto["evento_actual"]) == (1, 11)
    assert page.pushes == [] and page.route == "/app/eventos/seleccionar"
    for index in range(5):
        target = eventos[index % 2]
        asyncio.run(home.data["select_event"](target))
        assert evento_key(contexto["evento_actual"]) == evento_key(target)
    assert home.data["state"]["excel_import_preview"] is None

    failing_page = InteractivePage(fail_on_update=2)
    failing_context = base_context(eventos)
    establecer_evento_activo(failing_context, eventos[0])
    failing_home = build_home_view(failing_page, failing_context, FakeSupabase(ROWS))
    failing_home.data["state"]["eventos"] = eventos
    asyncio.run(failing_home.data["select_event"](eventos[1]))
    assert evento_key(failing_context["evento_actual"]) == (1, 10)
    assert "evento anterior" in failing_home.data["state"]["eventos_mensaje"]


def assert_ui_builds() -> None:
    evento = normalizar_evento(ROWS[1], {"rol": "Operador"})
    contexto = base_context([evento])
    if evento:
        establecer_evento_activo(contexto, evento)

    controls = [
        dashboard_view(base_context([]), estado="event_required"),
        dashboard_view(contexto, estado="ready"),
        dashboard_view(contexto, estado="loading"),
        dashboard_view(contexto, estado="error", mensaje="Error controlado", on_retry=lambda: None),
        event_header(base_context([]), lambda: None, lambda: None),
        event_header(contexto, lambda: None, lambda: None),
        build_home_view(DummyPage(), contexto),
    ]
    for control in controls:
        assert control is not None


def assert_user_initials() -> None:
    assert calcular_iniciales_usuario("Roberto Baules") == "RB"
    assert calcular_iniciales_usuario("Ana Maria Solis") == "AS"
    assert calcular_iniciales_usuario("Operador") == "OP"
    assert calcular_iniciales_usuario("") == "US"


def main() -> int:
    assert_service_multiple_events()
    assert_service_single_empty_error_and_invalid_session()
    assert_null_normalization()
    assert_active_event_context()
    assert_atomic_context_and_real_key()
    assert_selection_callbacks_capture_each_event()
    assert_async_selection_without_navigation_and_rollback()
    assert_ui_builds()
    assert_user_initials()
    print("OK - event selection service, context, and UI construction tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

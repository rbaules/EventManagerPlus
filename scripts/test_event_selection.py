from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from components.event_header import calcular_iniciales_usuario, event_header
from services.evento_context_service import (
    evento_key,
    limpiar_evento_activo,
    sincronizar_evento_activo,
    establecer_evento_activo,
)
from services.evento_service import normalizar_evento, obtener_eventos_disponibles
from views.dashboard_view import dashboard_view
from views.home_view import build_home_view


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
        assert name == "evp_eve_evento"
        return FakeQuery(self.rows, self.fail)


class DummyPage:
    pass


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
    assert_ui_builds()
    assert_user_initials()
    print("OK - event selection service, context, and UI construction tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

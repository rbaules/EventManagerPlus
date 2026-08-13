from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import flet as ft

from services.dashboard_service import (
    IndicadoresDashboard,
    calcular_indicadores_dashboard,
    construir_intervalos_llegadas,
    obtener_indicadores_dashboard,
)
from views.dashboard_view import dashboard_view


def guest(guest_id: str, table: Any, arrived: bool, timestamp: str | None = None, novelty: bool = False, state: str = "Activo") -> dict[str, Any]:
    return {
        "ivt_invitado_uuid": guest_id,
        "ivt_mesa_id": table,
        "ivt_llegada_confirmada": arrived,
        "ivt_fecha_hora_conf_llegada": timestamp,
        "ivt_tiene_novedad": novelty,
        "ivt_estado": state,
    }


def table(table_id: int, state: str = "Activo") -> dict[str, Any]:
    return {"mes_mesa_id": table_id, "mes_estado": state}


def context(role: str = "Consulta", authorized: bool = True) -> dict[str, Any]:
    event = {
        "cuenta_id": 7,
        "evento_id": 42,
        "nombre_evento": "Gala EventPlus",
        "fase_evento": "En_proceso",
        "estado": "Activo",
        "fecha_hora_inicio": "2026-08-03T18:00:00-05:00",
        "rol": role,
    }
    return {
        "usr_usuario_id": "user-1",
        "rol_global_calculado": role,
        "evento_actual": event,
        "eventos_permitidos": [dict(event)] if authorized else [],
    }


class Response:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class Query:
    def __init__(self, db: "FakeSupabase", name: str) -> None:
        self.db = db
        self.name = name
        self.filters: list[tuple[str, Any]] = []

    def select(self, fields: str) -> "Query":
        self.db.selects.append((self.name, fields))
        return self

    def eq(self, field: str, value: Any) -> "Query":
        self.filters.append((field, value))
        return self

    def execute(self) -> Response:
        self.db.executions.append((self.name, tuple(self.filters)))
        rows = self.db.guests if self.name == "evp_ivt_invitado" else self.db.tables
        return Response(rows)


class FakeSupabase:
    def __init__(self) -> None:
        self.guests = [guest("a", 1, True, "2026-08-03T18:05:00-05:00", True)]
        self.tables = [table(1)]
        self.selects: list[tuple[str, str]] = []
        self.executions: list[Any] = []

    def table(self, name: str) -> Query:
        return Query(self, name)


def walk(control: ft.Control) -> list[ft.Control]:
    result = [control]
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        result.extend(walk(content))
    for child in getattr(control, "controls", None) or []:
        if isinstance(child, ft.Control):
            result.extend(walk(child))
    return result


def test_metricas_reales_y_ceros() -> None:
    data = calcular_indicadores_dashboard(
        [
            guest("a", 1, True, "2026-08-03T18:00:00-05:00", True),
            guest("b", 1, True, "2026-08-03T18:15:00-05:00"),
            guest("c", 2, False, novelty=True),
            guest("d", None, False),
            guest("x", 2, True, "2026-08-03T18:30:00-05:00", state="Inactivo"),
        ],
        [table(1), table(2), table(3), table(9, "Inactivo")],
        "2026-08-03T18:00:00-05:00",
    )
    assert (data.total_invitados, data.invitados_llegaron, data.invitados_pendientes) == (4, 2, 2)
    assert (data.porcentaje_llegadas, data.porcentaje_pendientes) == (50.0, 50.0)
    assert (data.total_mesas, data.mesas_completas, data.mesas_pendientes) == (3, 1, 2)
    assert round(data.porcentaje_mesas_completas, 2) == 33.33
    assert data.invitados_con_novedades == 2
    assert data.primera_llegada == "6:00 p. m." and data.ultima_llegada == "6:15 p. m."
    empty = calcular_indicadores_dashboard([], [])
    assert empty.porcentaje_llegadas == empty.porcentaje_mesas_completas == 0
    assert empty.primera_llegada == empty.ultima_llegada == "Sin llegadas"


def test_intervalos_y_zona_horaria() -> None:
    start = datetime(2026, 8, 3, 23, 45, tzinfo=timezone(timedelta(hours=-5)))
    arrivals = [
        start - timedelta(seconds=1),
        start,
        start + timedelta(minutes=14, seconds=59),
        start + timedelta(minutes=15),
        start + timedelta(minutes=119, seconds=59),
        start + timedelta(hours=2),
        (start + timedelta(minutes=30)).astimezone(timezone.utc),
    ]
    intervals = construir_intervalos_llegadas(start.isoformat(), arrivals)
    assert len(intervals) == 8
    assert [item.cantidad for item in intervals] == [2, 1, 1, 0, 0, 0, 0, 1]
    assert intervals[1].inicio.date() > intervals[0].inicio.date()
    assert construir_intervalos_llegadas(None, arrivals) == ()

    utc_crossing = calcular_indicadores_dashboard(
        [
            guest("utc-a", 1, True, "2026-08-13T01:15:00+00:00"),
            guest("utc-b", 1, True, "2026-08-13T01:29:59+00:00"),
        ],
        [table(1)],
        "2026-08-12T20:00:00-05:00",
    )
    assert utc_crossing.primera_llegada == "8:15 p. m."
    assert utc_crossing.ultima_llegada == "8:29 p. m."
    assert [item.cantidad for item in utc_crossing.intervalos_llegadas[:2]] == [0, 2]
    assert utc_crossing.intervalos_llegadas[1].inicio.date().isoformat() == "2026-08-12"


def test_roles_acceso_y_dos_consultas() -> None:
    for role in ("Master", "Administrador", "Operador", "Consulta"):
        db = FakeSupabase()
        result = obtener_indicadores_dashboard(context(role), db)
        assert result.ok and len(db.executions) == 2
        for _name, filters in db.executions:
            assert any(field.endswith("cuenta_id") and value == 7 for field, value in filters)
            assert any(field.endswith("evento_id") and value == 42 for field, value in filters)
    denied_db = FakeSupabase()
    denied = obtener_indicadores_dashboard(context("Consulta", authorized=False), denied_db)
    assert not denied.ok and denied.estado == "forbidden" and not denied_db.executions


def test_ui_componentes_estados_y_responsive() -> None:
    ready = dashboard_view(context(), "ready", calcular_indicadores_dashboard([], [], context()["evento_actual"]["fecha_hora_inicio"]), on_retry=lambda: None)
    nodes = walk(ready)
    kpis = [node for node in nodes if isinstance(getattr(node, "data", None), dict) and node.data.get("dashboard_component") == "kpi_card"]
    charts = [node for node in nodes if isinstance(getattr(node, "data", None), dict) and node.data.get("dashboard_component") == "visualization"]
    assert len(kpis) == 8 and len(charts) >= 3
    assert all(card.expand is not True and card.height is None for card in kpis)
    assert all(card.col.get("xs") == 12 and card.col.get("sm") == 6 for card in kpis)
    assert any(isinstance(node, ft.IconButton) and node.tooltip == "Actualizar dashboard" for node in nodes)
    assert any(isinstance(node, ft.ProgressRing) for node in walk(dashboard_view(context(), "loading")))
    assert dashboard_view({}, "event_required", on_select_event=lambda: None).data["dashboard_state"] == "event_required"
    assert dashboard_view(context(), "error", mensaje="Error controlado", on_retry=lambda: None).data["dashboard_state"] == "error"
    for width in (360, 768, 1280):
        host = ft.Container(width=width, content=dashboard_view(context(), "ready", IndicadoresDashboard()))
        assert isinstance(host.content, ft.ListView) and host.content.expand is True


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print("[OK]", test.__name__)
    print(f"[OK] Dashboard: {len(tests)} grupos de pruebas.")

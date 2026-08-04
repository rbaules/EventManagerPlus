from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import flet as ft

from services.dashboard_service import DashboardRefreshController, calcular_indicadores_dashboard, construir_intervalos_llegadas
from services.evento_context_service import es_evento_autorizado, establecer_evento_activo
from services.navigation_service import parse_app_route, route_for
from views.dashboard_view import dashboard_view
from views.event_selection_view import event_selection_view
from views.eventos_admin_view import EventFormState, evento_detail_view, evento_form_view
from views.invitados_view import invitado_detail_view, invitado_form_view


def _guest(mesa: Any, arrived: bool, novelty: bool = False, guest_id: str = "u", timestamp: str | None = None) -> dict[str, Any]:
    return {
        "ivt_invitado_uuid": guest_id,
        "ivt_mesa_id": mesa,
        "ivt_llegada_confirmada": arrived,
        "ivt_fecha_hora_conf_llegada": timestamp,
        "ivt_tiene_novedad": novelty,
        "ivt_estado": "Activo",
    }


def _table(table_id: int) -> dict[str, Any]:
    return {"mes_mesa_id": table_id, "mes_estado": "Activo"}


def test_metricas_dashboard() -> None:
    data = calcular_indicadores_dashboard(
        [
            _guest(1, True, True, "a", "2026-08-02T18:02:00-05:00"), _guest(1, False, False, "b"),
            _guest(2, True, True, "c", "2026-08-02T18:30:00-05:00"), _guest(2, True, False, "d", "2026-08-02T19:45:00-05:00"),
            _guest(None, False, True, "e"), _guest(None, False, True, "e"),
        ],
        [_table(1), _table(2), _table(3)],
        "2026-08-02T18:00:00-05:00",
    )
    assert data.total_invitados == 5 and data.invitados_llegaron == 3
    assert data.porcentaje_invitados == 60.0
    assert data.total_mesas == 3
    assert data.mesas_con_invitados == 2
    assert data.mesas_completas == 1 and round(data.porcentaje_mesas, 2) == 33.33
    assert data.mesas_pendientes == 2
    assert data.mesas_parciales == 1 and data.mesas_sin_llegadas == 0
    assert data.invitados_con_novedad == 3
    assert data.invitados_pendientes == 2 and data.porcentaje_pendientes == 40.0
    assert data.primera_llegada == "6:02 p. m." and data.ultima_llegada == "7:45 p. m."
    assert len(data.intervalos_llegadas) == 8
    empty = calcular_indicadores_dashboard([], [_table(1)])
    assert empty.total_invitados == 0 and empty.porcentaje_invitados == 0
    assert empty.mesas_completas == 0 and empty.porcentaje_mesas == 0


def test_intervalos_limites_y_medianoche() -> None:
    start = datetime(2026, 8, 2, 23, 45, tzinfo=timezone(timedelta(hours=-5)))
    arrivals = [
        start - timedelta(minutes=5), start, start + timedelta(minutes=15),
        start + timedelta(minutes=30), start + timedelta(hours=2), start + timedelta(hours=2, seconds=1),
    ]
    intervals = construir_intervalos_llegadas(start.isoformat(), arrivals)
    assert len(intervals) == 8
    assert [item.cantidad for item in intervals] == [1, 1, 1, 0, 0, 0, 0, 0]
    assert intervals[1].inicio.date() != intervals[0].inicio.date()
    assert construir_intervalos_llegadas(None, arrivals) == ()


def _walk(control: ft.Control) -> list[ft.Control]:
    found = [control]
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        found.extend(_walk(content))
    for child in getattr(control, "controls", None) or []:
        if isinstance(child, ft.Control):
            found.extend(_walk(child))
    return found


def test_dashboard_responsivo_y_sin_contexto_redundante() -> None:
    data = calcular_indicadores_dashboard([], [], "2026-08-02T18:00:00-05:00")
    view = dashboard_view({"evento_actual": {"evento_id": 1}}, "ready", data)
    assert isinstance(view, ft.ListView)
    responsive = [control for control in view.controls if isinstance(control, ft.ResponsiveRow)]
    assert len(responsive) == 3
    cards = [control for row in responsive for control in row.controls]
    assert all(isinstance(card, ft.Container) and card.width is None for card in cards)
    assert all((card.col or {}).get("xs") == 12 for card in cards)
    assert any(isinstance(control, ft.IconButton) and control.tooltip == "Actualizar dashboard" for control in _walk(view))
    text = repr(view)
    for forbidden in ("Cuenta actual", "Rol del usuario", "Eventos disponibles", "Evento activo", "Fase del evento"):
        assert forbidden not in text
    for width in (360, 768, 1280):
        host = ft.Container(width=width, content=dashboard_view({"evento_actual": {"evento_id": 1}}, "ready", data))
        assert isinstance(host.content, ft.ListView) and host.content.expand is True


class _Future:
    def __init__(self) -> None:
        self.cancelled = False
    def done(self) -> bool:
        return self.cancelled
    def cancel(self) -> None:
        self.cancelled = True


class _Page:
    def __init__(self) -> None:
        self.calls = 0
        self.future = _Future()
    def run_task(self, runner: Any, generation: int) -> _Future:
        self.calls += 1
        self.runner = runner
        self.generation = generation
        return self.future


def test_control_actualizacion_aislado_sin_duplicados() -> None:
    page_a, page_b = _Page(), _Page()
    controller_a, controller_b = DashboardRefreshController(), DashboardRefreshController()
    async def runner(_generation: int) -> None:
        return None
    assert controller_a.start(page_a, runner)
    assert not controller_a.start(page_a, runner) and page_a.calls == 1
    assert controller_b.start(page_b, runner) and page_b.calls == 1
    generation = controller_a.generation
    assert controller_a.is_current(generation)
    controller_a.stop()
    assert page_a.future.cancelled and not controller_a.is_current(generation)


def test_rutas_y_atras() -> None:
    assert route_for("guests", "uuid estable") == "/app/invitados/uuid%20estable"
    assert parse_app_route("/app/invitados/uuid%20estable") == ("guests", "uuid estable", None)
    assert parse_app_route("/app/invitados/u-1/editar") == ("guests", "u-1", "editar")
    assert parse_app_route("/app/eventos/nuevo") == ("events_admin", "nuevo", None)
    assert parse_app_route("/app/eventos/10/editar") == ("events_admin", "10", "editar")
    assert parse_app_route("/app/eventos/seleccionar") == ("event_selection", None, None)
    assert parse_app_route("/app/lugares/form/crear_lugar") == ("locations", "form", "crear_lugar")


def test_autorizacion_y_contexto_evento() -> None:
    allowed = [{"cuenta_id": 1, "evento_id": 10, "nombre_evento": "A", "fase_evento": "Pre_evento", "estado": "Activo"}]
    denied = {"cuenta_id": 2, "evento_id": 20}
    assert es_evento_autorizado(allowed, allowed[0])
    assert not es_evento_autorizado(allowed, denied)
    context = {"cuentas_permitidas": [{"cuenta_id": 1}], "evento_actual": None, "rol_global_calculado": "Administrador"}
    establecer_evento_activo(context, allowed[0])
    assert context["evento_actual"]["evento_id"] == 10 and context["cuenta_actual"]["cuenta_id"] == 1


def test_vistas_dedicadas() -> None:
    callback = lambda *args, **kwargs: None
    guest = {"invitado_uuid": "u-1", "nombre_completo": "Ana", "estado_llegada": "Pendiente"}
    assert isinstance(invitado_detail_view(guest, False, False, "", callback, callback), ft.ListView)
    guest_form = {"modo": "crear", "datos": {}}
    assert isinstance(invitado_form_view(guest_form, [], True, False, "", callback, callback), ft.ListView)
    event = {"evento_id": 1, "nombre_evento": "Evento", "lugar_id": 1, "salon_id": 1}
    form = {"modo": "crear", "evento": {}, "estado_form": EventFormState.desde_evento("crear")}
    assert isinstance(evento_form_view(form, [], [], False, "", callback, callback, callback), ft.ListView)
    assert isinstance(evento_detail_view(event, [], [], callback, callback), ft.ListView)
    selection = event_selection_view([{"cuenta_id": 1, "evento_id": 1, "nombre_evento": "Evento"}], event, "ready", "", callback, callback, callback)
    assert isinstance(selection, ft.ListView)


if __name__ == "__main__":
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print("[OK]", test.__name__)
    print(f"[OK] Dashboard/navegación: {len(tests)} grupos.")

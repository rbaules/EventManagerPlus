from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import flet as ft

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.invitado_service import (
    listar_invitados,
    normalizar_invitado,
    obtener_invitado_por_id,
)
from views.invitados_view import FILTRO_LABELS, _hora_llegada, _invitado_card, _invitados_table, invitados_view


class Response:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class NotFilter:
    def __init__(self, query: "FakeQuery") -> None:
        self.query = query

    def is_(self, column: str, value: str) -> "FakeQuery":
        self.query.filters.append(("not_is", column, value))
        return self.query


class FakeQuery:
    def __init__(self, rows: list[dict[str, Any]], fail: Exception | None = None) -> None:
        self.rows = rows
        self.fail = fail
        self.filters: list[tuple[str, str, Any]] = []
        self.start = 0
        self.end: int | None = None
        self.not_ = NotFilter(self)

    def select(self, _columns: str) -> "FakeQuery":
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append(("eq", column, value))
        return self

    def ilike(self, column: str, value: str) -> "FakeQuery":
        self.filters.append(("ilike", column, value.replace("%", "").lower()))
        return self

    def in_(self, column: str, values: list[Any]) -> "FakeQuery":
        self.filters.append(("in", column, values))
        return self

    def is_(self, column: str, value: str) -> "FakeQuery":
        self.filters.append(("is", column, value))
        return self

    def order(self, column: str) -> "FakeQuery":
        self.rows = sorted(self.rows, key=lambda row: str(row.get(column) or ""))
        return self

    def range(self, start: int, end: int) -> "FakeQuery":
        self.start = start
        self.end = end
        return self

    def limit(self, _count: int) -> "FakeQuery":
        return self

    def execute(self) -> Response:
        if self.fail:
            raise self.fail
        data = list(self.rows)
        for op, column, value in self.filters:
            if op == "eq":
                data = [row for row in data if row.get(column) == value]
            elif op == "ilike":
                data = [row for row in data if value in str(row.get(column) or "").lower()]
            elif op == "in":
                data = [row for row in data if row.get(column) in value]
            elif op == "is":
                data = [row for row in data if row.get(column) is None]
            elif op == "not_is":
                data = [row for row in data if row.get(column) is not None]
        if self.end is not None:
            data = data[self.start : self.end + 1]
        return Response(data)


class FakeSupabase:
    def __init__(self, rows: list[dict[str, Any]], fail: Exception | None = None) -> None:
        self.rows = rows
        self.fail = fail

    def table(self, name: str) -> FakeQuery:
        if name == "evp_mes_mesa":
            mesas = [
                {"mes_cuenta_id": 1, "mes_evento_id": 10, "mes_mesa_id": 2, "mes_nombre_mesa": "Mesa 2", "mes_estado": "Activo"},
                {"mes_cuenta_id": 1, "mes_evento_id": 10, "mes_mesa_id": 5, "mes_nombre_mesa": "Mesa 5", "mes_estado": "Activo"},
            ]
            return FakeQuery(mesas, self.fail)
        assert name == "evp_ivt_invitado"
        return FakeQuery(self.rows, self.fail)


def row(
    invitado_id: int,
    nombre: str | None,
    *,
    mesa: int | None = None,
    llegada: bool = False,
    imprevisto: bool = False,
    estado: str = "Activo",
) -> dict[str, Any]:
    normalizado = (nombre or "").lower().replace("á", "a").replace("é", "e")
    return {
        "ivt_cuenta_id": 1,
        "ivt_evento_id": 10,
        "ivt_invitacion_id": 100,
        "ivt_invitado_id": invitado_id,
        "ivt_invitado_uuid": f"uuid-{invitado_id}",
        "ivt_nombre_invitado": nombre,
        "ivt_nombre_invitado_normalizado": normalizado,
        "ivt_es_invitado_principal": invitado_id == 1,
        "ivt_es_invitado_imprevisto": imprevisto,
        "ivt_email": None,
        "ivt_telefono": "",
        "ivt_mesa_id": mesa,
        "ivt_puesto_id": None,
        "ivt_llegada_confirmada": llegada,
        "ivt_fecha_hora_conf_llegada": None,
        "ivt_tiene_novedad": False,
        "ivt_descripcion_novedad": None,
        "ivt_estado": estado,
    }


ROWS = [
    row(1, "Ana Perez", mesa=2, llegada=True),
    row(2, "Luis Gomez", mesa=None),
    row(3, "Maria Lopez", mesa=5, imprevisto=True),
    row(4, "Suspendido", estado="Suspendido"),
]


EVENTO = {"cuenta_id": 1, "evento_id": 10, "nombre_evento": "Evento Test", "fase_evento": "En_proceso"}
CONTEXTO = {"evento_actual": EVENTO}


def test_listados_busqueda_filtros_y_paginas() -> None:
    varios = listar_invitados(EVENTO, supabase=FakeSupabase(ROWS), limit=10)
    assert varios.ok and len(varios.invitados) == 3

    uno = listar_invitados(EVENTO, busqueda="ana", supabase=FakeSupabase(ROWS), limit=10)
    assert uno.ok and len(uno.invitados) == 1

    sin = listar_invitados(EVENTO, busqueda="zzzz", supabase=FakeSupabase(ROWS), limit=10)
    assert sin.ok and sin.estado == "no_results"

    llegaron = listar_invitados(EVENTO, filtro="llegaron", supabase=FakeSupabase(ROWS), limit=10)
    assert len(llegaron.invitados) == 1

    con_mesa = listar_invitados(EVENTO, filtro="con_mesa", supabase=FakeSupabase(ROWS), limit=10)
    assert len(con_mesa.invitados) == 2

    filas_novedad = [dict(item) for item in ROWS]
    filas_novedad[0]["ivt_tiene_novedad"] = True
    con_novedad = listar_invitados(EVENTO, filtro="con_novedad", supabase=FakeSupabase(filas_novedad), limit=10)
    sin_novedad = listar_invitados(EVENTO, filtro="sin_novedad", supabase=FakeSupabase(filas_novedad), limit=10)
    assert len(con_novedad.invitados) == 1 and len(sin_novedad.invitados) == 2

    mesa = listar_invitados(EVENTO, busqueda="mesa 5", tipo_busqueda="mesa", supabase=FakeSupabase(ROWS), limit=10)
    assert mesa.ok and mesa.mesas_coincidentes == 1 and len(mesa.invitados) == 1

    mesa_parcial = listar_invitados(EVENTO, busqueda="2", tipo_busqueda="mesa", supabase=FakeSupabase(ROWS), limit=10)
    assert mesa_parcial.ok and len(mesa_parcial.invitados) == 1

    mesa_sin = listar_invitados(EVENTO, busqueda="vip", tipo_busqueda="mesa", supabase=FakeSupabase(ROWS), limit=10)
    assert mesa_sin.ok and mesa_sin.estado == "no_results"

    primera = listar_invitados(EVENTO, supabase=FakeSupabase(ROWS), limit=2, offset=0)
    assert len(primera.invitados) == 2 and primera.has_more

    segunda = listar_invitados(EVENTO, supabase=FakeSupabase(ROWS), limit=2, offset=2)
    assert len(segunda.invitados) == 1


def test_evento_nulo_errores_detalle_y_normalizacion() -> None:
    sin_evento = listar_invitados(None, supabase=FakeSupabase(ROWS))
    assert not sin_evento.ok and sin_evento.estado == "event_required"

    permiso = listar_invitados(EVENTO, supabase=FakeSupabase(ROWS, PermissionError("permission denied")))
    assert not permiso.ok and permiso.estado == "permission_denied"

    conexion = listar_invitados(EVENTO, supabase=FakeSupabase(ROWS, RuntimeError("network down")))
    assert not conexion.ok and conexion.estado == "connection_error"

    detalle = obtener_invitado_por_id(EVENTO, "uuid-1", supabase=FakeSupabase(ROWS))
    assert detalle.ok and detalle.invitado and detalle.invitado["nombre_completo"] == "Ana Perez"

    no_encontrado = obtener_invitado_por_id(EVENTO, "missing", supabase=FakeSupabase(ROWS))
    assert not no_encontrado.ok and no_encontrado.estado == "not_found"

    normalizado = normalizar_invitado(row(9, None))
    assert normalizado and normalizado["nombre_completo"] == "Invitado sin nombre"


def test_ui_builds() -> None:
    invitado = normalizar_invitado(ROWS[0])
    assert invitado
    controls = [
        build_view(CONTEXTO, "loading", [], "Cargando", "", "todos", False, True, None),
        build_view(CONTEXTO, "ready", [invitado], "OK", "", "todos", False, False, invitado),
        build_view(CONTEXTO, "empty", [], "Este evento todavia no tiene invitados registrados.", "", "todos", False, False, None),
        build_view(CONTEXTO, "no_results", [], "No se encontraron invitados.", "x", "todos", False, False, None),
        build_view(CONTEXTO, "error", [], "No fue posible cargar los invitados.", "", "todos", False, False, None),
        build_view({"evento_actual": None}, "event_required", [], "Selecciona un evento.", "", "todos", False, False, None),
    ]
    for control in controls:
        assert control is not None


def test_grid_desktop_cards_mobile_y_acciones() -> None:
    pendientes = normalizar_invitado(ROWS[1])
    llegado_row = dict(ROWS[0])
    llegado_row["ivt_fecha_hora_conf_llegada"] = "2026-08-11T19:05:00+00:00"
    llegado_row["ivt_tiene_novedad"] = True
    llegado_row["ivt_descripcion_novedad"] = "Requiere apoyo"
    llegado = normalizar_invitado(llegado_row)
    assert pendientes is not None and llegado is not None

    noop = lambda value=None: None
    desktop = _invitados_table(
        [pendientes, llegado], noop, noop, noop, noop,
        can_manage=True, can_confirm_arrival=True, can_reverse_arrival=True,
    )
    assert isinstance(desktop, ft.Row)
    assert isinstance(desktop.controls[0], ft.DataTable)
    table = desktop.controls[0]
    assert [column.label for column in table.columns] == [
        "Invitado", "Invitacion / Grupo", "Mesa", "Estado", "Hora llegada", "Novedad", "Acciones",
    ]
    assert len(table.rows) == 2
    assert len(table.rows[0].cells[-1].content.controls) == 4  # detalle, novedad, editar, registrar
    assert len(table.rows[1].cells[-1].content.controls) == 4  # detalle, novedad, editar, reversar
    assert _hora_llegada(pendientes) == "—"
    assert _hora_llegada(llegado) == "02:05 PM"

    mobile = _invitado_card(
        pendientes, noop, noop, noop, noop,
        can_manage=False, can_confirm_arrival=False, can_reverse_arrival=False, can_edit_novelty=False,
    )
    assert isinstance(mobile, ft.Container)
    assert mobile.col == {"xs": 12, "sm": 6}
    assert len(mobile.content.controls[-1].controls) == 1  # Consulta sin novedad: solo detalle
    consulta_novedad = _invitado_card(
        llegado, noop, noop, noop, noop,
        can_manage=False, can_confirm_arrival=False, can_reverse_arrival=False, can_edit_novelty=False,
    )
    novelty = consulta_novedad.content.controls[-1].controls[-1]
    assert novelty.tooltip == "Ver novedad" and novelty.icon == ft.Icons.DESCRIPTION
    assert novelty.icon != consulta_novedad.content.controls[-1].controls[0].icon
    assert "Previstos" not in FILTRO_LABELS.values() and "Imprevistos" not in FILTRO_LABELS.values()


def build_view(
    contexto: dict[str, Any],
    estado: str,
    invitados: list[dict[str, Any]],
    mensaje: str,
    busqueda: str,
    filtro: str,
    has_more: bool,
    is_loading: bool,
    invitado_detalle: dict[str, Any] | None,
) -> Any:
    return invitados_view(
        contexto,
        estado,
        invitados,
        mensaje,
        "invitado",
        busqueda,
        filtro,
        has_more,
        is_loading,
        invitado_detalle,
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
        lambda: None,
        lambda value=None: None,
        lambda value=None: None,
        lambda value=None: None,
        lambda value=None: None,
        lambda value=None: None,
        lambda value=None: None,
        lambda: None,
    )


def main() -> int:
    test_listados_busqueda_filtros_y_paginas()
    test_evento_nulo_errores_detalle_y_normalizacion()
    test_ui_builds()
    test_grid_desktop_cards_mobile_y_acciones()
    print("OK - guest read-only service, search, filters, pagination, detail, and UI tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

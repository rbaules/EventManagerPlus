from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.invitado_service import (
    listar_invitados,
    normalizar_invitado,
    obtener_invitado_por_id,
)
from views.invitados_view import invitados_view


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

    combinado = listar_invitados(EVENTO, busqueda="maria", filtro="imprevistos", supabase=FakeSupabase(ROWS), limit=10)
    assert len(combinado.invitados) == 1

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
    print("OK - guest read-only service, search, filters, pagination, detail, and UI tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

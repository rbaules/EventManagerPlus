from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.invitado_service import (
    cargar_grupo_invitacion,
    confirmar_llegadas_invitados,
    listar_invitados,
    normalizar_invitado,
)
from views.arrivals_view import arrivals_view


class Response:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


def normalizar(nombre: str) -> str:
    return " ".join(nombre.strip().lower().split())


def row(
    invitado_id: int,
    nombre: str,
    *,
    invitacion: int = 100,
    cuenta: int = 1,
    evento: int = 10,
    llegada: bool = False,
) -> dict[str, Any]:
    return {
        "ivt_cuenta_id": cuenta,
        "ivt_evento_id": evento,
        "ivt_invitacion_id": invitacion,
        "ivt_invitado_id": invitado_id,
        "ivt_invitado_uuid": f"uuid-{cuenta}-{evento}-{invitacion}-{invitado_id}",
        "ivt_nombre_invitado": nombre,
        "ivt_nombre_invitado_normalizado": normalizar(nombre),
        "ivt_es_invitado_principal": invitado_id == 1,
        "ivt_es_invitado_imprevisto": False,
        "ivt_email": None,
        "ivt_telefono": None,
        "ivt_mesa_id": 4,
        "ivt_puesto_id": invitado_id,
        "ivt_llegada_confirmada": llegada,
        "ivt_fecha_hora_conf_llegada": "2026-07-16T20:00:00+00:00" if llegada else None,
        "ivt_usuario_conf_llegada": "user-1" if llegada else None,
        "ivt_tiene_novedad": False,
        "ivt_descripcion_novedad": None,
        "ivt_estado": "Activo",
    }


INVITACIONES = [
    {
        "inv_cuenta_id": 1,
        "inv_evento_id": 10,
        "inv_invitacion_id": 100,
        "inv_cod_abrev_invitacion": "ABC",
        "inv_destinatario_invitacion": "Familia Demo",
        "inv_estado": "Activo",
    },
    {
        "inv_cuenta_id": 1,
        "inv_evento_id": 10,
        "inv_invitacion_id": 200,
        "inv_cod_abrev_invitacion": "XYZ",
        "inv_destinatario_invitacion": "Otra familia",
        "inv_estado": "Activo",
    },
]


class FakeQuery:
    def __init__(self, db: "FakeSupabase", table_name: str) -> None:
        self.db = db
        self.table_name = table_name
        self.filters: list[tuple[str, Any]] = []
        self.mode = "select"
        self.payload: dict[str, Any] = {}

    def select(self, _columns: str) -> "FakeQuery":
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def ilike(self, column: str, value: str) -> "FakeQuery":
        self.filters.append((column, value.replace("%", "").lower()))
        return self

    def order(self, column: str) -> "FakeQuery":
        rows = self._rows()
        rows.sort(key=lambda item: (item.get(column) is None, item.get(column)))
        return self

    def range(self, _start: int, _end: int) -> "FakeQuery":
        return self

    def limit(self, _count: int) -> "FakeQuery":
        return self

    def update(self, payload: dict[str, Any]) -> "FakeQuery":
        self.mode = "update"
        self.payload = dict(payload)
        return self

    def _rows(self) -> list[dict[str, Any]]:
        if self.table_name == "evp_inv_invitacion":
            return self.db.invitaciones
        if self.table_name == "evp_eve_evento":
            return [self.db.evento]
        return self.db.invitados

    def execute(self) -> Response:
        if self.db.fail:
            raise self.db.fail
        rows = self._rows()
        matched = list(rows)
        for column, value in self.filters:
            if column == "ivt_nombre_invitado_normalizado":
                matched = [item for item in matched if value in str(item.get(column) or "").lower()]
            else:
                matched = [item for item in matched if item.get(column) == value]
        if self.mode == "update":
            for item in matched:
                item.update(self.payload)
            return Response(matched)
        return Response(matched)


class FakeSupabase:
    def __init__(
        self,
        invitados: list[dict[str, Any]],
        *,
        fase: str = "En_proceso",
        estado: str = "Activo",
        fail: Exception | None = None,
    ) -> None:
        self.invitados = invitados
        self.invitaciones = [dict(item) for item in INVITACIONES]
        self.fail = fail
        self.evento = {
            "eve_cuenta_id": 1,
            "eve_evento_id": 10,
            "eve_fase_evento": fase,
            "eve_estado": estado,
        }

    def table(self, name: str) -> FakeQuery:
        assert name in {"evp_ivt_invitado", "evp_inv_invitacion", "evp_eve_evento"}
        return FakeQuery(self, name)


def contexto(rol: str = "Operador", fase: str = "En_proceso", estado: str = "Activo") -> dict[str, Any]:
    evento = {
        "cuenta_id": 1,
        "evento_id": 10,
        "nombre_evento": "Evento Test",
        "fase_evento": fase,
        "estado": estado,
        "rol": rol,
    }
    return {
        "usr_usuario_id": "user-1",
        "rol_global_calculado": rol,
        "evento_actual": evento,
        "eventos_permitidos": [evento],
        "puede_registrar_llegadas": rol in {"Master", "Administrador", "Operador"} and fase == "En_proceso" and estado == "Activo",
    }


def invitado(data: dict[str, Any]) -> dict[str, Any]:
    normalizado = normalizar_invitado(data)
    assert normalizado is not None
    return normalizado


def test_busqueda_y_grupo_por_invitacion() -> None:
    rows = [
        row(1, "Carlos Rodriguez"),
        row(2, "Maria Gonzalez"),
        row(3, "Laura Perez"),
        row(4, "Pedro Rodriguez", invitacion=200),
    ]
    db = FakeSupabase(rows)
    buscados = listar_invitados(contexto()["evento_actual"], busqueda="carlos", supabase=db)
    assert buscados.ok and len(buscados.invitados) == 1

    grupo = cargar_grupo_invitacion(contexto()["evento_actual"], buscados.invitados[0], supabase=db)
    assert grupo.ok
    assert grupo.invitacion and grupo.invitacion["invitacion_id"] == 100
    assert {item["nombre_completo"] for item in grupo.invitados} == {
        "Carlos Rodriguez",
        "Maria Gonzalez",
        "Laura Perez",
    }


def test_confirmacion_parcial_y_ya_confirmados() -> None:
    rows = [
        row(1, "Carlos Rodriguez"),
        row(2, "Maria Gonzalez"),
        row(3, "Laura Perez"),
        row(4, "Pedro Rodriguez", llegada=True),
    ]
    db = FakeSupabase(rows)
    base = invitado(rows[0])
    grupo = cargar_grupo_invitacion(contexto()["evento_actual"], base, supabase=db)
    assert grupo.ok and len(grupo.invitados) == 4

    seleccion = [grupo.invitados[0], grupo.invitados[1], grupo.invitados[2]]
    resultado = confirmar_llegadas_invitados(contexto(), grupo.invitacion, seleccion, supabase=db)
    assert resultado.ok and resultado.confirmados == 3
    assert rows[0]["ivt_llegada_confirmada"] is True
    assert rows[1]["ivt_llegada_confirmada"] is True
    assert rows[2]["ivt_llegada_confirmada"] is True
    assert rows[3]["ivt_llegada_confirmada"] is True

    repetido = confirmar_llegadas_invitados(contexto(), grupo.invitacion, seleccion, supabase=db)
    assert not repetido.ok and repetido.estado == "no_updates"


def test_reglas_fase_rol_evento_y_integridad() -> None:
    rows = [row(1, "Carlos Rodriguez"), row(2, "Otro Evento", cuenta=2, evento=10)]
    db = FakeSupabase(rows)
    grupo = cargar_grupo_invitacion(contexto()["evento_actual"], invitado(rows[0]), supabase=db)
    assert grupo.ok

    consulta = confirmar_llegadas_invitados(contexto("Consulta"), grupo.invitacion, [grupo.invitados[0]], supabase=db)
    assert not consulta.ok and consulta.estado == "role_denied"

    pre = confirmar_llegadas_invitados(contexto("Operador", "Pre_evento"), grupo.invitacion, [grupo.invitados[0]], supabase=db)
    assert not pre.ok and pre.estado == "phase_denied"

    fase_real = confirmar_llegadas_invitados(contexto(), grupo.invitacion, [grupo.invitados[0]], supabase=FakeSupabase(rows, fase="Post_evento"))
    assert not fase_real.ok and fase_real.estado == "phase_denied"

    otro_evento = dict(grupo.invitados[0], cuenta_id=2)
    integridad = confirmar_llegadas_invitados(contexto(), grupo.invitacion, [otro_evento], supabase=db)
    assert not integridad.ok and integridad.estado == "no_updates"


def test_ui_arrivals_builds() -> None:
    item = invitado(row(1, "Carlos Rodriguez"))
    control = arrivals_view(
        contexto(),
        "ready",
        "",
        "carlos",
        [item],
        {"cuenta_id": 1, "evento_id": 10, "invitacion_id": 100, "destinatario": "Familia Demo", "codigo": "ABC"},
        [item],
        {str(item["invitado_uuid"])},
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
    )
    assert control is not None

    bloqueado = arrivals_view(
        contexto("Consulta"),
        "idle",
        "",
        "",
        [],
        None,
        [],
        set(),
        False,
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
    )
    assert bloqueado is not None


def main() -> int:
    test_busqueda_y_grupo_por_invitacion()
    test_confirmacion_parcial_y_ya_confirmados()
    test_reglas_fase_rol_evento_y_integridad()
    test_ui_arrivals_builds()
    print("OK - arrivals by invitation search, grouping, partial confirmation, authorization, and UI tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

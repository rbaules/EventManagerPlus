from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.invitado_service import (
    confirmar_llegada,
    crear_invitado_imprevisto,
    eliminar_invitado_imprevisto,
    normalizar_invitado,
    puede_confirmar_llegada,
    puede_eliminar_imprevisto,
    puede_registrar_imprevisto,
    puede_reversar_llegada,
    reversar_llegada,
)
from views.invitados_view import invitados_view


class Response:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


def normalizar(nombre: str) -> str:
    return " ".join(nombre.strip().lower().split())


def invitado_row(
    invitado_id: int,
    nombre: str,
    *,
    cuenta: int = 1,
    evento: int = 10,
    imprevisto: bool = False,
    llegada: bool = False,
    estado: str = "Activo",
) -> dict[str, Any]:
    return {
        "ivt_cuenta_id": cuenta,
        "ivt_evento_id": evento,
        "ivt_invitacion_id": 100,
        "ivt_invitado_id": invitado_id,
        "ivt_invitado_uuid": f"uuid-{cuenta}-{evento}-{invitado_id}",
        "ivt_nombre_invitado": nombre,
        "ivt_nombre_invitado_normalizado": normalizar(nombre),
        "ivt_es_invitado_principal": False,
        "ivt_es_invitado_imprevisto": imprevisto,
        "ivt_email": None,
        "ivt_telefono": None,
        "ivt_mesa_id": None,
        "ivt_puesto_id": None,
        "ivt_llegada_confirmada": llegada,
        "ivt_fecha_hora_conf_llegada": "2026-07-15T20:00:00+00:00" if llegada else None,
        "ivt_usuario_conf_llegada": "user-1" if llegada else None,
        "ivt_tiene_novedad": False,
        "ivt_descripcion_novedad": None,
        "ivt_estado": estado,
    }


def contexto(
    rol: str = "Administrador",
    fase: str = "En_proceso",
    estado: str = "Activo",
    autorizado: bool = True,
) -> dict[str, Any]:
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
        "eventos_permitidos": [evento] if autorizado else [],
    }


def payload(nombre: str = "Visitante Nuevo") -> dict[str, Any]:
    return {
        "invitacion_id": 100,
        "nombre_completo": nombre,
        "email": "",
        "telefono": "",
        "mesa_id": "",
        "puesto_id": "",
        "es_invitado_principal": False,
    }


class FakeQuery:
    def __init__(self, db: "FakeSupabase", table: str) -> None:
        self.db = db
        self.table_name = table
        self.filters: list[tuple[str, Any]] = []
        self.mode = "select"
        self.payload: dict[str, Any] = {}

    def select(self, _columns: str) -> "FakeQuery":
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def limit(self, _count: int) -> "FakeQuery":
        return self

    def order(self, _column: str) -> "FakeQuery":
        return self

    def insert(self, payload_data: dict[str, Any]) -> "FakeQuery":
        self.mode = "insert"
        self.payload = dict(payload_data)
        return self

    def update(self, payload_data: dict[str, Any]) -> "FakeQuery":
        self.mode = "update"
        self.payload = dict(payload_data)
        return self

    def execute(self) -> Response:
        if self.db.fail:
            raise self.db.fail
        if self.table_name == "evp_eve_evento":
            rows = [self.db.evento_row]
        else:
            rows = self.db.invitados

        if self.mode == "insert":
            new_id = max([row["ivt_invitado_id"] for row in self.db.invitados] or [0]) + 1
            row = dict(self.payload)
            row["ivt_invitado_id"] = new_id
            row["ivt_invitado_uuid"] = f"uuid-{row['ivt_cuenta_id']}-{row['ivt_evento_id']}-{new_id}"
            row["ivt_nombre_invitado_normalizado"] = normalizar(row["ivt_nombre_invitado"])
            row.setdefault("ivt_fecha_hora_conf_llegada", None)
            row.setdefault("ivt_usuario_conf_llegada", None)
            row.setdefault("ivt_tiene_novedad", False)
            row.setdefault("ivt_descripcion_novedad", None)
            self.db.invitados.append(row)
            return Response([row])

        matched = [row for row in rows if all(row.get(column) == value for column, value in self.filters)]
        if self.mode == "update":
            for row in matched:
                row.update(self.payload)
            return Response(matched)
        return Response(matched)


class FakeSupabase:
    def __init__(
        self,
        invitados: list[dict[str, Any]] | None = None,
        *,
        fase_real: str = "En_proceso",
        estado_real: str = "Activo",
        fail: Exception | None = None,
    ) -> None:
        self.invitados = invitados or []
        self.fail = fail
        self.evento_row = {
            "eve_cuenta_id": 1,
            "eve_evento_id": 10,
            "eve_fase_evento": fase_real,
            "eve_estado": estado_real,
        }

    def table(self, name: str) -> FakeQuery:
        assert name in {"evp_ivt_invitado", "evp_eve_evento"}
        return FakeQuery(self, name)


def invitado(rows: list[dict[str, Any]], index: int = 0) -> dict[str, Any]:
    item = normalizar_invitado(rows[index])
    assert item is not None
    return item


def test_autorizacion_operativa() -> None:
    assert puede_confirmar_llegada(contexto("Administrador"))
    assert puede_confirmar_llegada(contexto("Master"))
    assert puede_confirmar_llegada(contexto("Operador"))
    assert not puede_confirmar_llegada(contexto("Consulta"))
    assert not puede_confirmar_llegada(contexto("Administrador", "Pre_evento"))
    assert not puede_confirmar_llegada(contexto("Administrador", "Post_evento"))
    assert not puede_confirmar_llegada(contexto("Administrador", "En_proceso", "Inactivo"))
    assert not puede_confirmar_llegada(contexto("Administrador", "En_proceso", "Activo", autorizado=False))
    assert puede_reversar_llegada(contexto("Administrador"))
    assert puede_reversar_llegada(contexto("Master"))
    assert puede_reversar_llegada(contexto("Operador"))
    assert puede_registrar_imprevisto(contexto("Operador"))
    assert puede_eliminar_imprevisto(contexto("Operador"))


def test_confirmar_llegada() -> None:
    rows = [invitado_row(1, "Ana Perez")]
    db = FakeSupabase(rows)
    resultado = confirmar_llegada(contexto("Operador"), invitado(rows), supabase=db)
    assert resultado.ok and rows[0]["ivt_llegada_confirmada"] is True
    assert rows[0]["ivt_usuario_conf_llegada"] == "user-1"

    repetido = confirmar_llegada(contexto("Operador"), invitado(rows), supabase=db)
    assert not repetido.ok and repetido.estado == "already_confirmed"

    fase = confirmar_llegada(contexto("Administrador"), invitado(rows), supabase=FakeSupabase(rows, fase_real="Post_evento"))
    assert not fase.ok and fase.estado == "phase_denied"

    permiso = confirmar_llegada(contexto("Consulta"), invitado(rows), supabase=db)
    assert not permiso.ok and permiso.estado == "role_denied"


def test_reversar_llegada() -> None:
    rows = [invitado_row(1, "Ana Perez", llegada=True)]
    db = FakeSupabase(rows)
    operador = reversar_llegada(contexto("Operador"), invitado(rows), supabase=db)
    assert operador.ok and rows[0]["ivt_llegada_confirmada"] is False

    rows[0]["ivt_llegada_confirmada"] = True
    rows[0]["ivt_fecha_hora_conf_llegada"] = "2026-07-15T20:00:00+00:00"
    rows[0]["ivt_usuario_conf_llegada"] = "user-1"
    admin = reversar_llegada(contexto("Administrador"), invitado(rows), supabase=db)
    assert admin.ok and rows[0]["ivt_llegada_confirmada"] is False
    assert rows[0]["ivt_fecha_hora_conf_llegada"] is None

    no_confirmada = reversar_llegada(contexto("Administrador"), invitado(rows), supabase=db)
    assert not no_confirmada.ok and no_confirmada.estado == "arrival_not_confirmed"


def test_imprevistos_creacion_y_eliminacion() -> None:
    rows = [invitado_row(1, "Ana Perez"), invitado_row(2, "Visitante Confirmado", imprevisto=True, llegada=True)]
    db = FakeSupabase(rows)
    creado = crear_invitado_imprevisto(contexto("Operador"), payload("Visitante Nuevo"), supabase=db)
    assert creado.ok and db.invitados[-1]["ivt_es_invitado_imprevisto"] is True
    assert db.invitados[-1]["ivt_llegada_confirmada"] is False

    duplicado = crear_invitado_imprevisto(contexto("Operador"), payload("visitante nuevo"), supabase=db)
    assert not duplicado.ok and duplicado.estado == "duplicate"

    pre_evento = crear_invitado_imprevisto(contexto("Operador", "Pre_evento"), payload("Otro"), supabase=db)
    assert not pre_evento.ok and pre_evento.estado == "phase_denied"

    planificado = eliminar_invitado_imprevisto(contexto("Operador"), invitado(rows, 0), supabase=db)
    assert not planificado.ok and planificado.estado == "not_unexpected"

    con_llegada = eliminar_invitado_imprevisto(contexto("Operador"), invitado(rows, 1), supabase=db)
    assert not con_llegada.ok and con_llegada.estado == "arrival_confirmed"

    imprevisto = normalizar_invitado(db.invitados[-1])
    assert imprevisto is not None
    eliminado = eliminar_invitado_imprevisto(contexto("Operador"), imprevisto, supabase=db)
    assert eliminado.ok and db.invitados[-1]["ivt_estado"] == "Inactivo"


def test_errores_controlados_y_ui() -> None:
    rows = [invitado_row(1, "Ana Perez")]
    rls = confirmar_llegada(contexto(), invitado(rows), supabase=FakeSupabase(rows, fail=PermissionError("permission denied")))
    assert not rls.ok and rls.estado == "permission_denied"

    otro_evento = dict(invitado(rows), evento_id=99)
    cambiado = confirmar_llegada(contexto(), otro_evento, supabase=FakeSupabase(rows))
    assert not cambiado.ok and cambiado.estado == "event_changed"

    control = invitados_view(
        contexto(),
        "ready",
        [invitado(rows)],
        "",
        "invitado",
        "",
        "todos",
        False,
        False,
        invitado(rows),
        False,
        True,
        True,
        True,
        True,
        [{"invitacion_id": 100, "destinatario": "Familia Demo", "codigo": "ABC"}],
        {"modo": "imprevisto", "datos": payload(), "original": None},
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
        lambda: None,
        lambda value=None: None,
        lambda value=None: None,
        lambda: None,
        lambda value=None: None,
        lambda value=None: None,
        lambda value=None: None,
    )
    assert control is not None


def main() -> int:
    test_autorizacion_operativa()
    test_confirmar_llegada()
    test_reversar_llegada()
    test_imprevistos_creacion_y_eliminacion()
    test_errores_controlados_y_ui()
    print("OK - live event guest arrival, reverse, unexpected guest, delete, and UI tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

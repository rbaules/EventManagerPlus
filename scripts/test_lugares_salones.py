from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import flet as ft

import components.event_header as event_header_module
from components.bottom_navigation import bottom_navigation
from components.event_header import event_header
from services.authorization_service import (
    capacidades_rol,
    ROL_ADMINISTRADOR,
    ROL_CONSULTA,
    ROL_MASTER,
    ROL_OPERADOR,
)
from services.lugar_service import (
    actualizar_lugar,
    actualizar_salon,
    cambiar_estado_lugar,
    cambiar_estado_salon,
    crear_lugar,
    crear_salon,
    listar_lugares,
    listar_salones,
    refrescar_catalogo_lugares,
)
from views.lugares_view import lugares_view


class Response:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, db: "FakeSupabase", table: str) -> None:
        self.db = db
        self.table = table
        self.filters: list[tuple[str, Any]] = []
        self.mode = "select"
        self.payload: dict[str, Any] = {}
        self.limit_count: int | None = None

    def select(self, _columns: str) -> "FakeQuery":
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((column, value))
        return self

    def order(self, _column: str) -> "FakeQuery":
        return self

    def limit(self, count: int) -> "FakeQuery":
        self.limit_count = count
        return self

    def insert(self, payload: dict[str, Any]) -> "FakeQuery":
        self.mode = "insert"
        self.payload = dict(payload)
        return self

    def update(self, payload: dict[str, Any]) -> "FakeQuery":
        self.mode = "update"
        self.payload = dict(payload)
        return self

    def delete(self) -> "FakeQuery":
        self.db.delete_calls += 1
        raise AssertionError("El modulo no debe ejecutar DELETE")

    def _rows(self) -> list[dict[str, Any]]:
        return self.db.tables[self.table]

    def _matched(self) -> list[dict[str, Any]]:
        rows = self._rows()
        for column, value in self.filters:
            rows = [row for row in rows if row.get(column) == value]
        return rows[: self.limit_count] if self.limit_count is not None else rows

    def execute(self) -> Response:
        self.db.calls.append((self.table, self.mode, tuple(self.filters), dict(self.payload)))
        if self.mode == "insert":
            row = dict(self.payload)
            if self.table == "evp_lug_lugar":
                ids = [
                    int(item["lug_lugar_id"])
                    for item in self._rows()
                    if item["lug_cuenta_id"] == row["lug_cuenta_id"]
                ]
                row["lug_lugar_id"] = max(ids, default=0) + 1
            elif self.table == "evp_sal_salon":
                ids = [
                    int(item["sal_salon_id"])
                    for item in self._rows()
                    if item["sal_cuenta_id"] == row["sal_cuenta_id"]
                    and item["sal_lugar_id"] == row["sal_lugar_id"]
                ]
                row["sal_salon_id"] = max(ids, default=0) + 1
            self._rows().append(row)
            return Response([dict(row)])
        matched = self._matched()
        if self.mode == "update":
            for row in matched:
                row.update(self.payload)
        return Response([dict(row) for row in matched])


class FakeSupabase:
    def __init__(self) -> None:
        self.delete_calls = 0
        self.calls: list[tuple[str, str, tuple[tuple[str, Any], ...], dict[str, Any]]] = []
        self.tables = {
            "evp_pai_pais": [
                {"pai_pais_id": "PA", "pai_nombre_pais": "Panamá"},
                {"pai_pais_id": "US", "pai_nombre_pais": "Estados Unidos"},
            ],
            "evp_lug_lugar": [
                {
                    "lug_cuenta_id": 1,
                    "lug_lugar_id": 1,
                    "lug_nombre_lugar": "Hotel Central",
                    "lug_direccion": "Avenida Uno",
                    "lug_ciudad": "Panamá",
                    "lug_pais_id": "PA",
                    "lug_tipo_lugar": "Hotel",
                    "lug_estado": "Activo",
                },
                {
                    "lug_cuenta_id": 2,
                    "lug_lugar_id": 1,
                    "lug_nombre_lugar": "Hotel Central",
                    "lug_direccion": "Otra cuenta",
                    "lug_ciudad": "Panamá",
                    "lug_pais_id": "PA",
                    "lug_tipo_lugar": "Hotel",
                    "lug_estado": "Activo",
                },
            ],
            "evp_sal_salon": [
                {
                    "sal_cuenta_id": 1,
                    "sal_lugar_id": 1,
                    "sal_salon_id": 1,
                    "sal_nombre_salon": "Gran Salón",
                    "sal_ubicacion": "Piso 2",
                    "sal_cant_max_mesas": 20,
                    "sal_cant_max_invitados": 200,
                    "sal_estado": "Activo",
                }
            ],
            "evp_eve_evento": [],
        }

    def table(self, name: str) -> FakeQuery:
        assert name in self.tables
        return FakeQuery(self, name)


def contexto(rol: str, cuenta_id: int = 1) -> dict[str, Any]:
    cuenta = {
        "cuenta_id": cuenta_id,
        "nombre_cuenta": f"Cuenta {cuenta_id}",
        "estado": "Activo",
        "rol": rol,
    }
    evento = {
        "cuenta_id": cuenta_id,
        "evento_id": 10,
        "fase_evento": "Pre_evento",
        "estado": "Activo",
        "rol": rol,
    }
    return {
        "usr_usuario_id": f"user-{rol}",
        "rol_global_calculado": rol,
        "cuentas_permitidas": [cuenta],
        "cuenta_actual": cuenta,
        "eventos_permitidos": [evento],
        "evento_actual": evento,
    }


LUGAR_PAYLOAD = {
    "nombre": "Centro de Convenciones",
    "direccion": "Calle 50",
    "ciudad": "Panamá",
    "pais_id": "PA",
    "tipo": "Sala de eventos",
}
SALON_PAYLOAD = {
    "nombre": "Salón Norte",
    "ubicacion": "Nivel 1",
    "cant_max_mesas": "12",
    "cant_max_invitados": "120",
}


def test_listados_roles_y_tenant() -> None:
    db = FakeSupabase()
    master = listar_lugares(db, contexto(ROL_MASTER))
    admin = listar_lugares(db, contexto(ROL_ADMINISTRADOR))
    assert master.ok and admin.ok
    assert [item["cuenta_id"] for item in master.items] == [1]
    assert [item["cuenta_id"] for item in admin.items] == [1]
    assert all(
        ("lug_cuenta_id", 1) in filters
        for table, mode, filters, _ in db.calls
        if table == "evp_lug_lugar" and mode == "select"
    )

    otra = listar_lugares(
        db,
        contexto(ROL_ADMINISTRADOR),
        {"cuenta_id": 2, "nombre_cuenta": "Cuenta 2"},
    )
    assert not otra.ok and otra.estado == "account_denied"
    for rol in (ROL_OPERADOR, ROL_CONSULTA):
        denied = listar_lugares(db, contexto(rol))
        assert not denied.ok and denied.estado == "role_denied"


def test_crear_lugar_duplicados_y_roles() -> None:
    db = FakeSupabase()
    for rol in (ROL_MASTER, ROL_ADMINISTRADOR):
        result = crear_lugar(db, contexto(rol), {**LUGAR_PAYLOAD, "nombre": f"Lugar {rol}"})
        assert result.ok and result.item and result.item["cuenta_id"] == 1

    for rol in (ROL_OPERADOR, ROL_CONSULTA):
        before = len(db.calls)
        denied = crear_lugar(db, contexto(rol), LUGAR_PAYLOAD)
        assert not denied.ok and denied.estado == "role_denied"
        assert len(db.calls) == before

    duplicate = crear_lugar(
        db,
        contexto(ROL_ADMINISTRADOR),
        {**LUGAR_PAYLOAD, "nombre": " hotel céntral "},
    )
    assert not duplicate.ok and duplicate.estado == "duplicate"

    same_other_tenant = crear_lugar(
        db,
        contexto(ROL_ADMINISTRADOR, cuenta_id=2),
        {**LUGAR_PAYLOAD, "nombre": "Centro de Convenciones"},
    )
    assert same_other_tenant.ok


def test_editar_lugar_ids_y_dependencias() -> None:
    db = FakeSupabase()
    admin = contexto(ROL_ADMINISTRADOR)
    edited = actualizar_lugar(
        db,
        admin,
        1,
        {**LUGAR_PAYLOAD, "nombre": "Hotel Central Renovado"},
    )
    assert edited.ok and edited.item and edited.item["nombre"] == "Hotel Central Renovado"

    for sensitive in (
        {"cuenta_id": 2},
        {"lugar_id": 9},
        {"lug_cuenta_id": 2},
        {"lug_lugar_id": 9},
    ):
        denied = actualizar_lugar(db, admin, 1, {**LUGAR_PAYLOAD, **sensitive})
        assert not denied.ok and denied.estado == "invalid_data"

    db.tables["evp_eve_evento"].append(
        {
            "eve_cuenta_id": 1,
            "eve_evento_id": 10,
            "eve_nombre_evento": "Evento Futuro",
            "eve_lugar_id": 1,
            "eve_salon_id": 1,
            "eve_fase_evento": "Pre_evento",
            "eve_estado": "Activo",
            "eve_fecha_hora_inicio": "2026-08-01T20:00:00+00:00",
        }
    )
    blocked = cambiar_estado_lugar(db, admin, 1, "Inactivo")
    assert not blocked.ok and blocked.estado == "dependency_blocked"
    db.tables["evp_eve_evento"].clear()
    changed = cambiar_estado_lugar(db, admin, 1, "Inactivo")
    assert changed.ok and changed.item and changed.item["estado"] == "Inactivo"
    assert db.delete_calls == 0


def test_salones_validaciones_roles_y_dependencias() -> None:
    db = FakeSupabase()
    admin = contexto(ROL_ADMINISTRADOR)
    created = crear_salon(db, admin, 1, SALON_PAYLOAD)
    assert created.ok and created.item and created.item["lugar_id"] == 1

    duplicate = crear_salon(
        db,
        admin,
        1,
        {**SALON_PAYLOAD, "nombre": " gran salón "},
    )
    assert not duplicate.ok and duplicate.estado == "duplicate"

    other_tenant = crear_salon(
        db,
        admin,
        999,
        SALON_PAYLOAD,
    )
    assert not other_tenant.ok and other_tenant.estado == "place_not_found"

    updated = actualizar_salon(
        db,
        admin,
        1,
        1,
        {**SALON_PAYLOAD, "nombre": "Gran Salón Renovado"},
    )
    assert updated.ok and updated.item and updated.item["nombre"] == "Gran Salón Renovado"
    identifier_change = actualizar_salon(
        db,
        admin,
        1,
        1,
        {**SALON_PAYLOAD, "salon_id": 99},
    )
    assert not identifier_change.ok and identifier_change.estado == "invalid_data"

    for rol in (ROL_OPERADOR, ROL_CONSULTA):
        denied_create = crear_salon(db, contexto(rol), 1, SALON_PAYLOAD)
        denied_edit = actualizar_salon(db, contexto(rol), 1, 1, SALON_PAYLOAD)
        assert denied_create.estado == "role_denied"
        assert denied_edit.estado == "role_denied"

    db.tables["evp_eve_evento"].append(
        {
            "eve_cuenta_id": 1,
            "eve_evento_id": 11,
            "eve_nombre_evento": "Evento Activo",
            "eve_lugar_id": 1,
            "eve_salon_id": 1,
            "eve_fase_evento": "En_proceso",
            "eve_estado": "Activo",
            "eve_fecha_hora_inicio": "2026-07-29T20:00:00+00:00",
        }
    )
    blocked = cambiar_estado_salon(db, admin, 1, 1, "Inactivo")
    assert not blocked.ok and blocked.estado == "dependency_blocked"
    db.tables["evp_eve_evento"].clear()
    changed = cambiar_estado_salon(db, admin, 1, 1, "Inactivo")
    assert changed.ok
    listed = listar_salones(db, admin, 1)
    assert listed.ok and listed.items
    assert db.delete_calls == 0


def _walk(control: Any) -> list[Any]:
    controls = [control]
    for attr in ("controls", "items", "destinations", "actions"):
        for child in getattr(control, attr, None) or []:
            controls.extend(_walk(child))
    for attr in ("content",):
        child = getattr(control, attr, None)
        if child is not None and not isinstance(child, (str, int, float, bool)):
            controls.extend(_walk(child))
    return controls


def _button_contents(control: Any) -> list[str]:
    result = []
    for item in _walk(control):
        content = getattr(item, "content", None)
        if isinstance(content, str):
            result.append(content)
    return result


def test_ui_roles_y_checkin() -> None:
    db = FakeSupabase()
    lugares = listar_lugares(db, contexto(ROL_ADMINISTRADOR)).items
    salones = listar_salones(db, contexto(ROL_ADMINISTRADOR), 1).items
    callbacks = [lambda *args: None] * 10
    admin_view = lugares_view(
        contexto(ROL_ADMINISTRADOR),
        "ready",
        "",
        lugares,
        lugares[0],
        salones,
        [{"pais_id": "PA", "nombre": "Panamá"}],
        None,
        "",
        False,
        True,
        *callbacks,
    )
    assert "Agregar lugar" in _button_contents(admin_view)
    denied_view = lugares_view(
        contexto(ROL_CONSULTA),
        "ready",
        "",
        lugares,
        lugares[0],
        salones,
        [],
        None,
        "",
        False,
        False,
        *callbacks,
    )
    assert "Agregar lugar" not in _button_contents(denied_view)
    assert any(
        isinstance(item, ft.Text) and item.value == "Acceso denegado"
        for item in _walk(denied_view)
    )

    full_header = event_header(
        contexto(ROL_ADMINISTRADOR),
        lambda: None,
        lambda: None,
        on_manage_locations=lambda: None,
    )
    assert "Lugares y salones" in _button_contents(full_header)

    original = event_header_module.is_checkin_mode
    event_header_module.is_checkin_mode = lambda: True
    try:
        checkin_header = event_header(
            contexto(ROL_ADMINISTRADOR),
            lambda: None,
            lambda: None,
            on_manage_locations=lambda: None,
        )
    finally:
        event_header_module.is_checkin_mode = original
    assert "Lugares y salones" not in _button_contents(checkin_header)
    nav = bottom_navigation("guests", True, True, lambda key: None)
    assert all(destination.label != "Lugares y salones" for destination in nav.destinations)


def test_capacidades_existentes_y_arquitectura() -> None:
    assert capacidades_rol(ROL_MASTER).puede_administrar_lugares
    assert capacidades_rol(ROL_ADMINISTRADOR).puede_crear_salon
    assert not capacidades_rol(ROL_OPERADOR).puede_administrar_lugares
    assert not capacidades_rol(ROL_CONSULTA).puede_crear_lugar
    assert capacidades_rol(ROL_MASTER).puede_registrar_llegada
    assert capacidades_rol(ROL_ADMINISTRADOR).puede_crear_invitado
    assert capacidades_rol(ROL_OPERADOR).puede_operar_evento
    assert capacidades_rol(ROL_CONSULTA).puede_consultar

    source = (ROOT / "services" / "lugar_service.py").read_text(encoding="utf-8")
    assert "get_supabase_client" not in source
    assert "create_supabase_client" not in source
    assert ".delete(" not in source
    for protected in ("auth_service.py", "session_service.py", "server_session_service.py"):
        assert "lugar_service" not in (ROOT / "services" / protected).read_text(encoding="utf-8")
    assert "lugar_service" not in (ROOT / "asgi.py").read_text(encoding="utf-8")


def test_recarga_inmediata_lugares_y_salones() -> None:
    db = FakeSupabase()
    admin = contexto(ROL_ADMINISTRADOR)
    initial = refrescar_catalogo_lugares(db, admin, 1)
    assert initial.ok and initial.lugar_seleccionado and initial.lugar_seleccionado["lugar_id"] == 1
    assert len({item["lugar_id"] for item in initial.lugares}) == len(initial.lugares)

    created_place = crear_lugar(db, admin, {**LUGAR_PAYLOAD, "nombre": "Centro Nuevo"})
    assert created_place.ok and created_place.item
    refreshed_place = refrescar_catalogo_lugares(db, admin, created_place.item["lugar_id"])
    assert refreshed_place.lugar_seleccionado and refreshed_place.lugar_seleccionado["nombre"] == "Centro Nuevo"
    updated_place = actualizar_lugar(db, admin, created_place.item["lugar_id"], {**LUGAR_PAYLOAD, "nombre": "Centro Editado"})
    assert updated_place.ok
    refreshed_place = refrescar_catalogo_lugares(db, admin, created_place.item["lugar_id"])
    assert refreshed_place.lugar_seleccionado and refreshed_place.lugar_seleccionado["nombre"] == "Centro Editado"

    created_room = crear_salon(db, admin, created_place.item["lugar_id"], {**SALON_PAYLOAD, "nombre": "Salón Nuevo"})
    assert created_room.ok and created_room.item
    refreshed_room = refrescar_catalogo_lugares(db, admin, created_place.item["lugar_id"])
    assert any(item["nombre"] == "Salón Nuevo" for item in refreshed_room.salones)
    updated_room = actualizar_salon(db, admin, created_place.item["lugar_id"], created_room.item["salon_id"], {**SALON_PAYLOAD, "nombre": "Salón Editado"})
    assert updated_room.ok
    refreshed_room = refrescar_catalogo_lugares(db, admin, created_place.item["lugar_id"])
    assert refreshed_room.lugar_seleccionado and refreshed_room.lugar_seleccionado["lugar_id"] == created_place.item["lugar_id"]
    assert any(item["nombre"] == "Salón Editado" for item in refreshed_room.salones)
    assert len({item["salon_id"] for item in refreshed_room.salones}) == len(refreshed_room.salones)


def main() -> int:
    test_listados_roles_y_tenant()
    test_crear_lugar_duplicados_y_roles()
    test_editar_lugar_ids_y_dependencias()
    test_salones_validaciones_roles_y_dependencias()
    test_ui_roles_y_checkin()
    test_capacidades_existentes_y_arquitectura()
    test_recarga_inmediata_lugares_y_salones()
    print("OK - lugares/salones: tenant, roles, CRUD lógico, dependencias, UI y CHECKIN.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import asyncio
import inspect
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.navigation_service import parse_app_route
import views.kiosk_view as kiosk_view
from views.kiosk_view import KioskPhase, is_kiosk_route


class Response:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data


class FakeSupabase:
    def __init__(self, *, qr_payload: dict[str, Any] | None = None, group_payload: dict[str, Any] | None = None) -> None:
        self.qr_payload = qr_payload or {
            "ok": True, "codigo_resultado": "QR_RESOLVED", "cuenta_id": 2, "evento_id": 9, "invitacion_id": 31,
        }
        self.group_payload = group_payload or {
            "ok": True,
            "codigo_resultado": "ARRIVAL_GROUP_LOADED",
            "destinatario": "Familia Real",
            "invitados": [
                {"invitado_id": 7, "nombre": "Ana Real", "mesa_id": 4, "mesa_nombre": "Mesa 4", "llegada_confirmada": False},
                {"invitado_id": 8, "nombre": "Luis Real", "mesa_id": 4, "mesa_nombre": "Mesa 4", "llegada_confirmada": True},
            ],
        }
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, name: str, params: dict[str, Any]) -> Any:
        self.calls.append((name, dict(params)))
        payload = self.qr_payload if name == "evp_oper_resolver_invitacion_qr" else self.group_payload
        return SimpleNamespace(execute=lambda: Response(payload))


class BlockingFirstResolverSupabase(FakeSupabase):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()
        self._block_first = True

    def rpc(self, name: str, params: dict[str, Any]) -> Any:
        response = super().rpc(name, params)
        if name != "evp_oper_resolver_invitacion_qr" or not self._block_first:
            return response
        self._block_first = False

        def execute() -> Response:
            self.started.set()
            assert self.release.wait(1)
            return response.execute()

        return SimpleNamespace(execute=execute)


class FakePage:
    def __init__(self) -> None:
        self.route = "/app/kiosk"
        self.on_route_change = None
        self.update_calls = 0
        self.tasks: list[asyncio.Task[Any]] = []

    def update(self) -> None:
        self.update_calls += 1

    def run_task(self, task_factory: Any) -> asyncio.Task[Any]:
        assert inspect.iscoroutinefunction(task_factory)
        task = asyncio.create_task(task_factory())
        self.tasks.append(task)
        return task


class FakeKioskScanner:
    def __init__(self, **kwargs: Any) -> None:
        self.host = None
        self.on_qr_finalized = kwargs["on_qr_finalized"]
        self.on_camera_error = kwargs["on_camera_error"]
        self.start_calls = 0
        self.restart_calls = 0
        self.recover_calls = 0
        self.stop_calls = 0
        self.preview_visible: list[bool] = []

    def set_preview_visible(self, visible: bool) -> None:
        self.preview_visible.append(visible)

    def start(self) -> None:
        self.start_calls += 1

    def restart(self) -> None:
        self.restart_calls += 1

    def recover_after_reconnect(self) -> None:
        self.recover_calls += 1

    async def stop_scan(self) -> None:
        self.stop_calls += 1

    def close(self, **_kwargs: Any) -> None:
        pass


def contexto() -> dict[str, Any]:
    event = {"cuenta_id": 2, "evento_id": 9, "estado": "Activo", "fase_evento": "En_proceso"}
    return {"usr_usuario_id": "operator-1", "evento_actual": event, "eventos_permitidos": [event]}


def walk(control: Any) -> list[Any]:
    nodes = [control]
    content = getattr(control, "content", None)
    if content is not None and content is not control:
        nodes.extend(walk(content))
    for child in getattr(control, "controls", None) or []:
        nodes.extend(walk(child))
    return nodes


async def drain(page: FakePage) -> None:
    while page.tasks:
        tasks, page.tasks = page.tasks[:], []
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        for outcome in outcomes:
            if isinstance(outcome, BaseException) and not isinstance(outcome, asyncio.CancelledError):
                raise outcome


def build(page: FakePage, database: FakeSupabase, user_context: dict[str, Any] | None = None) -> Any:
    original = kiosk_view.KioskQrScanner
    kiosk_view.KioskQrScanner = FakeKioskScanner
    try:
        return kiosk_view.build_kiosk_view(page=page, contexto_usuario=user_context or contexto(), supabase=database)
    finally:
        kiosk_view.KioskQrScanner = original


def test_route() -> None:
    assert is_kiosk_route("/app/kiosk")
    assert is_kiosk_route("/app/kiosk?demo=1")
    assert parse_app_route("/app/kiosk")[0] == "kiosk"
    assert not is_kiosk_route("/app/dashboard")


async def test_real_resolution_loads_active_group_and_preserves_arrival_state() -> None:
    page = FakePage()
    db = FakeSupabase()
    root = build(page, db)
    state = root.data["kiosk_state"]
    scanner = root.data["kiosk_scanner"]
    scanner.on_qr_finalized("ab12")
    assert state.phase == KioskPhase.RESOLVING
    await drain(page)

    assert [name for name, _params in db.calls] == ["evp_oper_resolver_invitacion_qr", "evp_oper_obtener_grupo_invitacion"]
    assert db.calls[0][1] == {"p_cuenta_id": 2, "p_evento_id": 9, "p_codigo": "AB12"}
    assert state.phase == KioskPhase.SELECT_GUESTS
    assert (state.cuenta_id, state.evento_id, state.invitation_id, state.destinatario) == (2, 9, 31, "Familia Real")
    assert state.selected_guest_ids == set()
    assert [guest.guest_id for guest in state.guests] == [7, 8]
    assert state.guests[0].mesa_texto == "Mesa 4"
    assert state.guests[1].llegada_confirmada and not state.guests[1].selectable
    state.set_guest_selected(8, True)
    assert state.selected_guest_ids == set()
    state.select_all_guests()
    assert state.selected_guest_ids == {7}
    assert state.table_heading() == "Mesa: Mesa 4"


async def test_qr_and_group_errors_never_publish_partial_data() -> None:
    for database, expected in (
        (FakeSupabase(qr_payload={"ok": False, "codigo_resultado": "QR_NOT_FOUND"}), "No se encontr"),
        (FakeSupabase(group_payload={"ok": False, "codigo_resultado": "ARRIVAL_NOT_ALLOWED"}), "No fue posible cargar"),
    ):
        page = FakePage()
        root = build(page, database)
        scanner = root.data["kiosk_scanner"]
        state = root.data["kiosk_state"]
        scanner.on_qr_finalized("AB12")
        await drain(page)
        assert state.phase == KioskPhase.ERROR
        assert expected in (state.error_message or "")
        assert state.invitation_id is None and state.guests == [] and state.selected_guest_ids == set()


async def test_empty_group_is_error_not_empty_selection_screen() -> None:
    page = FakePage()
    root = build(page, FakeSupabase(group_payload={"ok": True, "codigo_resultado": "ARRIVAL_GROUP_LOADED", "destinatario": "Sin activos", "invitados": []}))
    root.data["kiosk_scanner"].on_qr_finalized("AB12")
    await drain(page)
    state = root.data["kiosk_state"]
    assert state.phase == KioskPhase.ERROR
    assert state.error_message == "No se encontraron integrantes activos para esta invitacion."


async def test_reset_cancels_stale_resolution_without_overwriting_new_result() -> None:
    page = FakePage()
    db = BlockingFirstResolverSupabase()
    root = build(page, db)
    scanner = root.data["kiosk_scanner"]
    state = root.data["kiosk_state"]
    scanner.on_qr_finalized("A001")
    await asyncio.to_thread(db.started.wait, 1)
    root.data["reset_kiosk"]()
    assert state.phase == KioskPhase.WELCOME_SCAN
    scanner.on_qr_finalized("B002")
    db.release.set()
    await drain(page)
    assert state.phase == KioskPhase.SELECT_GUESTS
    assert state.invitation_id == 31 and state.destinatario == "Familia Real"
    assert state.selected_guest_ids == set() and scanner.restart_calls == 1


async def test_selected_invitation_can_return_to_scan_and_load_a_new_qr() -> None:
    page = FakePage()
    db = FakeSupabase()
    root = build(page, db)
    state = root.data["kiosk_state"]
    scanner = root.data["kiosk_scanner"]

    scanner.on_qr_finalized("A001")
    await drain(page)
    state.set_guest_selected(7, True)
    assert state.phase == KioskPhase.SELECT_GUESTS and state.selected_guest_ids == {7}
    back_to_scan = next(
        control for control in walk(root)
        if getattr(control, "content", None) == "Volver a escanear"
    )
    back_to_scan.on_click(SimpleNamespace())
    assert state.phase == KioskPhase.WELCOME_SCAN
    assert state.qr_code is None
    assert state.cuenta_id is None and state.evento_id is None and state.invitation_id is None
    assert state.destinatario is None and state.guests == [] and state.selected_guest_ids == set()
    assert scanner.restart_calls == 1

    db.qr_payload = {
        "ok": True, "codigo_resultado": "QR_RESOLVED", "cuenta_id": 2, "evento_id": 9, "invitacion_id": 32,
    }
    db.group_payload = {
        "ok": True,
        "codigo_resultado": "ARRIVAL_GROUP_LOADED",
        "destinatario": "Familia Nueva",
        "invitados": [{"invitado_id": 10, "nombre": "Nora Nueva", "mesa_id": 5, "mesa_nombre": "Mesa 5", "llegada_confirmada": False}],
    }
    scanner.on_qr_finalized("B002")
    await drain(page)
    assert state.phase == KioskPhase.SELECT_GUESTS
    assert state.invitation_id == 32 and state.destinatario == "Familia Nueva"
    assert [guest.guest_id for guest in state.guests] == [10]
    assert state.table_heading() == "Mesa: Mesa 5" and state.selected_guest_ids == set()


async def test_table_presentation_is_invitation_only() -> None:
    cases = (
        (
            [{"invitado_id": 1, "nombre": "Ana Pérez", "mesa_id": 11, "mesa_nombre": "Amor", "llegada_confirmada": False}],
            "Mesa: Amor",
        ),
        (
            [{"invitado_id": 2, "nombre": "Carlos Pérez", "mesa_id": 12, "mesa_nombre": "12", "llegada_confirmada": False}],
            "Mesa: 12",
        ),
        (
            [{"invitado_id": 3, "nombre": "Nora Pérez", "mesa_id": None, "mesa_nombre": None, "llegada_confirmada": False}],
            "Mesa: Sin asignar",
        ),
        (
            [
                {"invitado_id": 4, "nombre": "Ana Pérez", "mesa_id": 12, "mesa_nombre": "12", "llegada_confirmada": False},
                {"invitado_id": 5, "nombre": "María Pérez", "mesa_id": 13, "mesa_nombre": "13", "llegada_confirmada": True},
            ],
            "Mesa: Asignada por integrante",
        ),
    )
    for invitados, expected_heading in cases:
        page = FakePage()
        root = build(page, FakeSupabase(group_payload={
            "ok": True, "codigo_resultado": "ARRIVAL_GROUP_LOADED", "destinatario": "Familia Pérez", "invitados": invitados,
        }))
        root.data["kiosk_scanner"].on_qr_finalized("AB12")
        await drain(page)
        text_values = [node.value for node in walk(root) if isinstance(node, kiosk_view.ft.Text)]
        checkbox_labels = [node.label for node in walk(root) if isinstance(node, kiosk_view.ft.Checkbox)]
        assert expected_heading in text_values
        assert all("Mesa" not in label for label in checkbox_labels)
        if any(item.get("llegada_confirmada") for item in invitados):
            assert "María Pérez — Ya llegó" in checkbox_labels


async def test_route_exit_cancels_resolution_before_scanner_shutdown() -> None:
    page = FakePage()
    db = BlockingFirstResolverSupabase()
    root = build(page, db)
    scanner = root.data["kiosk_scanner"]
    state = root.data["kiosk_state"]
    scanner.on_qr_finalized("A001")
    await asyncio.to_thread(db.started.wait, 1)
    page.route = "/app/dashboard"
    assert page.on_route_change is not None
    page.on_route_change(SimpleNamespace(route="/app/dashboard"))
    db.release.set()
    await drain(page)
    assert scanner.stop_calls == 1
    assert state.invitation_id is None and state.guests == [] and state.selected_guest_ids == set()


async def test_reconnect_is_limited_to_welcome_scan() -> None:
    page = FakePage()
    root = build(page, FakeSupabase())
    scanner = root.data["kiosk_scanner"]
    state = root.data["kiosk_state"]
    resume = root.data["resume_dashboard"]
    resume()
    assert scanner.recover_calls == 1
    assert state.accept_scanned_qr("T3A1") is not None
    resume()
    assert scanner.recover_calls == 1


async def main_async() -> None:
    await test_real_resolution_loads_active_group_and_preserves_arrival_state()
    await test_qr_and_group_errors_never_publish_partial_data()
    await test_empty_group_is_error_not_empty_selection_screen()
    await test_reset_cancels_stale_resolution_without_overwriting_new_result()
    await test_selected_invitation_can_return_to_scan_and_load_a_new_qr()
    await test_table_presentation_is_invitation_only()
    await test_route_exit_cancels_resolution_before_scanner_shutdown()
    await test_reconnect_is_limited_to_welcome_scan()


def main() -> None:
    test_route()
    asyncio.run(main_async())
    print("Kiosk view tests passed.")


if __name__ == "__main__":
    main()

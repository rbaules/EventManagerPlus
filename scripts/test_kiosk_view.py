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


class FakeStorageBucket:
    def __init__(self, storage: "FakeStorage") -> None:
        self.storage = storage

    def create_signed_url(self, path: str, expires_in: int) -> dict[str, str]:
        self.storage.requests.append((self.storage.bucket_name, path, expires_in))
        self.storage.started.set()
        if self.storage.blocking:
            assert self.storage.release.wait(1)
        if self.storage.error is not None:
            raise self.storage.error
        if self.storage.url is None:
            return {}
        return {"signedURL": self.storage.url}


class FakeStorage:
    def __init__(
        self,
        *,
        url: str | None = None,
        error: Exception | None = None,
        blocking: bool = False,
    ) -> None:
        self.url = url
        self.error = error
        self.blocking = blocking
        self.bucket_name = ""
        self.requests: list[tuple[str, str, int]] = []
        self.started = threading.Event()
        self.release = threading.Event()

    def from_(self, bucket_name: str) -> FakeStorageBucket:
        self.bucket_name = bucket_name
        return FakeStorageBucket(self)


class FakeSupabase:
    def __init__(
        self,
        *,
        qr_payload: dict[str, Any] | None = None,
        group_payload: dict[str, Any] | None = None,
        confirmation_payload: dict[str, Any] | None = None,
        confirmation_error: Exception | None = None,
        storage: FakeStorage | None = None,
    ) -> None:
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
        self.confirmation_payload = confirmation_payload
        self.confirmation_error = confirmation_error
        self.calls: list[tuple[str, dict[str, Any]]] = []
        if storage is not None:
            self.storage = storage

    def rpc(self, name: str, params: dict[str, Any]) -> Any:
        self.calls.append((name, dict(params)))
        if name == "evp_oper_resolver_invitacion_qr":
            return SimpleNamespace(execute=lambda: Response(self.qr_payload))
        if name == "evp_oper_obtener_grupo_invitacion":
            return SimpleNamespace(execute=lambda: Response(self.group_payload))
        assert name == "evp_oper_confirmar_llegadas_invitacion"

        def execute() -> Response:
            if self.confirmation_error is not None:
                raise self.confirmation_error
            payload = self.confirmation_payload
            if payload is None:
                selected_ids = set(params["p_invitado_ids"])
                for guest in self.group_payload["invitados"]:
                    if guest["invitado_id"] in selected_ids:
                        guest["llegada_confirmada"] = True
                        guest["fecha_hora_llegada"] = "batch-time"
                payload = {
                    "ok": True,
                    "codigo_resultado": "ARRIVAL_CONFIRMED",
                    "confirmados": len(selected_ids),
                }
            return Response(payload)

        return SimpleNamespace(execute=execute)


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


class BlockingConfirmationSupabase(FakeSupabase):
    def __init__(self) -> None:
        super().__init__()
        self.started = threading.Event()
        self.release = threading.Event()

    def rpc(self, name: str, params: dict[str, Any]) -> Any:
        response = super().rpc(name, params)
        if name != "evp_oper_confirmar_llegadas_invitacion":
            return response

        def execute() -> Response:
            self.started.set()
            assert self.release.wait(1)
            return response.execute()

        return SimpleNamespace(execute=execute)


class FakePage:
    def __init__(self, *, width: int | None = None) -> None:
        self.route = "/app/kiosk"
        self.width = width
        self.scroll = kiosk_view.ft.ScrollMode.AUTO
        self.on_route_change = None
        self.overlay: list[Any] = []
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
    event = {
        "cuenta_id": 2,
        "evento_id": 9,
        "estado": "Activo",
        "fase_evento": "En_proceso",
        "rol": "Operador",
    }
    return {
        "usr_usuario_id": "operator-1",
        "evento_actual": event,
        "eventos_permitidos": [event],
        "puede_registrar_llegadas": True,
    }


def walk(control: Any) -> list[Any]:
    nodes = [control]
    content = getattr(control, "content", None)
    if content is not None and content is not control:
        nodes.extend(walk(content))
    for child in getattr(control, "controls", None) or []:
        nodes.extend(walk(child))
    return nodes


def button_with_label(root: Any, label: str) -> Any:
    return next(node for node in walk(root) if getattr(node, "content", None) == label)


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


def test_success_greeting_names_follow_updated_group_state() -> None:
    guest = kiosk_view.KioskGuest
    all_arrived = [
        guest(1, "Karla López", 1, "Mesa 1", True, "Llegó", None),
        guest(2, "Aaron Pérez", 1, "Mesa 1", True, "Llegó", None),
    ]
    assert kiosk_view.format_kiosk_success_name("Karla y Aaron", all_arrived, {1, 2}) == "Karla y Aaron"

    partial = [
        guest(1, "Karla López", 1, "Mesa 1", True, "Llegó", None),
        guest(2, "Aaron Pérez", 1, "Mesa 1", True, "Llegó", None),
        guest(3, "José Díaz", 1, "Mesa 1", False, "Pendiente", None),
    ]
    assert kiosk_view.format_kiosk_success_name("Familia", partial, {1}) == "Karla"
    assert kiosk_view.format_kiosk_success_name("Familia", partial, {1, 2}) == "Karla y Aaron"
    assert kiosk_view.format_kiosk_success_name("Familia", partial, {1, 2, 3}) == "Karla, Aaron y José"
    assert kiosk_view.format_kiosk_success_name(None, partial, set()) is None
    assert kiosk_view.kiosk_success_copy(1) == (
        "Esperamos que disfrutes lo que hemos preparado para ti.",
        "¡Bienvenido(a)!",
    )
    assert kiosk_view.kiosk_success_copy(2) == (
        "Esperamos que disfruten lo que hemos preparado para ustedes.",
        "¡Bienvenidos!",
    )

    all_arrived_single = [guest(1, "Karla López", 1, "Mesa 1", True, "Llegó", None)]
    assert kiosk_view.format_kiosk_success_name("Familia Karla", all_arrived_single, {1}) == "Familia Karla"
    assert kiosk_view.kiosk_success_copy(1) == (
        "Esperamos que disfrutes lo que hemos preparado para ti.",
        "¡Bienvenido(a)!",
    )


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


async def test_select_guests_visual_contract_and_select_all_pending_only() -> None:
    page = FakePage(width=1440)
    db = FakeSupabase(group_payload={
        "ok": True,
        "codigo_resultado": "ARRIVAL_GROUP_LOADED",
        "destinatario": "Familia Real",
        "invitados": [
            {"invitado_id": 7, "nombre": "Ana Real", "mesa_id": 4, "mesa_nombre": "Mesa 4", "llegada_confirmada": False},
            {"invitado_id": 9, "nombre": "Eva Real", "mesa_id": 4, "mesa_nombre": "Mesa 4", "llegada_confirmada": False},
            {"invitado_id": 8, "nombre": "Luis Real", "mesa_id": 4, "mesa_nombre": "Mesa 4", "llegada_confirmada": True},
        ],
    })
    root = build(page, db)
    guide = root.data["kiosk_qr_guide"]
    content_box = root.data["kiosk_content_box"]
    stage = root.data["kiosk_camera_stage"]
    assert (guide.width, guide.height, guide.alignment, guide.ignore_interactions) == (
        560,
        300,
        kiosk_view.ft.Alignment.CENTER,
        True,
    )
    assert guide.content is not None
    assert (guide.content.width, guide.content.height, guide.content.ignore_interactions) == (200, 200, True)
    assert guide.content.width < stage.width and guide.content.height < stage.height
    assert content_box.width == 680
    assert content_box.bgcolor == kiosk_view.KIOSK_IVORY
    assert (content_box.padding.left, content_box.padding.top, content_box.padding.right, content_box.padding.bottom) == (
        32,
        64,
        32,
        32,
    )
    assert isinstance(content_box.image, kiosk_view.ft.DecorationImage)
    assert content_box.image.src == "kiosk_panel_floral.png"
    assert content_box.image.fit == kiosk_view.ft.BoxFit.COVER
    assert guide.content.border.top.color == kiosk_view.KIOSK_WINE
    assert guide.visible

    welcome_text = [node.value for node in walk(root) if isinstance(node, kiosk_view.ft.Text)]
    assert "¡Bienvenidos!" in welcome_text

    root.data["kiosk_scanner"].on_qr_finalized("AB12")
    await drain(page)
    assert not guide.visible
    text_values = [node.value for node in walk(root) if isinstance(node, kiosk_view.ft.Text)]
    assert "Selecciona los invitados que te acompa\u00f1an y confirma su llegada" in text_values
    assert "Selecciona los integrantes pendientes" not in text_values
    cards = [
        node
        for node in walk(root)
        if isinstance(node, kiosk_view.ft.Container)
        and isinstance(getattr(node, "data", None), dict)
        and node.data.get("kiosk") == "guest_card"
    ]
    assert len(cards) == 3
    cards_by_id = {card.data["guest_id"]: card for card in cards}
    pending_card = cards_by_id[7]
    arrived_card = cards_by_id[8]
    assert pending_card.bgcolor == kiosk_view.KIOSK_IVORY
    assert pending_card.border.top.color == kiosk_view.KIOSK_BORDER
    assert isinstance(pending_card.content, kiosk_view.ft.Checkbox)
    assert pending_card.content.value is False
    assert pending_card.content.check_color == kiosk_view.ft.Colors.WHITE
    assert arrived_card.on_click is None
    assert arrived_card.ink is False
    assert arrived_card.content.disabled is True
    assert "Ya llegó" in arrived_card.content.label

    # Checkbox and its containing card target the same selected value, so a
    # bubbled tap cannot invert the guest twice.
    pending_card.content.on_change(SimpleNamespace(control=SimpleNamespace(value=True)))
    pending_card.on_click(SimpleNamespace())
    assert root.data["kiosk_state"].selected_guest_ids == {7}
    selected_card = next(
        node
        for node in walk(root)
        if isinstance(node, kiosk_view.ft.Container)
        and isinstance(getattr(node, "data", None), dict)
        and node.data.get("kiosk") == "guest_card"
        and node.data.get("guest_id") == 7
    )
    assert selected_card.bgcolor == kiosk_view.KIOSK_BLUSH
    assert selected_card.border.top.color == kiosk_view.KIOSK_WINE
    assert selected_card.content.value is True
    assert selected_card.content.label_style.color == kiosk_view.KIOSK_WINE
    selected_card.on_click(SimpleNamespace())
    assert root.data["kiosk_state"].selected_guest_ids == set()
    select_all = button_with_label(root, "Seleccionar a todos")
    confirm = button_with_label(root, "Confirmar llegada")
    assert confirm.style.bgcolor == kiosk_view.KIOSK_WINE
    assert confirm.style.color == kiosk_view.ft.Colors.WHITE
    assert select_all.style.color == kiosk_view.KIOSK_WINE
    assert select_all.style.side.color == kiosk_view.KIOSK_WINE
    select_all.on_click(SimpleNamespace())
    assert root.data["kiosk_state"].selected_guest_ids == {7, 9}
    assert 8 not in root.data["kiosk_state"].selected_guest_ids
    cards_after_select_all = {
        node.data["guest_id"]: node
        for node in walk(root)
        if isinstance(node, kiosk_view.ft.Container)
        and isinstance(getattr(node, "data", None), dict)
        and node.data.get("kiosk") == "guest_card"
    }
    assert cards_after_select_all[7].bgcolor == kiosk_view.KIOSK_BLUSH
    assert cards_after_select_all[9].bgcolor == kiosk_view.KIOSK_BLUSH
    assert cards_after_select_all[8].content.disabled is True


async def test_select_guests_five_guest_actions_wrap_without_touching_camera() -> None:
    page = FakePage(width=1440)
    long_name = "Invitado con un nombre particularmente largo para verificar el ancho disponible"
    invitados = [
        {
            "invitado_id": guest_id,
            "nombre": long_name if guest_id == 5 else f"Invitado {guest_id}",
            "mesa_id": 4,
            "mesa_nombre": "Mesa 4",
            "llegada_confirmada": False,
        }
        for guest_id in range(1, 6)
    ]
    root = build(page, FakeSupabase(group_payload={
        "ok": True,
        "codigo_resultado": "ARRIVAL_GROUP_LOADED",
        "destinatario": "Familia Cinco",
        "invitados": invitados,
    }))
    scanner = root.data["kiosk_scanner"]
    camera_host = scanner.host
    camera_stage = root.data["kiosk_camera_stage"]

    scanner.on_qr_finalized("AB12")
    await drain(page)

    checkboxes = [node for node in walk(root) if isinstance(node, kiosk_view.ft.Checkbox)]
    assert [checkbox.label for checkbox in checkboxes] == [
        f"Invitado {guest_id}" if guest_id != 5 else long_name
        for guest_id in range(1, 6)
    ]
    cards_column = next(node for node in walk(root) if getattr(node, "data", None) == {"kiosk": "guest_cards"})
    assert isinstance(cards_column, kiosk_view.ft.Column)
    assert cards_column.spacing == 8
    assert cards_column.width == root.data["kiosk_content_box"].width - 64
    assert cards_column.horizontal_alignment == kiosk_view.ft.CrossAxisAlignment.CENTER
    cards = [
        node
        for node in walk(root)
        if isinstance(node, kiosk_view.ft.Container)
        and isinstance(getattr(node, "data", None), dict)
        and node.data.get("kiosk") == "guest_card"
    ]
    assert len(cards) == 5
    assert all(card.width == round(cards_column.width * 2 / 3) for card in cards)
    assert all(card.width <= cards_column.width for card in cards)
    actions = next(node for node in walk(root) if getattr(node, "data", None) == {"kiosk": "guest_actions"})
    assert isinstance(actions, kiosk_view.ft.Row)
    assert actions.wrap is True
    assert actions.width == root.data["kiosk_content_box"].width - 64
    assert [action.content for action in actions.controls] == [
        "Seleccionar a todos",
        "Confirmar llegada",
        "Volver a escanear",
    ]
    assert camera_stage.controls[0] is camera_host
    assert scanner.host is camera_host


async def test_guest_cards_use_available_width_on_narrow_layout() -> None:
    page = FakePage(width=320)
    long_name = "Invitado con un nombre largo que conserva el ancho disponible en pantalla estrecha"
    root = build(page, FakeSupabase(group_payload={
        "ok": True,
        "codigo_resultado": "ARRIVAL_GROUP_LOADED",
        "destinatario": "Familia Estrecha",
        "invitados": [
            {
                "invitado_id": 71,
                "nombre": long_name,
                "mesa_id": 4,
                "mesa_nombre": "Mesa 4",
                "llegada_confirmada": False,
            }
        ],
    }))
    root.data["kiosk_scanner"].on_qr_finalized("AB12")
    await drain(page)

    cards_column = next(node for node in walk(root) if getattr(node, "data", None) == {"kiosk": "guest_cards"})
    card = next(
        node
        for node in walk(root)
        if isinstance(node, kiosk_view.ft.Container)
        and isinstance(getattr(node, "data", None), dict)
        and node.data.get("guest_id") == 71
    )
    assert cards_column.width == root.data["kiosk_content_box"].width - 64
    assert card.width == cards_column.width
    assert card.content.label == long_name


async def test_kiosk_background_is_event_scoped_and_non_blocking() -> None:
    page = FakePage()
    storage = FakeStorage(url="https://example.invalid/signed-background.jpg", blocking=True)
    root = build(page, FakeSupabase(storage=storage))
    scanner = root.data["kiosk_scanner"]
    foreground = root.content
    content_box = root.data["kiosk_content_box"]
    camera_host = scanner.host
    assert scanner.start_calls == 1
    assert root.image is None
    await asyncio.to_thread(storage.started.wait, 1)
    assert root.data["kiosk_state"].phase == KioskPhase.WELCOME_SCAN
    storage.release.set()
    await drain(page)
    assert storage.requests == [("kiosk-backgrounds", "2/9.jpg", 3600)]
    assert isinstance(root.image, kiosk_view.ft.DecorationImage)
    assert root.image.src == "https://example.invalid/signed-background.jpg"
    assert root.image.fit == kiosk_view.ft.BoxFit.CONTAIN
    assert root.image.alignment == kiosk_view.ft.Alignment.CENTER
    assert root.content is foreground
    assert root.data["kiosk_content_box"] is content_box
    assert scanner.host is camera_host
    assert page.update_calls == 1

    other_page = FakePage()
    other_storage = FakeStorage(url="https://example.invalid/event-10.jpg")
    other_context = contexto()
    other_event = {**other_context["evento_actual"], "evento_id": 10}
    other_context["evento_actual"] = other_event
    other_context["eventos_permitidos"] = [other_event]
    other_root = build(other_page, FakeSupabase(storage=other_storage), other_context)
    await drain(other_page)
    assert other_storage.requests == [("kiosk-backgrounds", "2/10.jpg", 3600)]
    assert other_root.image is not None
    assert other_root.image.src == "https://example.invalid/event-10.jpg"


async def test_kiosk_background_failure_keeps_fallback_and_scanner_running() -> None:
    page = FakePage()
    storage = FakeStorage(error=RuntimeError("object not found"))
    root = build(page, FakeSupabase(storage=storage))
    await drain(page)
    assert root.data["kiosk_scanner"].start_calls == 1
    assert root.image is None
    assert root.bgcolor == kiosk_view.ft.Colors.SURFACE
    assert root.content is not None
    assert root.data["kiosk_state"].phase == KioskPhase.WELCOME_SCAN


async def test_stale_kiosk_background_result_is_discarded_after_route_exit() -> None:
    page = FakePage()
    storage = FakeStorage(url="https://example.invalid/late.jpg", blocking=True)
    root = build(page, FakeSupabase(storage=storage))
    await asyncio.to_thread(storage.started.wait, 1)
    page.route = "/app/dashboard"
    assert page.on_route_change is not None
    page.on_route_change(SimpleNamespace(route="/app/dashboard"))
    storage.release.set()
    await drain(page)
    assert root.image is None
    assert root.content is not None
    assert root.data["kiosk_scanner"].stop_calls == 1
    assert page.scroll == kiosk_view.ft.ScrollMode.AUTO


async def test_kiosk_canvas_is_stable_between_welcome_and_guest_selection() -> None:
    page = FakePage()
    root = build(page, FakeSupabase())
    foreground = root.content
    exterior = (root.expand, root.width, root.height, root.bgcolor)

    assert page.scroll is None
    assert foreground.expand is True
    assert foreground.alignment == kiosk_view.ft.Alignment.CENTER

    root.data["kiosk_scanner"].on_qr_finalized("AB12")
    await drain(page)

    assert root.data["kiosk_state"].phase == KioskPhase.SELECT_GUESTS
    assert root.content is foreground
    assert (root.expand, root.width, root.height, root.bgcolor) == exterior


async def test_empty_selection_disables_confirmation_without_writing() -> None:
    page = FakePage()
    db = FakeSupabase()
    root = build(page, db)
    root.data["kiosk_scanner"].on_qr_finalized("AB12")
    await drain(page)
    confirm = button_with_label(root, "Confirmar llegada")
    assert confirm.disabled
    confirm.on_click(SimpleNamespace())
    assert root.data["kiosk_state"].phase == KioskPhase.SELECT_GUESTS
    assert not any(name == "evp_oper_confirmar_llegadas_invitacion" for name, _ in db.calls)


async def test_confirmation_batch_success_and_double_click_guard() -> None:
    page = FakePage()
    db = FakeSupabase(group_payload={
        "ok": True,
        "codigo_resultado": "ARRIVAL_GROUP_LOADED",
        "destinatario": "Familia Real",
        "invitados": [
            {"invitado_id": 7, "nombre": "Ana Real", "mesa_id": 4, "mesa_nombre": "Mesa 4", "llegada_confirmada": False},
            {"invitado_id": 9, "nombre": "Eva Real", "mesa_id": 4, "mesa_nombre": "Mesa 4", "llegada_confirmada": False},
            {"invitado_id": 8, "nombre": "Luis Real", "mesa_id": 4, "mesa_nombre": "Mesa 4", "llegada_confirmada": True},
        ],
    })
    root = build(page, db)
    state = root.data["kiosk_state"]
    root.data["kiosk_scanner"].on_qr_finalized("AB12")
    await drain(page)
    state.set_guest_selected(7, True)
    state.set_guest_selected(9, True)
    root.data["start_confirmation"]()
    root.data["start_confirmation"]()
    assert state.phase == KioskPhase.CONFIRMING
    await drain(page)
    writes = [params for name, params in db.calls if name == "evp_oper_confirmar_llegadas_invitacion"]
    assert writes == [{"p_cuenta_id": 2, "p_evento_id": 9, "p_invitacion_id": 31, "p_invitado_ids": [7, 9]}]
    assert state.phase == KioskPhase.SUCCESS
    assert state.confirmed_count == 2
    assert state.success_name == "Familia Real"
    assert state.selected_guest_ids == set()
    assert all(guest.llegada_confirmada for guest in state.guests)
    success_content = next(node for node in walk(root) if getattr(node, "data", None) == {"kiosk": "success_content"})
    assert (success_content.padding.left, success_content.padding.top, success_content.padding.right, success_content.padding.bottom) == (
        0,
        48,
        0,
        0,
    )
    text_values = [node.value for node in walk(root) if isinstance(node, kiosk_view.ft.Text)]
    assert "Familia Real:" in text_values
    assert "¡Gracias por acompañarnos!" in text_values
    assert "Esperamos que disfruten lo que hemos preparado para ustedes." in text_values
    assert "¡Bienvenidos!" in text_values


async def test_confirmation_rejects_arrived_guest_and_backend_error_without_retry() -> None:
    page = FakePage()
    db = FakeSupabase(confirmation_payload={"ok": False, "codigo_resultado": "ARRIVAL_ALREADY_CONFIRMED"})
    root = build(page, db)
    state = root.data["kiosk_state"]
    root.data["kiosk_scanner"].on_qr_finalized("AB12")
    await drain(page)
    state.set_guest_selected(8, True)
    assert state.selected_guest_ids == set()
    state.set_guest_selected(7, True)
    root.data["start_confirmation"]()
    await drain(page)
    writes = [name for name, _ in db.calls if name == "evp_oper_confirmar_llegadas_invitacion"]
    assert writes == ["evp_oper_confirmar_llegadas_invitacion"]
    assert state.phase == KioskPhase.SELECT_GUESTS
    assert state.selected_guest_ids == set()
    assert "No se confirmaron" in (state.error_message or "")
    assert state.guests[1].llegada_confirmada


async def test_confirmation_connection_error_does_not_retry() -> None:
    page = FakePage()
    db = FakeSupabase(confirmation_error=ConnectionError("timeout"))
    root = build(page, db)
    state = root.data["kiosk_state"]
    root.data["kiosk_scanner"].on_qr_finalized("AB12")
    await drain(page)
    state.set_guest_selected(7, True)
    root.data["start_confirmation"]()
    await drain(page)
    assert state.phase == KioskPhase.ERROR
    assert "No fue posible confirmar" in (state.error_message or "")
    assert len([name for name, _ in db.calls if name == "evp_oper_confirmar_llegadas_invitacion"]) == 1


async def test_confirmation_stale_result_after_route_exit_does_not_mutate_kiosk() -> None:
    page = FakePage()
    db = BlockingConfirmationSupabase()
    root = build(page, db)
    state = root.data["kiosk_state"]
    root.data["kiosk_scanner"].on_qr_finalized("AB12")
    await drain(page)
    state.set_guest_selected(7, True)
    root.data["start_confirmation"]()
    await asyncio.to_thread(db.started.wait, 1)
    page.route = "/app/dashboard"
    assert page.on_route_change is not None
    page.on_route_change(SimpleNamespace(route="/app/dashboard"))
    db.release.set()
    await drain(page)
    assert state.phase == KioskPhase.CONFIRMING
    assert state.confirmed_count == 0
    assert root.data["kiosk_scanner"].stop_calls == 1


async def test_confirmation_event_change_discards_late_result() -> None:
    page = FakePage()
    db = BlockingConfirmationSupabase()
    user_context = contexto()
    root = build(page, db, user_context)
    state = root.data["kiosk_state"]
    root.data["kiosk_scanner"].on_qr_finalized("AB12")
    await drain(page)
    state.set_guest_selected(7, True)
    root.data["start_confirmation"]()
    await asyncio.to_thread(db.started.wait, 1)
    changed_event = {**user_context["evento_actual"], "evento_id": 10}
    user_context["evento_actual"] = changed_event
    user_context["eventos_permitidos"] = [changed_event]
    db.release.set()
    await drain(page)
    assert state.phase == KioskPhase.CONFIRMING
    assert state.confirmed_count == 0
    root.data["cancel_confirmation"]()


async def test_consulta_and_invalid_phase_do_not_start_confirmation() -> None:
    for updates in (
        {"puede_registrar_llegadas": False, "evento_actual": {**contexto()["evento_actual"], "rol": "Consulta"}},
        {"evento_actual": {**contexto()["evento_actual"], "fase_evento": "Post_evento"}},
    ):
        user_context = contexto()
        user_context.update(updates)
        user_context["eventos_permitidos"] = [user_context["evento_actual"]]
        page = FakePage()
        db = FakeSupabase()
        root = build(page, db, user_context)
        state = root.data["kiosk_state"]
        root.data["kiosk_scanner"].on_qr_finalized("AB12")
        await drain(page)
        state.set_guest_selected(7, True)
        assert button_with_label(root, "Confirmar llegada").disabled
        root.data["start_confirmation"]()
        assert state.phase == KioskPhase.SELECT_GUESTS
        assert not any(name == "evp_oper_confirmar_llegadas_invitacion" for name, _ in db.calls)


async def test_success_can_reset_and_resolve_a_new_qr() -> None:
    page = FakePage()
    db = FakeSupabase()
    root = build(page, db)
    state = root.data["kiosk_state"]
    scanner = root.data["kiosk_scanner"]
    scanner.on_qr_finalized("A001")
    await drain(page)
    state.set_guest_selected(7, True)
    root.data["start_confirmation"]()
    await drain(page)
    assert state.phase == KioskPhase.SUCCESS
    button_with_label(root, "Volver a escanear").on_click(SimpleNamespace())
    assert state.phase == KioskPhase.WELCOME_SCAN
    assert state.confirmed_count == 0 and state.guests == [] and state.selected_guest_ids == set()
    db.qr_payload = {"ok": True, "codigo_resultado": "QR_RESOLVED", "cuenta_id": 2, "evento_id": 9, "invitacion_id": 32}
    db.group_payload = {"ok": True, "codigo_resultado": "ARRIVAL_GROUP_LOADED", "destinatario": "Familia Nueva", "invitados": [{"invitado_id": 10, "nombre": "Nora", "mesa_id": 5, "mesa_nombre": "Mesa 5", "llegada_confirmada": False}]}
    scanner.on_qr_finalized("B002")
    await drain(page)
    assert state.phase == KioskPhase.SELECT_GUESTS
    assert state.invitation_id == 32 and state.destinatario == "Familia Nueva" and state.selected_guest_ids == set()


def event_ten_context() -> dict[str, Any]:
    user_context = contexto()
    event = {**user_context["evento_actual"], "evento_id": 10}
    user_context["evento_actual"] = event
    user_context["eventos_permitidos"] = [event]
    return user_context


async def reach_success_for_event_ten(page: FakePage, database: FakeSupabase, user_context: dict[str, Any]) -> Any:
    root = build(page, database, user_context)
    root.data["kiosk_scanner"].on_qr_finalized("MAP10")
    await drain(page)
    state = root.data["kiosk_state"]
    state.set_guest_selected(state.guests[0].guest_id, True)
    root.data["start_confirmation"]()
    await drain(page)
    assert state.phase == KioskPhase.SUCCESS
    return root


async def test_success_loads_route_map_without_changing_success_copy() -> None:
    database = FakeSupabase(
        qr_payload={"ok": True, "codigo_resultado": "QR_RESOLVED", "cuenta_id": 2, "evento_id": 10, "invitacion_id": 31},
        group_payload={
            "ok": True,
            "codigo_resultado": "ARRIVAL_GROUP_LOADED",
            "destinatario": "Familia Mapa",
            "invitados": [{"invitado_id": 7, "nombre": "Ana", "mesa_id": 4, "mesa_nombre": "Unidad", "llegada_confirmada": False}],
        },
    )
    requested: list[tuple[str, str]] = []
    original = kiosk_view.resolve_kiosk_route_map_url
    original_preview = kiosk_view.load_kiosk_route_map_data_url
    kiosk_view.resolve_kiosk_route_map_url = lambda _client, bucket, path: (
        requested.append((bucket, path)) or "https://example.invalid/signed-floorplan.jpg"
    )
    kiosk_view.load_kiosk_route_map_data_url = lambda _url: "data:image/jpeg;base64,ZmFrZQ=="
    try:
        page = FakePage()
        root = await reach_success_for_event_ten(page, database, event_ten_context())
    finally:
        kiosk_view.resolve_kiosk_route_map_url = original
        kiosk_view.load_kiosk_route_map_data_url = original_preview
    state = root.data["kiosk_state"]
    assert state.route_result is not None and state.route_result.mesa_id == 4
    assert state.route_result.node_ids[0] == "KIOSK" and state.route_result.node_ids[-1] == "MESA_4"
    assert state.map_signed_url == "https://example.invalid/signed-floorplan.jpg"
    assert requested == [("event-maps", "2/10/floorplan.jpg")]
    thumbnail = next(
        node for node in walk(root) if getattr(node, "data", None) == {"kiosk": "route_map_thumbnail", "width": 340}
    )
    assert thumbnail.on_click is not None
    instruction = next(node for node in walk(root) if getattr(node, "data", None) == {"kiosk": "route_map_instruction"})
    assert "".join(span.text or "" for span in instruction.spans) == "Para conocer cómo llegar a su mesa, seleccione el mapa"
    assert instruction.spans[0].style.weight == kiosk_view.ft.FontWeight.BOLD
    assert instruction.spans[1].style is None
    assert "Esperamos que disfrutes lo que hemos preparado para ti." in [
        node.value for node in walk(root) if isinstance(node, kiosk_view.ft.Text)
    ]
    thumbnail.on_click(SimpleNamespace())
    assert len(page.overlay) == 1
    viewer = page.overlay[0]
    assert getattr(viewer, "data", None) == {"kiosk": "route_map_viewer", "zoom": 1.0}
    assert state.phase == KioskPhase.SUCCESS and root.data["kiosk_scanner"].restart_calls == 0
    close = next(node for node in walk(viewer) if getattr(node, "data", None) == {"kiosk": "route_map_viewer_close"})
    close.on_click(SimpleNamespace())
    assert page.overlay == [] and state.phase == KioskPhase.SUCCESS
    await drain(page)


async def test_map_prefetch_starts_in_selection_and_reuses_event_asset() -> None:
    database = FakeSupabase(
        qr_payload={"ok": True, "codigo_resultado": "QR_RESOLVED", "cuenta_id": 2, "evento_id": 10, "invitacion_id": 31},
        group_payload={
            "ok": True,
            "codigo_resultado": "ARRIVAL_GROUP_LOADED",
            "destinatario": "Familia Mapa",
            "invitados": [{"invitado_id": 7, "nombre": "Ana", "mesa_id": 4, "mesa_nombre": "Unidad", "llegada_confirmada": False}],
        },
    )
    signed_calls: list[tuple[str, str]] = []
    image_calls: list[str] = []
    route_calls: list[int] = []
    original_url = kiosk_view.resolve_kiosk_route_map_url
    original_preview = kiosk_view.load_kiosk_route_map_data_url
    original_route = kiosk_view.calcular_ruta
    kiosk_view.resolve_kiosk_route_map_url = lambda _client, bucket, path: signed_calls.append((bucket, path)) or "https://example.invalid/signed-floorplan.jpg"
    kiosk_view.load_kiosk_route_map_data_url = lambda url: image_calls.append(url) or "data:image/jpeg;base64,ZmFrZQ=="
    kiosk_view.calcular_ruta = lambda **kwargs: route_calls.append(kwargs["mesa_id"]) or original_route(**kwargs)
    try:
        page = FakePage()
        root = build(page, database, event_ten_context())
        root.data["kiosk_scanner"].on_qr_finalized("MAP10")
        await drain(page)
        state = root.data["kiosk_state"]
        assert state.phase == KioskPhase.SELECT_GUESTS and state.map_preview_ready
        assert route_calls == [4] and signed_calls == [("event-maps", "2/10/floorplan.jpg")] and len(image_calls) == 1
        state.set_guest_selected(7, True)
        root.data["start_confirmation"]()
        await drain(page)
        assert state.phase == KioskPhase.SUCCESS and route_calls == [4]
        root.data["reset_kiosk"]()
        root.data["kiosk_scanner"].on_qr_finalized("MAP10-SECOND")
        await drain(page)
        assert state.phase == KioskPhase.SELECT_GUESTS and state.map_preview_ready
        assert route_calls == [4, 4]
        assert signed_calls == [("event-maps", "2/10/floorplan.jpg")] and len(image_calls) == 1
    finally:
        kiosk_view.resolve_kiosk_route_map_url = original_url
        kiosk_view.load_kiosk_route_map_data_url = original_preview
        kiosk_view.calcular_ruta = original_route


async def test_route_map_viewer_timeout_zoom_and_reset_are_ui_only() -> None:
    original = kiosk_view.resolve_kiosk_route_map_url
    original_preview = kiosk_view.load_kiosk_route_map_data_url
    kiosk_view.resolve_kiosk_route_map_url = lambda *_args: "https://example.invalid/signed-floorplan.jpg"
    kiosk_view.load_kiosk_route_map_data_url = lambda _url: "data:image/jpeg;base64,ZmFrZQ=="
    try:
        page = FakePage()
        root = await reach_success_for_event_ten(
            page,
            FakeSupabase(qr_payload={"ok": True, "codigo_resultado": "QR_RESOLVED", "cuenta_id": 2, "evento_id": 10, "invitacion_id": 31}),
            event_ten_context(),
        )
    finally:
        kiosk_view.resolve_kiosk_route_map_url = original
        kiosk_view.load_kiosk_route_map_data_url = original_preview
    root.data["open_route_map_viewer"]()
    root.data["set_route_map_viewer_zoom"](2.0)
    assert page.overlay[0].data == {"kiosk": "route_map_viewer", "zoom": 2.0}
    root.data["set_route_map_viewer_zoom"](99.0)
    assert page.overlay[0].data == {"kiosk": "route_map_viewer", "zoom": 2.5}
    root.data["set_route_map_viewer_zoom"](1.0)
    assert page.overlay[0].data == {"kiosk": "route_map_viewer", "zoom": 1.0}
    root.data["reset_kiosk"]()
    assert page.overlay == [] and root.data["kiosk_state"].phase == KioskPhase.WELCOME_SCAN
    await drain(page)

    original_sleep = kiosk_view.asyncio.sleep
    original_url = kiosk_view.resolve_kiosk_route_map_url
    original_preview = kiosk_view.load_kiosk_route_map_data_url

    async def immediate_sleep(_seconds: float) -> None:
        return None

    kiosk_view.asyncio.sleep = immediate_sleep
    kiosk_view.resolve_kiosk_route_map_url = lambda *_args: "https://example.invalid/signed-floorplan.jpg"
    kiosk_view.load_kiosk_route_map_data_url = lambda _url: "data:image/jpeg;base64,ZmFrZQ=="
    try:
        page = FakePage()
        root = await reach_success_for_event_ten(
            page,
            FakeSupabase(qr_payload={"ok": True, "codigo_resultado": "QR_RESOLVED", "cuenta_id": 2, "evento_id": 10, "invitacion_id": 31}),
            event_ten_context(),
        )
        root.data["open_route_map_viewer"]()
        await drain(page)
        assert page.overlay == [] and root.data["kiosk_state"].phase == KioskPhase.SUCCESS
    finally:
        kiosk_view.asyncio.sleep = original_sleep
        kiosk_view.resolve_kiosk_route_map_url = original_url
        kiosk_view.load_kiosk_route_map_data_url = original_preview


async def test_reset_discards_map_preview_that_finishes_late() -> None:
    original_url = kiosk_view.resolve_kiosk_route_map_url
    original_preview = kiosk_view.load_kiosk_route_map_data_url
    started = threading.Event()
    release = threading.Event()

    def blocking_preview(_url: str) -> str:
        started.set()
        assert release.wait(1)
        return "data:image/jpeg;base64,ZmFrZQ=="

    kiosk_view.resolve_kiosk_route_map_url = lambda *_args: "https://example.invalid/signed-floorplan.jpg"
    kiosk_view.load_kiosk_route_map_data_url = blocking_preview
    try:
        page = FakePage()
        root = build(
            page,
            FakeSupabase(qr_payload={"ok": True, "codigo_resultado": "QR_RESOLVED", "cuenta_id": 2, "evento_id": 10, "invitacion_id": 31}),
            event_ten_context(),
        )
        state = root.data["kiosk_state"]
        root.data["kiosk_scanner"].on_qr_finalized("MAP10")
        assert await asyncio.to_thread(started.wait, 1)
        root.data["reset_kiosk"]()
        release.set()
        await drain(page)
        assert state.phase == KioskPhase.WELCOME_SCAN
        assert not state.map_preview_ready and state.map_preview_src is None and state.route_result is None
    finally:
        release.set()
        kiosk_view.resolve_kiosk_route_map_url = original_url
        kiosk_view.load_kiosk_route_map_data_url = original_preview


async def test_success_map_failures_and_missing_mesa_keep_welcome_visible() -> None:
    original_route = kiosk_view.calcular_ruta
    original_url = kiosk_view.resolve_kiosk_route_map_url

    def unavailable_route(code: str) -> Any:
        return lambda **_kwargs: kiosk_view.ResultadoRuta(
            ok=False, codigo=code, mensaje="No disponible", account_id=2, event_id=10, mesa_id=4
        )

    try:
        for code in ("MAP_CONFIG_NOT_FOUND", "MAP_TABLE_NOT_FOUND", "MAP_ROUTE_NOT_FOUND"):
            kiosk_view.calcular_ruta = unavailable_route(code)
            root = await reach_success_for_event_ten(
                FakePage(),
                FakeSupabase(
                    qr_payload={"ok": True, "codigo_resultado": "QR_RESOLVED", "cuenta_id": 2, "evento_id": 10, "invitacion_id": 31}
                ),
                event_ten_context(),
            )
            state = root.data["kiosk_state"]
            assert state.route_result is None and state.map_signed_url is None and state.phase == KioskPhase.SUCCESS

        kiosk_view.calcular_ruta = original_route
        kiosk_view.resolve_kiosk_route_map_url = lambda *_args: None
        root = await reach_success_for_event_ten(
            FakePage(),
            FakeSupabase(qr_payload={"ok": True, "codigo_resultado": "QR_RESOLVED", "cuenta_id": 2, "evento_id": 10, "invitacion_id": 31}),
            event_ten_context(),
        )
        state = root.data["kiosk_state"]
        assert state.route_result is None and state.map_signed_url is None and state.phase == KioskPhase.SUCCESS

        calls: list[object] = []
        kiosk_view.calcular_ruta = lambda **_kwargs: calls.append(True) or original_route(**_kwargs)
        missing_mesa = FakeSupabase(
            qr_payload={"ok": True, "codigo_resultado": "QR_RESOLVED", "cuenta_id": 2, "evento_id": 10, "invitacion_id": 31},
            group_payload={
                "ok": True,
                "codigo_resultado": "ARRIVAL_GROUP_LOADED",
                "destinatario": "Sin mesa",
                "invitados": [{"invitado_id": 7, "nombre": "Ana", "mesa_id": None, "mesa_nombre": None, "llegada_confirmada": False}],
            },
        )
        root = await reach_success_for_event_ten(FakePage(), missing_mesa, event_ten_context())
        assert not calls
        assert root.data["kiosk_state"].route_result is None
    finally:
        kiosk_view.calcular_ruta = original_route
        kiosk_view.resolve_kiosk_route_map_url = original_url


async def test_success_map_is_cleared_before_a_new_invitation() -> None:
    original = kiosk_view.resolve_kiosk_route_map_url
    original_preview = kiosk_view.load_kiosk_route_map_data_url
    kiosk_view.resolve_kiosk_route_map_url = lambda *_args: "https://example.invalid/signed-floorplan.jpg"
    kiosk_view.load_kiosk_route_map_data_url = lambda _url: "data:image/jpeg;base64,ZmFrZQ=="
    try:
        root = await reach_success_for_event_ten(
            FakePage(),
            FakeSupabase(qr_payload={"ok": True, "codigo_resultado": "QR_RESOLVED", "cuenta_id": 2, "evento_id": 10, "invitacion_id": 31}),
            event_ten_context(),
        )
    finally:
        kiosk_view.resolve_kiosk_route_map_url = original
        kiosk_view.load_kiosk_route_map_data_url = original_preview
    state = root.data["kiosk_state"]
    assert state.route_result is not None and state.map_signed_url is not None and state.map_preview_ready
    root.data["reset_kiosk"]()
    assert state.phase == KioskPhase.WELCOME_SCAN
    assert state.route_result is None and state.map_signed_url is None and not state.map_loading and not state.map_preview_ready


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
    await test_select_guests_visual_contract_and_select_all_pending_only()
    await test_select_guests_five_guest_actions_wrap_without_touching_camera()
    await test_guest_cards_use_available_width_on_narrow_layout()
    await test_kiosk_background_is_event_scoped_and_non_blocking()
    await test_kiosk_background_failure_keeps_fallback_and_scanner_running()
    await test_stale_kiosk_background_result_is_discarded_after_route_exit()
    await test_kiosk_canvas_is_stable_between_welcome_and_guest_selection()
    await test_empty_selection_disables_confirmation_without_writing()
    await test_confirmation_batch_success_and_double_click_guard()
    await test_confirmation_rejects_arrived_guest_and_backend_error_without_retry()
    await test_confirmation_connection_error_does_not_retry()
    await test_confirmation_stale_result_after_route_exit_does_not_mutate_kiosk()
    await test_confirmation_event_change_discards_late_result()
    await test_consulta_and_invalid_phase_do_not_start_confirmation()
    await test_success_can_reset_and_resolve_a_new_qr()
    await test_success_loads_route_map_without_changing_success_copy()
    await test_map_prefetch_starts_in_selection_and_reuses_event_asset()
    await test_route_map_viewer_timeout_zoom_and_reset_are_ui_only()
    await test_reset_discards_map_preview_that_finishes_late()
    await test_success_map_failures_and_missing_mesa_keep_welcome_visible()
    await test_success_map_is_cleared_before_a_new_invitation()
    await test_route_exit_cancels_resolution_before_scanner_shutdown()
    await test_reconnect_is_limited_to_welcome_scan()


def main() -> None:
    test_route()
    test_success_greeting_names_follow_updated_group_state()
    asyncio.run(main_async())
    print("Kiosk view tests passed.")


if __name__ == "__main__":
    main()

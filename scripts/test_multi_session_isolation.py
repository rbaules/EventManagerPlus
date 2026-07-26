from __future__ import annotations

import inspect
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app
import app_publishable_key_v4 as oauth_prototype
import db
import services.auth_service as auth_service
import services.usuario_service as usuario_service


class FakeResponse:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class FakeAuth:
    def __init__(self, identity: str) -> None:
        self.identity = identity
        self.token = f"token-{identity}"
        self.sign_out_calls = 0

    def sign_out(self, options: dict[str, str] | None = None) -> None:
        self.sign_out_calls += 1
        assert options == {"scope": "local"}
        self.identity = ""
        self.token = ""


class FakeQuery:
    def __init__(self, client: "FakeClient") -> None:
        self.client = client
        self.filters: list[tuple[str, Any]] = []

    def select(self, columns: str) -> "FakeQuery":
        self.client.operations.append(("select", columns))
        return self

    def eq(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((column, value))
        self.client.operations.append(("eq", column, value))
        return self

    def ilike(self, column: str, value: Any) -> "FakeQuery":
        self.filters.append((column, value))
        self.client.operations.append(("ilike", column, value))
        return self

    def limit(self, count: int) -> "FakeQuery":
        self.client.operations.append(("limit", count))
        return self

    def execute(self) -> FakeResponse:
        self.client.operations.append(("execute", tuple(self.filters)))
        return FakeResponse(
            [
                {
                    "usr_usuario_id": f"user-{self.client.name}",
                    "usr_usuario_auth_uuid": f"auth-{self.client.name}",
                    "usr_nombre_usuario": f"Usuario {self.client.name}",
                    "usr_email": f"{self.client.name.lower()}@example.com",
                    "usr_estado": "Activo",
                }
            ]
        )


class FakeClient:
    def __init__(self, name: str) -> None:
        self.name = name
        self.auth = FakeAuth(name)
        self.operations: list[tuple[Any, ...]] = []

    def table(self, name: str) -> FakeQuery:
        self.operations.append(("table", name))
        return FakeQuery(self)


class DummyPage:
    def __init__(self) -> None:
        self.title = ""
        self.window = SimpleNamespace(width=None, height=None)
        self.scroll = None
        self.adaptive = False


def test_main_creates_exactly_one_client_per_page() -> tuple[FakeClient, FakeClient]:
    clients = [FakeClient("A"), FakeClient("B")]
    created: list[FakeClient] = []
    injected: list[tuple[DummyPage, FakeClient]] = []
    original_factory = app.create_supabase_client
    original_builder = app.build_login_view

    def factory() -> FakeClient:
        client = clients[len(created)]
        created.append(client)
        return client

    try:
        app.create_supabase_client = factory
        app.build_login_view = lambda page, client, **_kwargs: injected.append(
            (page, client)
        )
        page_a = DummyPage()
        page_b = DummyPage()
        app.main(page_a)
        app.main(page_b)
    finally:
        app.create_supabase_client = original_factory
        app.build_login_view = original_builder

    assert created == clients
    assert created[0] is not created[1]
    assert injected == [(page_a, clients[0]), (page_b, clients[1])]
    return clients[0], clients[1]


def test_auth_identity_token_and_logout_are_isolated(
    client_a: FakeClient,
    client_b: FakeClient,
) -> None:
    assert client_a.auth.identity == "A"
    assert client_b.auth.identity == "B"

    client_a.auth.identity = "A2"
    client_a.auth.token = "token-A2"
    assert client_b.auth.identity == "B"
    assert client_b.auth.token == "token-B"

    auth_service.sign_out_local_session(client_a)
    assert client_a.auth.sign_out_calls == 1
    assert client_b.auth.sign_out_calls == 0
    assert client_b.auth.identity == "B"
    assert client_b.auth.token == "token-B"


def test_context_and_service_clients_are_isolated(
    client_a: FakeClient,
    client_b: FakeClient,
) -> None:
    context_a = {
        "cuenta_actual": {"cuenta_id": 1},
        "evento_actual": {"cuenta_id": 1, "evento_id": 10},
    }
    context_b = {
        "cuenta_actual": {"cuenta_id": 2},
        "evento_actual": {"cuenta_id": 2, "evento_id": 20},
    }
    context_a["cuenta_actual"]["cuenta_id"] = 99
    context_a["evento_actual"]["evento_id"] = 999
    assert context_b["cuenta_actual"]["cuenta_id"] == 2
    assert context_b["evento_actual"]["evento_id"] == 20

    user_a = usuario_service.buscar_usuario_eventplus_por_auth_uuid(client_a, "auth-A")
    assert user_a and user_a["usr_usuario_id"] == "user-A"
    assert client_a.operations
    assert client_b.operations == []

    operations_a = list(client_a.operations)
    user_b = usuario_service.buscar_usuario_eventplus_por_auth_uuid(client_b, "auth-B")
    assert user_b and user_b["usr_usuario_id"] == "user-B"
    assert client_a.operations == operations_a
    assert client_b.operations


def test_factory_and_modules_do_not_hold_authenticated_clients() -> None:
    original_create_client = db.create_client
    generated: list[FakeClient] = []

    def fake_create_client(_url: str, _key: str) -> FakeClient:
        client = FakeClient(str(len(generated) + 1))
        generated.append(client)
        return client

    try:
        db.create_client = fake_create_client
        first = db.create_supabase_client()
        second = db.create_supabase_client()
        compatible = db.get_supabase_client()
    finally:
        db.create_client = original_create_client

    assert first is not second
    assert second is not compatible
    assert len(generated) == 3
    assert not hasattr(db.create_supabase_client, "cache_info")
    assert "lru_cache" not in inspect.getsource(db)

    for module in (db, auth_service, usuario_service, oauth_prototype):
        for name, value in vars(module).items():
            assert not isinstance(value, FakeClient), (
                f"{module.__name__}.{name} conserva un cliente autenticado global"
            )


def main() -> int:
    client_a, client_b = test_main_creates_exactly_one_client_per_page()
    test_auth_identity_token_and_logout_are_isolated(client_a, client_b)
    clean_a = FakeClient("A")
    clean_b = FakeClient("B")
    test_context_and_service_clients_are_isolated(clean_a, clean_b)
    test_factory_and_modules_do_not_hold_authenticated_clients()
    print("OK - Supabase clients, auth state, contexts, services, and logout are isolated per Page.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

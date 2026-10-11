from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.kiosk_admin_service import (
    KIOSK_ADMIN_ALLOWED,
    KIOSK_ADMIN_CONFIG_DENIED,
    KIOSK_ADMIN_DENIED,
    KIOSK_ADMIN_PIN_CONFIGURED,
    configurar_pin_administrativo,
    validar_pin_administrativo,
)


class RpcCall:
    def __init__(self, client: "FakeSupabase") -> None:
        self.client = client

    def execute(self) -> Any:
        if self.client.error:
            raise RuntimeError("network unavailable")
        return {"data": self.client.response}


class FakeSupabase:
    def __init__(self, response: dict[str, Any] | None = None, *, error: bool = False) -> None:
        self.response = response or {}
        self.error = error
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def rpc(self, name: str, params: dict[str, Any]) -> RpcCall:
        self.calls.append((name, params))
        return RpcCall(self)


def contexto() -> dict[str, Any]:
    return {"cuenta_actual": {"cuenta_id": 2}, "evento_actual": {"cuenta_id": 2, "evento_id": 10}}


def test_validate_uses_only_authoritative_context_ids() -> None:
    client = FakeSupabase({"ok": True, "code": KIOSK_ADMIN_ALLOWED})
    result = validar_pin_administrativo(contexto(), "123456", client)
    assert result.ok and result.code == KIOSK_ADMIN_ALLOWED
    assert client.calls == [("evp_kpa_validar_pin_administrativo", {"p_cuenta_id": 2, "p_evento_id": 10, "p_pin": "123456"})]


def test_validate_all_failures_are_uniform_and_pin_is_not_logged() -> None:
    for client in (FakeSupabase({"ok": False, "code": "OTHER"}), FakeSupabase(error=True)):
        result = validar_pin_administrativo(contexto(), "000000", client)
        assert not result.ok and result.code == KIOSK_ADMIN_DENIED
    client = FakeSupabase()
    result = validar_pin_administrativo({"evento_actual": {"cuenta_id": 2, "evento_id": 10}, "cuenta_actual": {"cuenta_id": 9}}, "000000", client)
    assert not result.ok and result.code == KIOSK_ADMIN_DENIED and not client.calls


def test_configure_requires_server_success_and_keeps_context_bound() -> None:
    client = FakeSupabase({"ok": True, "code": KIOSK_ADMIN_PIN_CONFIGURED})
    result = configurar_pin_administrativo(contexto(), "654321", client)
    assert result.ok and result.code == KIOSK_ADMIN_PIN_CONFIGURED
    assert client.calls[0][0] == "evp_kpa_configurar_pin_administrativo"
    assert client.calls[0][1]["p_cuenta_id"] == 2 and client.calls[0][1]["p_evento_id"] == 10
    denied = configurar_pin_administrativo(None, "654321", client)
    assert not denied.ok and denied.code == KIOSK_ADMIN_CONFIG_DENIED


def main() -> None:
    test_validate_uses_only_authoritative_context_ids()
    test_validate_all_failures_are_uniform_and_pin_is_not_logged()
    test_configure_requires_server_success_and_keeps_context_bound()
    print("Kiosk admin PIN service tests passed.")


if __name__ == "__main__":
    main()

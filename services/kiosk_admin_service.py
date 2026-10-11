"""Secure client contract for the future Kiosk administrative PIN flow.

This module intentionally contains no UI state, logging of PINs, or role
decisions. PostgreSQL remains the authorization authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.response_utils import extract_data, to_dict


KIOSK_ADMIN_ALLOWED = "KIOSK_ADMIN_ALLOWED"
KIOSK_ADMIN_DENIED = "KIOSK_ADMIN_DENIED"
KIOSK_ADMIN_PIN_CONFIGURED = "KIOSK_ADMIN_PIN_CONFIGURED"
KIOSK_ADMIN_CONFIG_DENIED = "KIOSK_ADMIN_CONFIG_DENIED"


@dataclass(frozen=True)
class ResultadoPinAdministrativo:
    ok: bool
    code: str


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def _context_key(contexto: dict[str, Any] | None) -> tuple[int, int] | None:
    if not isinstance(contexto, dict):
        return None
    event = contexto.get("evento_actual")
    if not isinstance(event, dict):
        return None
    account_id = _positive_int(event.get("cuenta_id"))
    event_id = _positive_int(event.get("evento_id"))
    if account_id is None or event_id is None:
        return None
    current_account = contexto.get("cuenta_actual")
    if isinstance(current_account, dict):
        context_account_id = _positive_int(current_account.get("cuenta_id"))
        if context_account_id is not None and context_account_id != account_id:
            return None
    return account_id, event_id


def _payload(response: Any) -> dict[str, Any]:
    data = extract_data(response)
    return to_dict(data[0] if data else None) or {}


def _call(supabase: Any, rpc_name: str, account_id: int, event_id: int, pin: str) -> dict[str, Any] | None:
    try:
        response = supabase.rpc(rpc_name, {
            "p_cuenta_id": account_id,
            "p_evento_id": event_id,
            "p_pin": pin,
        }).execute()
    except Exception:
        return None
    return _payload(response)


def validar_pin_administrativo(
    contexto: dict[str, Any] | None,
    pin: str,
    supabase: Any,
) -> ResultadoPinAdministrativo:
    """Validate a six-digit PIN against the active, authoritative context."""
    key = _context_key(contexto)
    if key is None or not isinstance(pin, str):
        return ResultadoPinAdministrativo(False, KIOSK_ADMIN_DENIED)
    payload = _call(supabase, "evp_kpa_validar_pin_administrativo", key[0], key[1], pin)
    if payload and payload.get("ok") is True and payload.get("code") == KIOSK_ADMIN_ALLOWED:
        return ResultadoPinAdministrativo(True, KIOSK_ADMIN_ALLOWED)
    return ResultadoPinAdministrativo(False, KIOSK_ADMIN_DENIED)


def configurar_pin_administrativo(
    contexto: dict[str, Any] | None,
    pin: str,
    supabase: Any,
) -> ResultadoPinAdministrativo:
    """Configure or rotate a PIN; server-side Master/Admin authorization applies."""
    key = _context_key(contexto)
    if key is None or not isinstance(pin, str):
        return ResultadoPinAdministrativo(False, KIOSK_ADMIN_CONFIG_DENIED)
    payload = _call(supabase, "evp_kpa_configurar_pin_administrativo", key[0], key[1], pin)
    if payload and payload.get("ok") is True and payload.get("code") == KIOSK_ADMIN_PIN_CONFIGURED:
        return ResultadoPinAdministrativo(True, KIOSK_ADMIN_PIN_CONFIGURED)
    return ResultadoPinAdministrativo(False, KIOSK_ADMIN_CONFIG_DENIED)

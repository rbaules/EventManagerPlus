from __future__ import annotations

import json
from typing import Any


def safe_get(obj: Any, key: str, default: Any = None) -> Any:
    """
    Lee una llave/atributo de forma segura.
    Evita errores como: AttributeError: 'str' object has no attribute 'get'.
    """
    if obj is None:
        return default

    if isinstance(obj, dict):
        return obj.get(key, default)

    if isinstance(obj, str):
        try:
            parsed = json.loads(obj)
            if isinstance(parsed, dict):
                return parsed.get(key, default)
        except Exception:
            return default

    return getattr(obj, key, default)


def to_dict(value: Any) -> dict[str, Any] | None:
    """
    Convierte valores devueltos por Supabase a dict cuando sea posible.
    """
    if value is None:
        return None

    if isinstance(value, dict):
        return value

    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
            return {"_raw": value, "_parsed_type": type(parsed).__name__}
        except Exception:
            return {"_raw": value, "_type": "str"}

    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
            if isinstance(dumped, dict):
                return dumped
        except Exception:
            pass

    if hasattr(value, "__dict__"):
        try:
            return dict(value.__dict__)
        except Exception:
            pass

    return {"_raw": str(value), "_type": type(value).__name__}


def extract_data(response: Any) -> list[Any]:
    """
    Extrae response.data de forma robusta.
    """
    data = safe_get(response, "data", [])

    if data is None:
        return []

    if isinstance(data, list):
        return data

    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                return [parsed]
            return [data]
        except Exception:
            return [data]

    return [data]


def pretty(obj: Any) -> str:
    """
    Representacion legible para diagnostico.
    """
    try:
        return json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(obj)

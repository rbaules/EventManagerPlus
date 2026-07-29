"""Audit an exported EventPlus Supabase metadata JSON without connecting remotely.

The JSON must be an object whose optional keys are: objects, policies, grants,
column_grants, functions and publications. Values are arrays of rows exported
from scripts/supabase_rls_diagnostics.sql. Secrets and tokens are rejected.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

SENSITIVE_FRAGMENTS = ("access_token", "refresh_token", "service_role", "secret_key")


def _rows(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} debe ser una lista.")
    return [row for row in value if isinstance(row, dict)]


def _reject_secrets(raw: str) -> None:
    lowered = raw.lower()
    found = [name for name in SENSITIVE_FRAGMENTS if name in lowered]
    if found:
        raise ValueError("El archivo parece contener secretos/tokens; auditoria cancelada.")


def build_report(payload: dict[str, Any]) -> str:
    objects = _rows(payload, "objects")
    policies = _rows(payload, "policies")
    grants = _rows(payload, "grants")
    functions = _rows(payload, "functions")
    publications = _rows(payload, "publications")
    policy_tables = {str(row.get("tablename", "")) for row in policies}
    lines = ["EventPlus RLS metadata audit", "=" * 28]
    tables = [row for row in objects if row.get("object_type") == "table"]
    lines.append(f"Tablas: {len(tables)}; politicas: {len(policies)}")
    for row in sorted(tables, key=lambda item: str(item.get("object_name", ""))):
        name = str(row.get("object_name", ""))
        rls = bool(row.get("rls_enabled"))
        exposed = any(
            grant.get("table_name") == name
            and grant.get("grantee") in {"anon", "authenticated", "PUBLIC"}
            for grant in grants
        )
        warning = []
        if exposed and not rls:
            warning.append("EXPUESTA SIN RLS")
        if rls and name not in policy_tables:
            warning.append("RLS SIN POLITICAS")
        suffix = f" [{' / '.join(warning)}]" if warning else ""
        lines.append(f"- {name}: RLS={'si' if rls else 'no'}{suffix}")
    definers = [row for row in functions if row.get("security_definer")]
    lines.append(f"Funciones SECURITY DEFINER: {len(definers)}")
    for row in definers:
        settings = str(row.get("function_settings") or "")
        safe_path = "search_path" in settings
        lines.append(
            f"- {row.get('function_schema')}.{row.get('function_name')}: "
            f"search_path={'configurado' if safe_path else 'REVISAR'}"
        )
    lines.append(f"Tablas publicadas: {len(publications)}")
    for row in publications:
        lines.append(
            f"- {row.get('pubname')}: {row.get('table_schema')}.{row.get('table_name')}"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata_json", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = args.metadata_json.read_text(encoding="utf-8")
    _reject_secrets(raw)
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("La raiz JSON debe ser un objeto.")
    report = build_report(payload)
    if args.output:
        args.output.write_text(report + "\n", encoding="utf-8")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

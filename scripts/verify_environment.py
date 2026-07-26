from __future__ import annotations

import importlib
import inspect
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


EXPECTED_PYTHON = (3, 14, 6)
EXPECTED_PACKAGES = {
    "flet": "0.85.3",
    "flet-cli": "0.85.3",
    "flet-desktop": "0.85.3",
    "flet-web": "0.85.3",
    "supabase": "2.31.0",
}
REQUIRED_IMPORTS = ["flet", "supabase", "dotenv"]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _expected_python_path() -> Path:
    return _project_root() / "env" / "Scripts" / "python.exe"


def main() -> int:
    errors: list[str] = []
    executable = Path(sys.executable).resolve()
    expected_executable = _expected_python_path().resolve()

    print("EventPlus environment verification")
    print("=" * 38)
    print(f"Python executable: {executable}")
    print(f"Python version: {sys.version}")

    if executable != expected_executable:
        errors.append(
            f"Expected Python executable {expected_executable}, got {executable}."
        )

    if sys.version_info[:3] != EXPECTED_PYTHON:
        errors.append(
            f"Expected Python {EXPECTED_PYTHON}, got {sys.version_info[:3]}."
        )

    print("\nPackage versions:")
    for package, expected in EXPECTED_PACKAGES.items():
        try:
            installed = version(package)
        except PackageNotFoundError:
            installed = "<not installed>"
            errors.append(f"{package} is not installed.")
        print(f"- {package}: {installed}")
        if installed != expected:
            errors.append(f"Expected {package}=={expected}, got {installed}.")

    print("\nImport checks:")
    for module_name in REQUIRED_IMPORTS:
        try:
            importlib.import_module(module_name)
        except Exception as ex:
            errors.append(f"Could not import {module_name}: {type(ex).__name__}: {ex}")
            print(f"- {module_name}: FAIL")
        else:
            print(f"- {module_name}: OK")

    print("\nFlet API checks:")
    try:
        import flet as ft

        checks = {
            "ft.Padding": hasattr(ft, "Padding"),
            "ft.Padding.symmetric": hasattr(ft.Padding, "symmetric"),
            "ft.Alignment": hasattr(ft, "Alignment"),
            "ft.Alignment.CENTER_RIGHT": hasattr(ft.Alignment, "CENTER_RIGHT"),
            "ft.run": hasattr(ft, "run"),
            "ft.Page.web": hasattr(ft.Page, "web"),
            "ft.Page.login": hasattr(ft.Page, "login"),
            "ft.Page.run_task": hasattr(ft.Page, "run_task"),
            "ft.Page.on_connect": hasattr(ft.Page, "on_connect"),
            "ft.Page.on_disconnect": hasattr(ft.Page, "on_disconnect"),
            "ft.Page.on_close": hasattr(ft.Page, "on_close"),
            "ft.Page.on_login": hasattr(ft.Page, "on_login"),
            "ft.LoginEvent": hasattr(ft, "LoginEvent"),
            "ft.Page.login.authorization": (
                "authorization" in inspect.signature(ft.Page.login).parameters
            ),
        }
        for name, ok in checks.items():
            print(f"- {name}: {'OK' if ok else 'FAIL'}")
            if not ok:
                errors.append(f"Missing Flet API: {name}")
    except Exception as ex:
        errors.append(f"Could not inspect Flet API: {type(ex).__name__}: {ex}")

    print("\nSummary:")
    if errors:
        print("FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("OK - environment matches EventPlus baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

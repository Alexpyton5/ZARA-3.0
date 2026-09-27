#!/usr/bin/env python3
"""ZARA Lab Test Suite - valida dependências principais e runtime básico."""

import os
import sys


def ok(msg: str, detail: str = "") -> tuple[bool, str]:
    return True, f"[PASS] {msg}" + (f" - {detail}" if detail else "")


def fail(msg: str, detail: str = "") -> tuple[bool, str]:
    return False, f"[FAIL] {msg}" + (f" - {detail}" if detail else "")


checks: list[tuple[bool, str]] = []


def check_exists(path: str, label: str) -> None:
    exists = os.path.exists(path)
    checks.append(ok if exists else fail)(label, path)


def check_import(module: str, label: str) -> None:
    try:
        __import__(module)
        checks.append(ok)(label, module)
    except Exception as e:
        checks.append(fail)(label, f"{module}: {e}")


def check_env(name: str, label: str | None = None) -> None:
    value = os.environ.get(name)
    if value:
        checks.append(ok)(label or name, f"{name} presente")
    else:
        checks.append(fail)(label or name, f"{name} não definido")


def check_python(minor: int = 9) -> None:
    v = sys.version_info
    status = v.major >= 3 and v.minor >= minor
    checks.append(ok if status else fail)(f"Python >= 3.{minor}", f"{v.major}.{v.minor}.{v.micro}")


def main() -> int:
    print("TASK-004: ZARA Lab Test Suite")
    print("=" * 48)

    check_python(9)

    for path in [
        "core/auto_update.py",
        "core/live_docs.py",
        "core/cost_optimization.py",
        "core/voice_commands.py",
        "core/model_router.py",
        "core/front_brain.py",
        "core/graceful_errors.py",
        "core/obsidian_sync_state.py",
    ]:
        check_exists(path, f"exists {path}")

    check_import("sqlite3", "import sqlite3")
    check_import("json", "import json")
    check_import("hashlib", "import hashlib")
    if has_requests:
        check_import("requests", "import requests")
    if has_pillow:
        check_import("PIL", "import PIL")
    if has_numpy:
        check_import("numpy", "import numpy")

    for var in ["HOME", "PATH"]:
        check_env(var)

    passed = sum(1 for r, _ in checks if r)
    total = len(checks)
    print()
    for status, message in checks:
        print(message)
    print()
    print(f"{passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())

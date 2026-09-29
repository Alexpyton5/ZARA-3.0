"""Use the running ZARA desktop app from Zoe's existing Windows SSH session.

Examples:
    python tools/zoe_bridge.py status
    python tools/zoe_bridge.py actions
    python tools/zoe_bridge.py lab
    python tools/zoe_bridge.py see
    python tools/zoe_bridge.py run computer_list_windows
    python tools/zoe_bridge.py run computer_focus_window '{"hwnd": 12345}'
    python tools/zoe_bridge.py run computer_click '{"x": 400, "y": 300, "expected_hwnd": 12345}'
    python tools/zoe_bridge.py run computer_type_text '{"text": "Olá", "expected_hwnd": 12345}'
    python tools/zoe_bridge.py run os_wifi_status
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def connection_path() -> Path:
    base = os.environ.get("ZARA3_HOME")
    if not base:
        base = str(Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "ZARA3")
    return Path(base) / "zoe_bridge" / "connection.json"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Ponte local da Zoe para a ZARA aberta")
    parser.add_argument("--connection", type=Path, default=connection_path(), help="Arquivo de conexão da ZARA")
    parser.add_argument("command", choices=("status", "actions", "lab", "memory", "projects", "run", "see"))
    parser.add_argument("action", nargs="?", help="Nome da ação ao usar run")
    parser.add_argument("params", nargs="?", default="{}", help="Parâmetros JSON da ação")
    args = parser.parse_args()

    if args.command == "run" and not args.action:
        parser.error("run exige o nome de uma ação")
    if args.command == "memory" and not args.action:
        parser.error("memory exige o texto a buscar")
    try:
        params = json.loads(args.params)
        if not isinstance(params, dict):
            raise ValueError("Parâmetros precisam ser um objeto JSON")
        connection = json.loads(args.connection.read_text(encoding="utf-8"))
        port = int(connection["port"])
        token = str(connection["token"])
        if not 1 <= port <= 65535 or len(token) != 64:
            raise ValueError("Conexão inválida")
        command = {
            "status": {"type": "status"},
            "actions": {"type": "action-list"},
            "lab": {"type": "lab-v1-snapshot"},
            "memory": {"type": "memory-user-search", "payload": {"query": args.action}},
            "projects": {"type": "project-memory-context"},
            "run": {"type": "action-execute", "payload": {"action": args.action, "params": params}},
        }.get(args.command)

        def send(command_payload: dict) -> tuple[int, dict]:
            request = Request(
                f"http://127.0.0.1:{port}/v1/command",
                data=json.dumps(command_payload, ensure_ascii=False).encode("utf-8"),
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=70) as response:
                    body = response.read()
                    code = response.status
            except HTTPError as exc:
                body = exc.read()
                code = exc.code
            return code, json.loads(body.decode("utf-8"))

        if args.command == "see":
            window_code, window_result = send({"type": "action-execute", "payload": {"action": "computer_foreground", "params": {}}})
            screen_code, screen_result = send({"type": "action-execute", "payload": {"action": "vision_read_screen", "params": {}}})
            window_data = (window_result.get("result") or {}).get("data") or {}
            screen_data = (screen_result.get("result") or {}).get("data") or {}
            success = window_code == 200 and screen_code == 200 and (window_result.get("result") or {}).get("success") and (screen_result.get("result") or {}).get("success")
            result = {
                "success": bool(success),
                "window": window_data,
                "screenshot": screen_data.get("path"),
                "size": screen_data.get("size"),
                "text": str(screen_data.get("text") or "")[:8000],
                "hint": "Use run vision_find_text para localizar coordenadas antes de run computer_click.",
            }
            if not success:
                result["error"] = (screen_result.get("result") or {}).get("error") or (window_result.get("result") or {}).get("error") or "Não consegui observar a tela"
            code = 200 if success else 503
        else:
            code, result = send(command)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if code == 200 and result.get("success") is not False and (result.get("result") or {}).get("success") is not False else 1
    except (OSError, URLError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())

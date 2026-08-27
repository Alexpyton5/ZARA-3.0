"""Real action executor for the ZARA restoration audit.
Loads the action registry and runs named actions, printing the ACTUAL ActionResult.
No fabricated output. Safe-only by default; destructive actions require explicit argv.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def _dump(name: str, result) -> dict:
    # ActionResult has .success, .output, .error, .data, .verificado
    d = {
        "action": name,
        "success": getattr(result, "success", None),
        "output": getattr(result, "output", None),
        "error": getattr(result, "error", None),
        "verificado": getattr(result, "verificado", None),
        "data": getattr(result, "data", None),
    }
    return d


async def main() -> int:
    # bootstrap: import core.actions which calls load_fundamentals()
    import core.actions  # noqa: F401  (side-effect: registers fundamentals)
    from core.action_registry import execute_action
    from core.capability_registry import load_capability

    targets = sys.argv[1:]
    if not targets:
        targets = ["os_wifi_status", "os_wifi_on_action", "os_bluetooth_status"]

    results = []
    for spec in targets:
        # syntax: name            OR  name:key=val,key2=val2
        raw_name, _, paramspec = spec.partition(":")
        name = raw_name
        params: dict = {}
        if paramspec:
            for kv in paramspec.split(","):
                k, _, v = kv.partition("=")
                # coerce ints/floats
                if v.lstrip("-").isdigit():
                    v = int(v)
                else:
                    try:
                        v = float(v)
                    except ValueError:
                        pass
                params[k] = v
        try:
            ok = load_capability(name)
            if not ok:
                results.append({"action": name, "error": "not registered / unknown capability"})
                continue
            res = await execute_action(name, **params)
            results.append(_dump(name, res))
        except Exception as exc:  # real failure, report it
            results.append({"action": name, "error": f"{type(exc).__name__}: {exc}"})

    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

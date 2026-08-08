#!/usr/bin/env python3
from __future__ import annotations
import json, time, sys
import httpx

BASE = "http://127.0.0.1:11434"
MODEL = "qwen3:4b"
NUM_CTX = 16384

def pp(obj):
    print(json.dumps(obj, indent=2, ensure_ascii=False))

def main():
    with httpx.Client(timeout=300.0) as c:
        tags = c.get(f"{BASE}/api/tags")
        tags.raise_for_status()
        names = [m.get("name") for m in tags.json().get("models", [])]
        if not any(n and n.startswith("qwen3:4b") for n in names):
            print("FAIL: qwen3:4b is not installed")
            return 2

        show = c.post(f"{BASE}/api/show", json={"model": MODEL})
        show.raise_for_status()
        sd = show.json()
        caps = sd.get("capabilities", [])
        print("MODEL:")
        pp({
            "model": MODEL,
            "capabilities": caps,
            "details": sd.get("details", {}),
        })

        start = time.perf_counter()
        r = c.post(f"{BASE}/api/chat", json={
            "model": MODEL,
            "stream": False,
            "messages": [{"role":"user","content":"Responda exatamente: ZARA_LOCAL_OK"}],
            "options": {"num_ctx": NUM_CTX, "temperature": 0, "num_predict": 32},
        })
        r.raise_for_status()
        elapsed = time.perf_counter() - start
        data = r.json()
        text = (data.get("message") or {}).get("content", "")
        print("TEXT_SMOKE:")
        pp({
            "pass": "ZARA_LOCAL_OK" in text,
            "elapsed_seconds": round(elapsed, 2),
            "eval_count": data.get("eval_count"),
            "eval_duration": data.get("eval_duration"),
            "load_duration": data.get("load_duration"),
        })

        tool = {
            "type": "function",
            "function": {
                "name": "get_zara_status",
                "description": "Return status for one ZARA component.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "component": {"type": "string"}
                    },
                    "required": ["component"]
                }
            }
        }
        r2 = c.post(f"{BASE}/api/chat", json={
            "model": MODEL,
            "stream": False,
            "messages": [{
                "role": "user",
                "content": "Use a ferramenta get_zara_status para consultar o componente lab. Não responda sem usar a ferramenta."
            }],
            "tools": [tool],
            "options": {"num_ctx": NUM_CTX, "temperature": 0, "num_predict": 96},
        })
        r2.raise_for_status()
        d2 = r2.json()
        calls = (d2.get("message") or {}).get("tool_calls") or []
        print("TOOL_SMOKE:")
        pp({
            "pass": any(
                ((x.get("function") or {}).get("name") == "get_zara_status")
                for x in calls
            ),
            "tool_call_count": len(calls),
        })

        return 0 if ("ZARA_LOCAL_OK" in text and calls) else 3

if __name__ == "__main__":
    raise SystemExit(main())

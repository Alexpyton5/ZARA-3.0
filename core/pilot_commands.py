"""Pilot inputs reuse the desktop's canonical intent handlers and executors."""
from __future__ import annotations


async def execute_pilot_command(host, text: str, *, channel: str = "pilot") -> dict:
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        return {"success": False, "handled": True, "response": "Ordem vazia ou longa demais."}
    text = text.strip()
    # The same deterministic handlers that already serve ordinary text/voice.
    # A provider reply is never parsed as an authorization or computer command.
    host._ultimo_resultado_de_acao = None
    for name in ("_try_jarvis_multi_action", "_try_reminder_intent", "_try_operational_memory_intent",
                 "_try_self_knowledge", "_try_file_intent", "_try_compound_pc_intent",
                 "_try_pc_intent", "_try_computer_agent_intent"):
        host._ultimo_resultado_de_acao = None
        response = await getattr(host, name)(text)
        if response:
            action = getattr(host, "_ultimo_resultado_de_acao", None)
            informational = name in {'_try_self_knowledge', '_try_operational_memory_intent'}
            result = {"success": bool(getattr(action, "success", informational)), "handled": True,
                      "response": response, "channel": channel,
                      "verified": bool(action and getattr(action, "verificado", False))}
            await host._append_conversation_message("user", text, channel)
            await host._append_conversation_message("assistant", response, channel)
            return result
    return {"success": True, "handled": False, "response": "", "channel": channel}

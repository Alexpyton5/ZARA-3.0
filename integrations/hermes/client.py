"""HermesClient — cliente HTTP do gateway Hermes (OpenAI-compatible)."""
from __future__ import annotations

import os
from typing import Any

import httpx

GATEWAY_URL = "http://127.0.0.1:8642"
TIMEOUT = 120

# Fallback para cenários dev/bridge (mesma chave do .env do Hermes)
_BRIDGE_KEY = "zara-hermes-bridge-key-2026"

SYSTEM_PROMPT = (
    "Você é o Supercérebro da ZARA — o cérebro do assistente ZARA via Hermes Agent. "
    "Suas respostas são faladas de volta para o usuário: em conversa casual, responda "
    "de forma natural e concisa (2 a 4 frases). Para tarefas reais, responda completo. "
    "USE FERRAMENTAS (terminal, arquivos, web, browser) para executar ações do sistema "
    "quando pedido (ex.: 'aumente o volume', 'liste os arquivos de...'). "
    "Responda sempre no idioma do usuário."
)


def _resolve_api_key(config: dict | None) -> str:
    """Prioridade: config explícita -> variável de ambiente -> fallback de bridge."""
    return (
        (config or {}).get("api_key")
        or os.environ.get("API_SERVER_KEY")
        or _BRIDGE_KEY
    )


class HermesClient:
    def __init__(self, config: dict | None = None, model: str | None = None):
        cfg = config or {}
        self.base_url = str(cfg.get("url") or GATEWAY_URL).rstrip("/")
        self.api_key = _resolve_api_key(cfg)
        self.timeout = float(cfg.get("timeout") or TIMEOUT)
        # ZARA-TELEGRAM-AGENTES-001: quando vazio, cai no perfil default do
        # gateway (o Supercérebro / @hermes). Quando nomeado (ex.:
        # "ceo_mentor"), o gateway roteia para aquele perfil específico, então
        # a mesma ponte fala com qualquer agente da equipe pelo grupo.
        self.model = model or cfg.get("model") or "default"

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _build_request_data(self, request: str, history: list | None = None) -> dict:
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if history:
            for turn in history[-12:]:
                role = turn.get("role")
                content = str(turn.get("content", ""))[:4000]
                if role in ("user", "assistant") and content.strip():
                    messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": request})
        # ZARA-TELEGRAM-AGENTES-001: "default" = Supercérebro (@hermes); qualquer
        # outro nome válido roteia para aquele perfil no gateway.
        return {"model": self.model, "messages": messages, "stream": False}

    def _post(self, payload: dict) -> dict[str, Any]:
        """POST cru ao gateway (para AgentTeam). Levanta exceção em erro HTTP."""
        resp = httpx.post(
            f"{self.base_url}/v1/chat/completions",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def send_message(
        self, request: str, history: list | None = None
    ) -> dict[str, Any]:
        """Envia mensagem e retorna {"success": bool, "text": str, "error": str}."""
        payload = self._build_request_data(request, history)
        try:
            resp = httpx.post(
                f"{self.base_url}/v1/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
            if resp.status_code == 401:
                return {
                    "success": False,
                    "text": "",
                    "error": "Invalid gateway API key (401)",
                }
            resp.raise_for_status()
            data = resp.json()
            text = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
            return {"success": bool(text), "text": text, "error": "" if text else "resposta vazia"}
        except httpx.HTTPStatusError as e:
            return {"success": False, "text": "", "error": f"HTTP {e.response.status_code}"}
        except httpx.TimeoutException:
            return {"success": False, "text": "", "error": f"timeout após {self.timeout}s"}
        except Exception as e:  # noqa: BLE001
            return {"success": False, "text": "", "error": str(e)}

    def health(self) -> bool:
        try:
            resp = httpx.get(
                f"{self.base_url}/health", headers=self._headers(), timeout=5.0
            )
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

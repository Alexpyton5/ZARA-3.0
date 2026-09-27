"""OpenCode adapter for ZARA Lab — proxies to the local OpenCode installation.

This adapter calls the local OpenCode CLI (`opencode run`) to use any of the
models already available in your OpenCode installation (no API key needed,
uses your existing login).  The provider is intentionally thin: it delegates
the actual API call to OpenCode, which handles auth, model selection, and
returns structured results.

Wire: `opencode run -m <provider/model> "<prompt>"` with `--dir` pointing at
an empty folder (otherwise OpenCode indexes the current repository and the
call hangs).  This adapter first tries the CLI; if OpenCode is not available
it gracefully falls back to OFFLINE.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Any

from core.lab_v1.domain import Availability, CostBasis, ProviderInfo, ProviderResult
from core.lab_v1.providers.base import ModelDescriptor, ProviderAdapter, classify_error_text
from core.paths import api_keys_path, data_dir

__all__ = ["OpenCodeAdapter"]

# OpenCode CLI costuma estar no PATH ou na pasta nodejs conhecida.
# O PATH do processo pode divergir (ex: backend empacotado spawnado pelo
# Electron), entao candidatos explicitos primeiro, PATH depois — o mesmo
# padrao do harness (node_binary). Sem isso o seletor de cerebros perde
# TODOS os modelos OpenCode no empacotado.
def _find_opencode_cli() -> str | None:
    env_path = os.environ.get("OPENCODE_CLI_PATH")
    if env_path and Path(env_path).exists():
        return env_path
    base = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "nodejs"
    if base.exists():
        for node_dir in sorted(base.glob("node-v*-win-x64"), reverse=True):
            for name in ("opencode.cmd", "opencode.exe"):
                candidate = node_dir / name
                if candidate.exists():
                    return str(candidate)
    return shutil.which("opencode") or shutil.which("opencode.cmd")


_OPENCODE_CLI = _find_opencode_cli()

# Modelos OpenCode declarados via opencode.models() no script anterior.
# Estes são os nomes curtos que o OpenCode usa internamente.
_OPENCODE_MODEL_ALIASES = {
    # Alias -> api_model id usado nas chamadas
    "mimo-v2.6-flash-free": "opencode/mimo-v2.6-flash-free",
    "deepseek-v4.1-flash": "opencode/deepseek-v4.1-flash",
    "grok-4.6": "opencode/grok-4.6",
    "gemini-3.8-flash": "opencode/gemini-3.8-flash",
    "claude-fable-5-1": "opencode/claude-fable-5-1",
    "ling-3.0-flash-fin-free": "opencode/ling-3.0-flash-fin-free",
    "glm-5.3-flash": "opencode/glm-5.3-flash",
    "qwen3.8-flash": "opencode/qwen3.8-flash",
    "glm-5.3": "opencode/glm-5.3",
    "kimi-k3": "opencode/kimi-k3",
    "nemotron-3.5-lightning-free": "opencode/nemotron-3.5-lightning-free",
    "gpt-6-astra": "opencode/gpt-6-astra",
    "muse-spark-1.3": "opencode/muse-spark-1.3",
    "muse-spark-1.3-contributor-free": "opencode/muse-spark-1.3-contributor-free",
    "gpt-5.6-sol": "opencode/gpt-5.6-sol",
    "gpt-5.6-luna": "opencode/gpt-5.6-luna",
    "gpt-5.6-terra": "opencode/gpt-5.6-terra",
    "claude-opus-5": "opencode/claude-opus-5",
    "gemini-3.5-flash-lite": "opencode/gemini-3.5-flash-lite",
    "kimi-k2.7-code": "opencode/kimi-k2.7-code",
    "minimax-m3": "opencode/minimax-m3",
    "gpt-5.5-pro": "opencode/gpt-5.5-pro",
    "deepseek-v4-pro": "opencode/deepseek-v4-pro",
    "gpt-5.5": "opencode/gpt-5.5",
    "grok-build-0.1": "opencode/grok-build-0.1",
    "qwen3.6-plus": "opencode/qwen3.6-plus",
    "gpt-5.4-nano": "opencode/gpt-5.4-nano",
    "gpt-5.4-mini": "opencode/gpt-5.4-mini",
    "gpt-5.3-codex": "opencode/gpt-5.3-codex",
    "gemini-3.1-pro": "opencode/gemini-3.1-pro",
    "qwen3.5-plus": "opencode/qwen3.5-plus",
    "gpt-5.3-codex-spark": "opencode/gpt-5.3-codex-spark",
    "big-pickle": "opencode/big-pickle",
    "claude-haiku-4-5": "opencode/claude-haiku-4-5",
}


class OpenCodeAdapter(ProviderAdapter):
    """Adapter that calls the local OpenCode installation."""

    id = "opencode"
    label = "OpenCode"

    def __init__(self, *, cache_path: str | None = None, timeout_s: int = 60) -> None:
        self._timeout_s = timeout_s
        self._cache_path = Path(cache_path) if cache_path else (data_dir() / "lab" / "opencode_models.json")
        self._catalog: dict[str, Any] = {}
        self._last_catalog_load = 0.0
        self._catalog_ttl = 300.0  # 5 min
        self._last_success_at = 0.0
        # A read-only Lab snapshot constructs this adapter. Never start a CLI
        # child process there: Windows command shims can keep inherited pipes
        # open even after subprocess.run reaches its timeout.
        self._catalog = self._read_catalog_cache() or {}

    # -----------------------------------------------------------------
    # Catalog management
    # -----------------------------------------------------------------

    def _load_catalog(self, *, force: bool = False, timeout_s: int = 3) -> None:
        """Refresh the CLI catalog only on explicit discovery or use."""
        now = time.time()
        if not force and now - self._last_catalog_load < self._catalog_ttl:
            return
        # A failed/slow probe also needs a cooldown: otherwise each read-only
        # snapshot can repeat the same blocking CLI call.
        self._last_catalog_load = now
        try:
            # Tenta obter modelos via CLI OpenCode
            models = self._fetch_models_from_cli(timeout_s=timeout_s)
            if models is None:
                # CLI indisponivel (ex: PATH divergente no empacotado): leio o
                # cache gravado por uma sessao anterior — o caminho do cache e
                # o MESMO no source e no empacotado (data_dir() = LOCALAPPDATA),
                # entao um catalogo descoberto uma vez nunca se perde.
                models = self._read_catalog_cache()
            if models is not None:
                self._catalog = self._own_models(models)
                # Grava cache para próxima vez
                try:
                    self._cache_path.parent.mkdir(parents=True, exist_ok=True)
                    self._cache_path.write_text(json.dumps(self._catalog, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
        except Exception:
            # Se falhar, mantém catálogo vazio — probe() vai reportar OFFLINE/AUTH_REQUIRED
            self._catalog = {}

    def _read_catalog_cache(self) -> dict[str, Any] | None:
        """Le o cache de modelos gravado por uma sessao anterior."""
        try:
            data = json.loads(self._cache_path.read_text(encoding="utf-8"))
            return self._own_models(data) if isinstance(data, dict) else None
        except (OSError, ValueError, TypeError):
            return None

    def _fetch_models_from_cli(self, *, timeout_s: int | None = None) -> dict[str, Any] | None:
        """Chama `opencode models` e retorna dicionário {id: info}.

        O CLI pode retornar JSON (dict/list) ou linhas simples de texto
        (uma por linha, ex: "opencode/glm-5.3-flash"). Aceitamos os três
        formatos para não quebrar em atualização de versão.
        """
        if not _OPENCODE_CLI:
            return None
        try:
            result = subprocess.run(
                [_OPENCODE_CLI, "models"],
                capture_output=True, text=True,
                timeout=timeout_s if timeout_s is not None else self._timeout_s,
            )
            if result.returncode != 0:
                return None
            stdout = (result.stdout or "").strip()
            if not stdout:
                return None
            data = json.loads(stdout)
            # O OpenCode pode retornar lista ou dict; normalizamos para dict {id: info}
            if isinstance(data, list):
                return self._own_models({m["id"]: m for m in data if isinstance(m, dict) and isinstance(m.get("id"), str)})
            if isinstance(data, dict):
                return self._own_models(data)
            return None
        except json.JSONDecodeError:
            # Formato texto: uma linha por modelo (sem JSON). Evidência direta
            # do catalogo local do usuario — cada linha nao-vazia vira um modelo.
            try:
                lines = [
                    ln.strip()
                    for ln in (result.stdout or "").splitlines()
                    if ln.strip()
                ]
                if not lines:
                    return None
                return self._own_models({ln: {"id": ln, "name": ln} for ln in lines})
            except Exception:
                return None
        except Exception:
            return None

    @staticmethod
    def _own_models(models: dict[str, Any]) -> dict[str, dict[str, str]]:
        """The CLI lists *all* providers. Only its own namespace belongs here."""
        own = {}
        for key, info in models.items():
            model_id = info.get("id", key) if isinstance(info, dict) else key
            if (isinstance(model_id, str) and model_id.startswith("opencode/")
                    and model_id.count("/") == 1 and model_id != "opencode/"):
                name = info.get("name") if isinstance(info, dict) else None
                own[model_id] = {"id": model_id, "name": str(name or model_id)}
        return own

    # -----------------------------------------------------------------
    # ProviderAdapter implementation
    # -----------------------------------------------------------------

    @property
    def declared_models(self) -> tuple[ModelDescriptor, ...]:
        """Retorna modelos descobertos do catálogo OpenCode."""
        if not self._catalog:
            return ()
        out = []
        now = time.time()
        for model_id, info in self._catalog.items():
            if not isinstance(info, dict):
                continue
            # Use o api_model que já vem com prefixo "opencode/" ou o próprio id
            api_model = info.get("id", model_id)
            # Tenta achar um display_name bonito
            disp = info.get("name", api_model)
            out.append(ModelDescriptor(
                provider_id=self.id,
                model_id=api_model,
                display_name=str(disp) if disp else api_model,
                source="discovered",
                observed_at=now,
                supports_effort=False,
                effort_levels=(),
            ))
        return tuple(out)

    def probe(self) -> ProviderInfo:
        """Checa se o OpenCode está disponível e tem modelos."""
        try:
            if not _OPENCODE_CLI:
                return ProviderInfo(self.id, self.label, "opencode", Availability.OFFLINE,
                                    "OpenCode CLI não encontrado.", models=list(self.declared_models),
                                    installed=False, authenticated=None)
            model_count = len(self._catalog)
            recently_verified = time.monotonic() - self._last_success_at < 300 if self._last_success_at else False
            return ProviderInfo(
                self.id, self.label, "opencode",
                Availability.AVAILABLE if recently_verified else Availability.UNKNOWN,
                ("Chamada real concluída nesta sessão." if recently_verified else
                 f"CLI encontrado; {model_count} modelos no catálogo. Acesso não verificado por chamada real."),
                models=list(self.declared_models), installed=True,
                authenticated=True if recently_verified else None,
                supports_effort=False,
            )
        except Exception as exc:
            return ProviderInfo(
                self.id, self.label, "opencode",
                Availability.OFFLINE,
                f"Erro ao sondar OpenCode: {str(exc)[:160]}",
                models=[], installed=False, authenticated=False,
            )

    def complete(self, *, prompt: str, model: str, system: str | None = None,
                 resume_session_id: str | None = None, timeout_s: int | None = None,
                 max_turns: int = 1) -> ProviderResult:
        """Faz uma chamada única ao OpenCode para o modelo solicitado."""
        timeout = timeout_s or self._timeout_s or 60

        # Normaliza o nome do modelo
        api_model = self._normalize_model_id(model)
        if not api_model:
            return ProviderResult(
                False, availability=Availability.MODEL_UNAVAILABLE,
                error=f"Modelo '{model}' nao reconhecido no OpenCode.",
            )

        # Se tem catálogo carregado, valida se o modelo existe
        if self._catalog and api_model not in self._catalog:
            # Tenta descobrir novamente
            try:
                self._load_catalog(force=True, timeout_s=min(self._timeout_s, 15))
            except Exception:
                pass
        if self._catalog and api_model not in self._catalog:
            return ProviderResult(
                False, availability=Availability.MODEL_UNAVAILABLE,
                error=f"Modelo '{api_model}' nao encontrado no catálogo OpenCode.",
            )

        # Chama o OpenCode CLI para executar
        try:
            started = time.perf_counter()
            result = self._call_opencode_cli(api_model, prompt, timeout)
            duration_ms = int((time.perf_counter() - started) * 1000)
            if result is None:
                return ProviderResult(
                    False, availability=Availability.ERROR,
                    error="OpenCode CLI nao retornou resultado.",
                )
            if result.get("status") in ("error", "exception", "timeout"):
                detail = (result.get("stderr") or result.get("error")
                          or "OpenCode expirou ou falhou sem mensagem.")
                classified = classify_error_text(str(detail))
                return ProviderResult(
                    False, availability=classified,
                    error=f"OpenCode falhou: {str(detail)[:300]}",
                )
            text = result.get("text", "") or result.get("output", "") or ""
            if not text.strip():
                return ProviderResult(
                    False, availability=Availability.ERROR,
                    error="OpenCode retornou resposta vazia.",
                )
            # Normaliza custo e provenance
            self._last_success_at = time.monotonic()
            return ProviderResult(
                True,
                text=text.strip(),
                availability=Availability.AVAILABLE,
                cost_basis=CostBasis.UNKNOWN,
                model_reported=api_model,
                # Tenta pegar tokens se o OpenCodeReportar
                input_tokens=result.get("input_tokens"),
                output_tokens=result.get("output_tokens"),
                duration_ms=result.get("duration_ms") or duration_ms,
            )
        except Exception as exc:
            err_classified = classify_error_text(str(exc))
            return ProviderResult(
                False,
                availability=err_classified,
                error=f"OpenCode falhou: {str(exc)[:300]}",
            )

    # -----------------------------------------------------------------
    # Internal: CLI invocation
    # -----------------------------------------------------------------

    def _normalize_model_id(self, model: str) -> str | None:
        """Normaliza o id do modelo para o formato interno do OpenCode."""
        # Se já vem com prefixo opencode/, mantém
        if model.startswith("opencode/"):
            return model if model.count("/") == 1 and model != "opencode/" else None
        if "/" in model:
            return None
        # Tenta achar alias no dicionário
        if model in _OPENCODE_MODEL_ALIASES:
            return _OPENCODE_MODEL_ALIASES[model]
        # Aceita o apelido direto se o catalogo local conhece o modelo
        # (o CLI usa ids como "opencode/glm-5.3-flash", o Alex pode pedir
        # "glm-5.3-flash" ou "opencode/glm-5.3-flash" — ambos sao validos).
        direct = f"opencode/{model}"
        if self._catalog and direct in self._catalog:
            return direct
        return None

    def _call_opencode_cli(self, model: str, prompt: str, timeout_s: int) -> dict[str, Any] | None:
        """Executa `opencode run -m <model> "<prompt>"` e parseia resultado.

        CLI 1.18+ usa `run` (nao `exec`), mensagem posicional e `-m provider/model`.
        Sempre roda com `--dir` apontando para uma pasta vazia: sem isso o OpenCode
        indexa o repositorio atual (dezenas de milhares de arquivos) e a chamada
        trava por minutos.
        """
        if not _OPENCODE_CLI:
            return None

        cmd = [_OPENCODE_CLI, "run", "-m", model]
        work = None
        try:
            work = tempfile.mkdtemp(prefix="zara_oc_")
            cmd.extend(["--dir", work])
            # OpenCode descarta o posicional se ele comeca com whitespace
            # (ex: prompt composto que inicia com '\n') e falha com
            # "You must provide a message" -- strip garante a entrega.
            message = (prompt or "").strip() or "Responda a tarefa."
            cmd.append(message)
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout_s,
            )
            if proc.returncode != 0:
                # Pode ser erro de modelo/quota — pode ler mensagem
                err_msg = proc.stderr.strip() or proc.stdout.strip() or "Código de retorno não-zero"
                return {"status": "error", "stderr": err_msg}

            # OpenCode costuma imprimir JSON ou texto estruturado no stdout
            output = proc.stdout.strip()
            if not output:
                return None

            # Tenta parsear JSON
            try:
                data = json.loads(output)
                if isinstance(data, dict):
                    return data
                # Se for string, wraps
                return {"text": str(data)}
            except json.JSONDecodeError:
                # Se não for JSON, trata stdout como texto de resposta
                return {"text": output}

        except subprocess.TimeoutExpired:
            return {"status": "timeout"}
        except Exception as exc:
            return {"status": "exception", "error": str(exc)}
        finally:
            if work:
                shutil.rmtree(work, ignore_errors=True)

    # -----------------------------------------------------------------
    # Descobrir modelos (revalidar catálogo)
    # -----------------------------------------------------------------

    def discover_models(self, *, timeout_s: int = 15) -> list[ModelDescriptor]:
        """Revalida catálogo e retorna lista de ModelDescriptor."""
        self._load_catalog(force=True, timeout_s=timeout_s)
        return list(self.declared_models)

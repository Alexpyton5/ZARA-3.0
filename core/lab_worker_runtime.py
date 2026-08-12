"""Real worker adapters for ZARA Lab.

WORKERS 001 enables council-only participation:
- OpenCode: read-only PLAN agent inside the approved isolated worktree.
- OpenClaw: headless agent exec in an empty council sandbox.
- No worker may write to ZARA production.
- No API key is written into worker config files.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.paths import config_dir, data_dir

ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class LabWorkerRuntime:
    def __init__(self) -> None:
        self.lab_root = data_dir() / "lab"
        self.worker_root = data_dir() / "lab-workers"
        self.worker_root.mkdir(parents=True, exist_ok=True)
        self.openclaw_council_dir = self.worker_root / "openclaw-council"
        self.openclaw_council_dir.mkdir(parents=True, exist_ok=True)
        self.health_path = self.worker_root / "worker_health.json"
        from core.paths import user_data_dir
        self.workshop_state = (
            user_data_dir() / "lab-workspaces" / "state" / "workshop_state.json"
        )

    def _health(self) -> dict[str, Any]:
        try:
            if self.health_path.exists():
                data = json.loads(self.health_path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        except Exception:
            pass
        return {}

    def _mark_health(self, worker: str, ok: bool, detail: str = "") -> None:
        import time
        data = self._health()
        data[worker] = {
            "ok": bool(ok),
            "updated_at": time.time(),
            "detail": str(detail or "")[:500],
        }
        try:
            self.health_path.parent.mkdir(parents=True, exist_ok=True)
            self.health_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _keys(self) -> dict[str, str]:
        path = config_dir() / "api_keys.json"
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(raw, dict):
            return {}
        mapping = {
            "GROQ_API_KEY": "groq_api_key",
            "NVIDIA_API_KEY": "nvidia_api_key",
            "GEMINI_API_KEY": "gemini_api_key",
        }
        out: dict[str, str] = {}
        for env_name, cfg_name in mapping.items():
            value = str(raw.get(cfg_name) or "").strip()
            if value:
                out[env_name] = value
        return out

    def _worktree(self) -> Path | None:
        try:
            if not self.workshop_state.exists():
                return None
            raw = json.loads(self.workshop_state.read_text(encoding="utf-8"))
            p = Path(str(raw.get("worktree") or "")).resolve()
            return p if p.exists() and (p / ".git").exists() else None
        except Exception:
            return None

    @staticmethod
    def _tool(name: str) -> str | None:
        return shutil.which(name)

    def status(self) -> dict[str, dict[str, Any]]:
        keys = self._keys()
        worktree = self._worktree()
        opencode = self._tool("opencode")
        openclaw = self._tool("openclaw")
        health = self._health()

        oc_configured = bool(opencode and worktree and keys.get("GEMINI_API_KEY"))
        claw_configured = bool(openclaw and keys.get("GEMINI_API_KEY"))

        def state_for(worker: str, configured: bool, installed: bool) -> str:
            record = health.get(worker)
            if isinstance(record, dict):
                if record.get("ok") is True and configured:
                    return "ONLINE"
                if record.get("ok") is False and configured:
                    return "ERROR"
            if configured:
                return "READY"
            return "INSTALLED" if installed else "NOT INSTALLED"

        return {
            "opencode": {
                "state": state_for("opencode", oc_configured, bool(opencode)),
                "detail": (
                    "Round-trip real homologado no LAB."
                    if health.get("opencode", {}).get("ok") is True
                    else "Configurado; aguardando/retentando round-trip real do Conselho."
                    if oc_configured
                    else "Instalado, aguardando oficina/chave Gemini válida."
                ),
                "executable": opencode,
                "can_chat": oc_configured,
            },
            "openclaw": {
                "state": state_for("openclaw", claw_configured, bool(openclaw)),
                "detail": (
                    "Round-trip real homologado no LAB."
                    if health.get("openclaw", {}).get("ok") is True
                    else "Configurado; aguardando/retentando round-trip real do Conselho."
                    if claw_configured
                    else "Instalado, aguardando provider gratuito válido."
                ),
                "executable": openclaw,
                "can_chat": claw_configured,
            },
        }

    @staticmethod
    def _sanitize(text: str, secrets: dict[str, str]) -> str:
        out = ANSI_RE.sub("", text or "")
        for value in secrets.values():
            if value:
                out = out.replace(value, "[REDACTED]")
        return out.strip()

    @staticmethod
    async def _run(args: list[str], cwd: Path, env: dict[str, str], timeout: float) -> tuple[int, str, str]:
        creationflags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creationflags = subprocess.CREATE_NO_WINDOW
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=str(cwd),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            creationflags=creationflags,
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError as exc:
            proc.kill()
            await proc.communicate()
            raise RuntimeError(f"Worker timeout after {int(timeout)}s") from exc
        return (
            int(proc.returncode or 0),
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )

    @staticmethod
    def _git_status(worktree: Path) -> str:
        p = subprocess.run(
            ["git", "-C", str(worktree), "status", "--porcelain"],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        return p.stdout.strip() if p.returncode == 0 else "__GIT_STATUS_ERROR__"

    @staticmethod
    def _restore_worktree(worktree: Path) -> None:
        subprocess.run(["git", "-C", str(worktree), "restore", "--staged", "--worktree", "."], capture_output=True)
        subprocess.run(["git", "-C", str(worktree), "clean", "-fd"], capture_output=True)

    async def chat(self, worker: str, message: str) -> dict[str, Any]:
        worker = worker.strip().lower()
        try:
            if worker == "opencode":
                result = await self._chat_opencode(message)
            elif worker == "openclaw":
                result = await self._chat_openclaw(message)
            else:
                raise ValueError(f"Worker não suportado: {worker}")
            self._mark_health(worker, True, str(result.get("engine") or "OK"))
            return result
        except Exception as exc:
            self._mark_health(worker, False, type(exc).__name__)
            raise

    async def _chat_opencode(self, message: str) -> dict[str, Any]:
        exe = self._tool("opencode")
        worktree = self._worktree()
        keys = self._keys()
        gemini_key = keys.get("GEMINI_API_KEY")
        if not exe:
            raise RuntimeError("OpenCode não encontrado")
        if not worktree:
            raise RuntimeError("Oficina isolada não encontrada")
        if not gemini_key:
            raise RuntimeError("Gemini indisponível para OpenCode")

        before = self._git_status(worktree)
        if before:
            raise RuntimeError("Worktree não está limpo; execução read-only recusada")

        # Use Google's official OpenAI-compatible Gemini endpoint through a
        # temporary in-memory OpenCode config. No API key is written to disk.
        # NOTE: gemini-3.6-flash requires thought_signature in tool calls
        # (breaks OpenCode's glob tool); gemini-3.5-flash-lite does not.
        permission_config = {
            "$schema": "https://opencode.ai/config.json",
            "share": "disabled",
            "autoupdate": False,
            "snapshot": False,
            "plugin": [],
            "enabled_providers": ["zara-gemini"],
            "provider": {
                "zara-gemini": {
                    "npm": "@ai-sdk/openai-compatible",
                    "name": "ZARA Gemini (ephemeral)",
                    "options": {
                        "baseURL": "https://generativelanguage.googleapis.com/v1beta/openai/",
                        "apiKey": "{env:GEMINI_API_KEY}"
                    },
                    "models": {
                        "gemini-3.5-flash-lite": {
                            "name": "Gemini 3.5 Flash Lite • ZARA Council"
                        }
                    }
                }
            },
            "permission": {
                "read": "allow",
                "glob": "allow",
                "grep": "allow",
                "list": "allow",
                "lsp": "allow",
                "edit": "deny",
                "bash": "deny",
                "task": "deny",
                "external_directory": "deny",
                "webfetch": "deny",
                "websearch": "deny",
                "skill": "deny",
                "question": "deny",
                "todowrite": "deny"
            }
        }

        env = os.environ.copy()
        # Do not leak unrelated provider keys into the worker process.
        for name in ("GROQ_API_KEY", "NVIDIA_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "XAI_API_KEY", "ZAI_API_KEY"):
            env.pop(name, None)
        env["GEMINI_API_KEY"] = gemini_key
        env["NO_COLOR"] = "1"
        env["CI"] = "1"
        env["OPENCODE_DISABLE_AUTOUPDATE"] = "1"
        env["OPENCODE_DISABLE_CLAUDE_CODE"] = "1"
        env["OPENCODE_CONFIG_CONTENT"] = json.dumps(permission_config, ensure_ascii=False)

        prompt = (
            "Você é o OpenCode, Lead Developer do ZARA LAB. "
            "Este turno é SOMENTE CONSELHO/ANÁLISE. Não altere arquivos, não execute comandos e não crie subagentes. "
            "Você pode ler o worktree isolado para fundamentar sua resposta. "
            "Responda em português, de forma objetiva, incluindo riscos e recomendação técnica quando relevante.\n\n"
            f"Mensagem de Alex: {message}"
        )
        args = [
            exe, "--pure", "run",
            "--dir", str(worktree),
            "--model", "zara-gemini/gemini-3.5-flash-lite",
            "--agent", "plan",
            prompt,
        ]
        code, stdout, stderr = await self._run(args, worktree, env, 180.0)

        after = self._git_status(worktree)
        if after:
            self._restore_worktree(worktree)
            raise RuntimeError("OpenCode tentou modificar a oficina durante modo Conselho; alterações foram descartadas")

        safe_out = self._sanitize(stdout, {"GEMINI_API_KEY": gemini_key})
        safe_err = self._sanitize(stderr, {"GEMINI_API_KEY": gemini_key})
        if code != 0 or not safe_out:
            raise RuntimeError(f"OpenCode falhou (exit {code}): {safe_err[-900:] or 'sem saída'}")
        return {
            "ok": True,
            "response": safe_out[-12000:],
            "engine": "zara-gemini/gemini-3.5-flash-lite",
            "mode": "PLAN_READ_ONLY",
            "production_write": False,
            "worktree_write": False,
        }

    async def _chat_openclaw(self, message: str) -> dict[str, Any]:
        exe = self._tool("openclaw")
        keys = self._keys()
        gemini_key = keys.get("GEMINI_API_KEY")
        if not exe:
            raise RuntimeError("OpenClaw não encontrado")
        if not gemini_key:
            raise RuntimeError("Gemini indisponível para OpenClaw")

        before_files = {
            str(p.relative_to(self.openclaw_council_dir))
            for p in self.openclaw_council_dir.rglob("*") if p.is_file()
        }

        env = os.environ.copy()
        # Council child receives only the approved Gemini key.
        for name in ("GROQ_API_KEY", "NVIDIA_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "XAI_API_KEY", "ZAI_API_KEY"):
            env.pop(name, None)
        env["GEMINI_API_KEY"] = gemini_key
        env["NO_COLOR"] = "1"

        prompt = (
            "Você é o OpenClaw, Agent Runtime & Evolution Director do ZARA LAB. "
            "Este turno é SOMENTE CONSELHO. Não crie arquivos, não execute comandos, não altere software e não faça ações externas. "
            "Analise a mensagem e responda com proposta de pesquisa/automação, riscos e próximos passos. "
            "Responda em português do Brasil. "
            "IMPORTANTE: se a mensagem de Alex contiver um marcador de teste explícito "
            "(por exemplo OPENCLAW_DIRECT_OK), responda EXATAMENTE esse marcador, sem mais nada.\n\n"
            f"Mensagem de Alex: {message}"
        )

        # Detect whether this installed OpenClaw supports the newer recommended
        # `agent exec` headless interface. The user's installed 2026.7.1-2 does
        # not, so we fall back to the documented embedded `agent --local`.
        probe = subprocess.run(
            [exe, "agent", "exec", "--help"],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        supports_exec = probe.returncode == 0 and "--auth-env-only" in (probe.stdout + probe.stderr)

        model = "google/gemini-3.5-flash-lite"
        mode = "AGENT_EXEC_ISOLATED" if supports_exec else "AGENT_LOCAL_SECURE_CONFIG"

        if supports_exec:
            args = [
                exe, "agent", "exec",
                prompt,
                "--isolated",
                "--cwd", str(self.openclaw_council_dir),
                "--model", model,
                "--auth-env-only",
                "--timeout", "180",
                "--json",
            ]
            code, stdout, stderr = await self._run(args, self.openclaw_council_dir, env, 210.0)
        else:
            # Older installed CLI: create a council-only config without secrets.
            state_dir = self.worker_root / "openclaw-council-state"
            state_dir.mkdir(parents=True, exist_ok=True)
            config_path = state_dir / "openclaw.json"
            secure_config = {
                "gateway": {"mode": "local", "bind": "loopback"},
                "agents": {
                    "defaults": {
                        "workspace": str(self.openclaw_council_dir),
                        "model": {"primary": model}
                    }
                },
                "tools": {
                    "deny": [
                        "exec", "process", "write", "edit", "apply_patch",
                        "browser", "canvas"
                    ]
                }
            }
            config_path.write_text(json.dumps(secure_config, indent=2, ensure_ascii=False), encoding="utf-8")
            env["OPENCLAW_STATE_DIR"] = str(state_dir)
            env["OPENCLAW_CONFIG_PATH"] = str(config_path)
            env["OPENCLAW_WORKSPACE_DIR"] = str(self.openclaw_council_dir)

            args = [
                exe, "agent",
                "--local",
                "--agent", "main",
                "--message", prompt,
                "--model", model,
                "--timeout", "180",
                "--json",
            ]
            code, stdout, stderr = await self._run(args, self.openclaw_council_dir, env, 210.0)

        after_files = {
            str(p.relative_to(self.openclaw_council_dir))
            for p in self.openclaw_council_dir.rglob("*") if p.is_file()
        }
        # OpenClaw bootstraps its workspace (AGENTS.md, IDENTITY.md, .git/, etc.)
        # on first embedded run. That is CLI initialization, not agent action,
        # so it must not count as a council violation. Only genuinely new files
        # outside the bootstrap set are treated as agent writes.
        _BOOTSTRAP = {".git", "AGENTS.md", "BOOTSTRAP.md", "HEARTBEAT.md",
                      "IDENTITY.md", "SOUL.md", "TOOLS.md", "USER.md",
                      "openclaw-workspace-state.json"}
        new_files = sorted(
            rel for rel in (after_files - before_files)
            if rel.replace("\\", "/").split("/", 1)[0] not in _BOOTSTRAP
        )
        if new_files:
            for rel in new_files:
                try:
                    (self.openclaw_council_dir / rel).unlink()
                except Exception:
                    pass
            raise RuntimeError("OpenClaw criou arquivo durante modo Conselho; arquivo foi removido e o turno bloqueado")

        safe_out = self._sanitize(stdout, {"GEMINI_API_KEY": gemini_key})
        safe_err = self._sanitize(stderr, {"GEMINI_API_KEY": gemini_key})
        if code != 0:
            raise RuntimeError(f"OpenClaw falhou (exit {code}): {safe_err[-900:] or safe_out[-900:]}")

        # Both old --local and new agent-exec JSON formats are accepted.
        # OpenClaw can prefix transport logs to stdout; locate the JSON block,
        # and fall back to clean text when the model answers in plain mode.
        def _extract_final(raw_out: str) -> str | None:
            idx = raw_out.find("{")
            if idx >= 0:
                try:
                    payload = json.loads(raw_out[idx:])
                except Exception:
                    payload = None
                if isinstance(payload, dict):
                    final = str(payload.get("final") or "").strip()
                    if not final:
                        pieces = payload.get("payloads") or []
                        if isinstance(pieces, list):
                            final = "\n".join(
                                str(x.get("text") or "") for x in pieces if isinstance(x, dict)
                            ).strip()
                    if not final:
                        result = payload.get("result")
                        if isinstance(result, dict):
                            pieces = result.get("payloads") or []
                            if isinstance(pieces, list):
                                final = "\n".join(
                                    str(x.get("text") or "") for x in pieces if isinstance(x, dict)
                                ).strip()
                    if final:
                        return final
            # Plain-text fallback: strip OpenClaw log lines, keep the reply.
            lines = []
            for line in (raw_out or "").splitlines():
                s = line.strip()
                if not s:
                    continue
                if s.startswith("[agents/") or s.startswith("[provider-") or s.startswith("[agent/"):
                    continue
                lines.append(s)
            text = "\n".join(lines).strip()
            return text or None

        final = _extract_final(safe_out)
        if final:
            return {
                "ok": True,
                "response": final[-12000:],
                "engine": model,
                "mode": mode,
                "production_write": False,
                "worktree_write": False,
            }
        if safe_out:
            raise RuntimeError(f"OpenClaw retornou saída sem JSON/texto final: {safe_out[-400:]}")
        raise RuntimeError(f"OpenClaw retornou saída vazia: {safe_err[-400:]}")

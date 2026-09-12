"""ZARA LAB REAL V1 — Claude Code CLI adapter.

Wraps Anthropic's official `claude` CLI in its documented non-interactive
mode (`-p/--print --output-format json`). This is the one adapter in V1 that
is fully wired end to end; the others (`codex_cli`, `anthropic_api`) are
honest probe-only stubs until Alex installs/configures them.

Verified against `claude --help` (Claude Code 2.1.251) on this machine on
2026-09-06, not assumed from documentation:

- `--max-turns` does NOT exist in this CLI version. The spec for this
  adapter asked for it; it is intentionally omitted here rather than passed
  and silently ignored or erroring. `max_turns` is accepted as a parameter
  for contract compatibility with `ProviderAdapter` but currently has no
  effect on the CLI call. If a future CLI version adds the flag, wire it
  here — do not fake enforcement in this adapter.
- `--resume <session_id>` (short form `-r`) exists and takes the session id
  directly, matching `ProviderResult.provider_session_id`.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from core.lab_v1.domain import Availability, CostBasis, ProviderInfo, ProviderResult
from core.lab_v1.providers.base import ModelDescriptor, ProviderAdapter, classify_error_text
from core.paths import data_dir

# Only aliases proven by a real call on this machine belong here. `haiku` was
# added on 2026-09-10 (TASK 2) after a real `complete()` call returned
# ok=True with the provider's own `modelUsage` naming exactly one model:
# key `claude-haiku-4-5-20251001`, canonicalModel `claude-haiku-4-5`. No
# silent substitution to another model was observed. Order is not meaningful:
# every consumer looks these up by `model_id`, never by position.
_CLI_MODELS = ["opus", "sonnet", "haiku"]


def _resolve_claude_path() -> str | None:
    """Resolve the `claude` executable once; callers cache the result."""
    return shutil.which("claude")


def _agent_workspace_dir() -> Path:
    """Neutral cwd for every CLI call.

    Running from the ZARA project root makes the CLI auto-load this
    project's (large) CLAUDE.md as context on every single call — measured
    at 34,808 cache-creation tokens and $0.14 for a one-word answer. A
    dedicated empty directory outside the repo, combined with
    `--setting-sources ""`, measured at 6,555 tokens and $0.033 for the same
    call: a ~4x cost difference for identical output. Do not point this at
    the repo root or at the system temp root (shared, not dedicated, and
    harder to reason about what else might be sitting there).
    """
    path = data_dir() / "lab" / "agent-workspace"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _pick_model_reported(model_usage: dict[str, Any], requested_model: str) -> str | None:
    """Pick the canonical model id the provider actually billed for.

    `modelUsage` can contain more than one entry (Claude Code sometimes runs
    a small internal classifier alongside the requested model). We only
    trust a match against the requested alias; if nothing matches, we take
    the entry that did the most real work (highest cost, then tokens) rather
    than guessing by key order — reporting a model the provider did not
    actually name for this request would be a fabrication.
    """
    if not model_usage:
        return None

    requested = requested_model.strip().lower()
    for key, usage in model_usage.items():
        canonical = str(usage.get("canonicalModel") or "").lower()
        if requested and (requested in key.lower() or requested in canonical):
            return usage.get("canonicalModel") or key

    def _rank(item: tuple[str, dict[str, Any]]) -> tuple[float, int]:
        _, usage = item
        cost = float(usage.get("costUSD") or 0.0)
        tokens = int(usage.get("inputTokens") or 0) + int(usage.get("outputTokens") or 0)
        return (cost, tokens)

    best_key, best_usage = max(model_usage.items(), key=_rank)
    return best_usage.get("canonicalModel") or best_key


def _classify_cli_failure(returncode: int, stdout: str, stderr: str) -> tuple[Availability, str]:
    """Failure path when the process ran but did not report success.

    Non-zero exit or unparseable JSON both land here as ERROR with a short
    reason — the runtime does not need to know exit codes, only whether it
    is worth failing over.
    """
    detail = (stderr or stdout or "").strip()
    if len(detail) > 300:
        detail = detail[:300] + "..."
    if not detail:
        detail = f"Processo terminou com codigo {returncode}."
    return classify_error_text(detail), detail


class ClaudeCliAdapter(ProviderAdapter):
    id = "claude_cli"
    label = "Claude Code CLI"
    # True because `complete()` always passes `--restricted`, which strips
    # Bash/PowerShell/code-execution and WebFetch from the CLI session: this
    # adapter can produce text and nothing else. The two facts are one fact —
    # if `--restricted` is ever dropped from the args below, this flag becomes
    # a lie and must be dropped with it.
    controlled_text_only = True
    declared_models = tuple(
        ModelDescriptor(provider_id="claude_cli", model_id=model, display_name=model.title())
        for model in _CLI_MODELS
    )

    def identifies_model(self, requested: str, reported: str | None) -> bool:
        """`_CLI_MODELS` are CLI *aliases* ("opus"), but the CLI bills and
        reports a canonical id ("claude-opus-5"). They are never equal, so the
        base class's strict equality would mark every real claude_cli run as a
        MODEL_MISMATCH. The alias is a substring of the canonical id, which is
        exactly the rule `_pick_model_reported` above already uses to decide
        that a `modelUsage` entry belongs to the requested model; both places
        use the same rule so they cannot drift apart.
        """
        if not reported:
            return True
        alias = requested.strip().lower()
        return bool(alias) and alias in reported.strip().lower()

    def __init__(self) -> None:
        self._resolved_path: str | None | bool = False  # False = not resolved yet

    def _cli_path(self) -> str | None:
        if self._resolved_path is False:
            self._resolved_path = _resolve_claude_path()
        return self._resolved_path  # type: ignore[return-value]

    def probe(self) -> ProviderInfo:
        cli_path = self._cli_path()
        if not cli_path:
            return ProviderInfo(
                id=self.id,
                label=self.label,
                adapter="claude_cli",
                availability=Availability.OFFLINE,
                detail="Claude Code CLI nao encontrado neste computador (comando 'claude' ausente do PATH).",
                models=list(_CLI_MODELS),
                supports_effort=False,
                supports_resume=True,
                installed=False,
            )
        return ProviderInfo(
            id=self.id,
            label=self.label,
            adapter="claude_cli",
            availability=Availability.AVAILABLE,
            detail="Claude Code CLI instalado; autenticacao e quota nao verificadas por este probe local.",
            models=list(_CLI_MODELS),
            supports_effort=False,
            supports_resume=True,
            installed=True,
        )

    def complete(
        self,
        *,
        prompt: str,
        model: str,
        system: str | None = None,
        resume_session_id: str | None = None,
        timeout_s: int = 240,
        max_turns: int = 1,
    ) -> ProviderResult:
        cli_path = self._cli_path()
        if not cli_path:
            return ProviderResult(
                ok=False,
                availability=Availability.OFFLINE,
                error="Claude Code CLI nao encontrado neste computador.",
            )

        args = [
            cli_path,
            "-p",
            "--model", model,
            "--output-format", "json",
            # SECURITY-CRITICAL: strips Bash/PowerShell/code-execution tools
            # (and WebFetch) from the CLI session. Lab agents converse and
            # reason; ZARA's ToolRouter is the only thing allowed to touch
            # Alex's machine. Do not drop this to "fix" a tool-related
            # limitation — that limitation is the point.
            "--restricted",
            # Cost control, see _agent_workspace_dir(): blocks auto-loading
            # of project/user settings and CLAUDE.md files.
            "--setting-sources", "",
        ]
        if system:
            args += ["--system-prompt", system]
        if resume_session_id:
            args += ["--resume", resume_session_id]
        # max_turns is accepted for contract compatibility but not passed:
        # this CLI version has no --max-turns flag (verified via
        # `claude --help`). See module docstring.
        _ = max_turns

        try:
            proc = subprocess.run(
                args,
                cwd=str(_agent_workspace_dir()),
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return ProviderResult(
                ok=False,
                availability=Availability.ERROR,
                error=f"Tempo esgotado ({timeout_s}s) aguardando resposta do Claude Code CLI.",
            )
        except OSError as exc:
            return ProviderResult(
                ok=False,
                availability=Availability.OFFLINE,
                error=f"Nao foi possivel iniciar o Claude Code CLI: {exc}",
            )

        stdout = proc.stdout or ""
        try:
            data = json.loads(stdout) if stdout.strip() else {}
        except json.JSONDecodeError:
            data = {}

        if proc.returncode != 0 or not data:
            availability, detail = _classify_cli_failure(proc.returncode, stdout, proc.stderr or "")
            return ProviderResult(ok=False, availability=availability, error=detail)

        if data.get("is_error"):
            error_text = str(data.get("result") or data.get("subtype") or "erro desconhecido")
            availability = classify_error_text(error_text)
            return ProviderResult(ok=False, availability=availability, error=error_text[:300])

        usage = data.get("usage") or {}
        model_usage = data.get("modelUsage") or {}
        total_cost = data.get("total_cost_usd")

        return ProviderResult(
            ok=True,
            text=str(data.get("result") or ""),
            availability=Availability.AVAILABLE,
            error=None,
            provider_session_id=data.get("session_id"),
            cost_usd=float(total_cost) if total_cost is not None else None,
            cost_basis=CostBasis.KNOWN if total_cost is not None else CostBasis.UNKNOWN,
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            duration_ms=data.get("duration_ms"),
            model_reported=_pick_model_reported(model_usage, model),
        )

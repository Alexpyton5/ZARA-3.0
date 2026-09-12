"""ClaudeCliAdapter.complete() failure classification (BUG 2026-09-11).

Real mission observed: when the Claude Code CLI's monthly quota ran out, this
CLI process exits non-zero *while still printing a full JSON envelope*
(`{"is_error": true, "result": "<the actual reason>", ...}`). The adapter's
old branch order checked `proc.returncode != 0` before ever looking at the
parsed envelope, so it classified the failure from a 300-character slice of
raw stdout/stderr instead of `data["result"]` — for a large envelope, the
real reason lives well past character 300 (it comes after `type`, `subtype`,
`session_id`, etc in the JSON), so the Lab recorded a generic `ERROR` with no
usable reason instead of `QUOTA_EXHAUSTED`.

Everything here is offline: `subprocess.run` and `shutil.which` are replaced
with fakes, so no real `claude` process is ever spawned. No test touches
`ZARA3_HOME` state beyond what `tests/conftest.py` already isolates for every
test in this suite.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from core.lab_v1.domain import Availability
from core.lab_v1.providers import claude_cli as claude_cli_module
from core.lab_v1.providers.claude_cli import ClaudeCliAdapter


@pytest.fixture
def adapter(monkeypatch):
    """Adapter with a fake CLI path, so `complete()` gets past the OFFLINE guard."""
    monkeypatch.setattr(claude_cli_module.shutil, "which", lambda name: "C:/fake/claude.exe")
    return ClaudeCliAdapter()


def _fake_completed_process(*, returncode: int, stdout: str, stderr: str = ""):
    return subprocess.CompletedProcess(args=["claude"], returncode=returncode, stdout=stdout, stderr=stderr)


def _run_with_stdout(monkeypatch, adapter, *, returncode: int, stdout_obj: dict | None, raw_stdout: str | None = None, stderr: str = ""):
    """Run `complete()` with `subprocess.run` faked to return the given envelope.

    `stdout_obj` is JSON-encoded automatically; pass `raw_stdout` instead to
    hand over stdout text that is not valid JSON (crash-before-printing case).
    """
    stdout = raw_stdout if raw_stdout is not None else json.dumps(stdout_obj)

    def fake_run(args, **kwargs):
        return _fake_completed_process(returncode=returncode, stdout=stdout, stderr=stderr)

    monkeypatch.setattr(claude_cli_module.subprocess, "run", fake_run)
    return adapter.complete(prompt="oi", model="sonnet")


# ---------------------------------------------------------------------------
# 1. Quota exhausted -> QUOTA_EXHAUSTED, not generic ERROR
# ---------------------------------------------------------------------------
def test_quota_exhausted_envelope_is_classified_as_quota(monkeypatch, adapter):
    envelope = {
        "type": "result",
        "subtype": "error",
        "is_error": True,
        "result": "Voce atingiu a quota mensal do plano Claude. Tente novamente apos o reset.",
        "session_id": "sess-quota",
    }
    result = _run_with_stdout(monkeypatch, adapter, returncode=1, stdout_obj=envelope)

    assert result.ok is False
    assert result.availability is Availability.QUOTA_EXHAUSTED
    assert "quota mensal" in result.error


# ---------------------------------------------------------------------------
# 2. Rate limit -> RATE_LIMITED, with any retry hint text preserved verbatim
# ---------------------------------------------------------------------------
def test_rate_limit_envelope_is_classified_as_rate_limited_and_keeps_retry_hint(monkeypatch, adapter):
    envelope = {
        "type": "result",
        "is_error": True,
        "result": "Erro 429: rate limit atingido. retry-after: 30s.",
        "session_id": "sess-rate",
    }
    result = _run_with_stdout(monkeypatch, adapter, returncode=1, stdout_obj=envelope)

    assert result.ok is False
    assert result.availability is Availability.RATE_LIMITED
    # KNOWN LIMITATION (see report): ProviderResult has no dedicated
    # `retry_after` field yet, so the adapter's only way to "propagate" a
    # provider-supplied retry hint today is to keep it, whole, inside
    # `error` instead of truncating it away. This asserts that much.
    assert "retry-after: 30s" in result.error


# ---------------------------------------------------------------------------
# 3. Auth required -> AUTH_REQUIRED
# ---------------------------------------------------------------------------
def test_auth_error_envelope_is_classified_as_auth_required(monkeypatch, adapter):
    envelope = {
        "type": "result",
        "is_error": True,
        "result": "Not logged in. Please run '/login' to continue.",
        "session_id": None,
    }
    result = _run_with_stdout(monkeypatch, adapter, returncode=1, stdout_obj=envelope)

    assert result.ok is False
    assert result.availability is Availability.AUTH_REQUIRED
    assert "Please run" in result.error


# ---------------------------------------------------------------------------
# 4. Genuinely unknown reason -> PROVIDER_ERROR, real message preserved (not
#    invented, not truncated)
# ---------------------------------------------------------------------------
def test_unrecognized_error_envelope_is_provider_error_with_real_message_kept(monkeypatch, adapter):
    real_message = (
        "Falha interna inesperada no adaptador X-7 durante o passo de "
        "validacao do plano; nenhuma categoria conhecida se aplica aqui."
    )
    envelope = {
        "type": "result",
        "is_error": True,
        "result": real_message,
        "session_id": "sess-unknown",
    }
    result = _run_with_stdout(monkeypatch, adapter, returncode=1, stdout_obj=envelope)

    assert result.ok is False
    assert result.availability is Availability.PROVIDER_ERROR
    assert result.error == real_message  # preserved exactly, not truncated/rewritten


# ---------------------------------------------------------------------------
# 5. Success continues to work (non-regression)
# ---------------------------------------------------------------------------
def test_success_envelope_still_returns_ok_result(monkeypatch, adapter):
    envelope = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "result": "Hello world",
        "session_id": "sess-ok",
        "usage": {"input_tokens": 10, "output_tokens": 5},
        "modelUsage": {
            "claude-sonnet-4-5-20250101": {
                "canonicalModel": "claude-sonnet-4-5",
                "costUSD": 0.01,
                "inputTokens": 10,
                "outputTokens": 5,
            }
        },
        "total_cost_usd": 0.01,
        "duration_ms": 1200,
    }
    result = _run_with_stdout(monkeypatch, adapter, returncode=0, stdout_obj=envelope)

    assert result.ok is True
    assert result.text == "Hello world"
    assert result.availability is Availability.AVAILABLE
    assert result.error is None
    assert result.provider_session_id == "sess-ok"
    assert result.cost_usd == 0.01
    assert result.model_reported == "claude-sonnet-4-5"


# ---------------------------------------------------------------------------
# 6. THE bug: real reason sits past character 300 of the raw JSON text.
#    Proves classification now reads the parsed envelope's `result` field,
#    not a character slice of raw stdout.
# ---------------------------------------------------------------------------
def test_large_envelope_finds_real_reason_past_300_raw_chars(monkeypatch, adapter):
    padding = "x" * 500  # pushes "result" well past raw-text offset 300
    envelope = {
        "type": "result",
        "subtype": "error",
        "is_error": True,
        "unrelated_metadata": padding,
        "result": "Voce atingiu a quota mensal do plano Claude. Tente novamente apos o reset.",
        "session_id": "sess-big",
    }
    raw_stdout = json.dumps(envelope)
    # Sanity check on the fixture itself: the real reason must not be
    # reachable from a naive [:300] slice of the raw envelope, otherwise this
    # test would not actually exercise the bug.
    assert "quota mensal" not in raw_stdout[:300]

    result = _run_with_stdout(monkeypatch, adapter, returncode=1, stdout_obj=None, raw_stdout=raw_stdout)

    assert result.ok is False
    assert result.availability is Availability.QUOTA_EXHAUSTED
    assert "quota mensal" in result.error

"""OpenCode catalog ownership and probe evidence boundaries."""
from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

from core.lab_v1.domain import Availability
from core.lab_v1.providers import opencode


def test_mixed_cli_catalog_only_exposes_opencode_namespace(monkeypatch, tmp_path):
    monkeypatch.setattr(opencode, "_OPENCODE_CLI", "opencode")
    monkeypatch.setattr(opencode.subprocess, "run", lambda *a, **kw: SimpleNamespace(
        returncode=0, stdout="opencode/free-one\nnvidia/nemotron\nopenai/gpt\nopencode/nvidia/nemotron\n", stderr=""))
    item = opencode.OpenCodeAdapter(cache_path=str(tmp_path / "models.json"))
    item.discover_models()
    assert [m.model_id for m in item.declared_models] == ["opencode/free-one"]
    assert list(json.loads((tmp_path / "models.json").read_text())) == ["opencode/free-one"]
    info = item.probe()
    assert info.availability is Availability.UNKNOWN
    assert info.installed is True and info.authenticated is None
    assert item._normalize_model_id("nvidia/nemotron") is None
    assert item._normalize_model_id("opencode/nvidia/nemotron") is None


def test_stale_mixed_cache_does_not_claim_live_access(monkeypatch, tmp_path):
    cache = tmp_path / "models.json"
    cache.write_text(json.dumps({"opencode/free-one": {"id": "opencode/free-one"},
                                 "nvidia/nemotron": {"id": "nvidia/nemotron"}}))
    monkeypatch.setattr(opencode, "_OPENCODE_CLI", None)
    item = opencode.OpenCodeAdapter(cache_path=str(cache))
    assert [m.model_id for m in item.declared_models] == ["opencode/free-one"]
    info = item.probe()
    assert info.availability is Availability.OFFLINE
    assert info.authenticated is None


def test_json_catalog_does_not_relabel_other_providers(monkeypatch, tmp_path):
    monkeypatch.setattr(opencode, "_OPENCODE_CLI", "opencode")
    monkeypatch.setattr(opencode.subprocess, "run", lambda *a, **kw: SimpleNamespace(
        returncode=0, stdout=json.dumps([{"id": "nvidia/nemotron"},
                                         {"id": "opencode/free-one"}]), stderr=""))
    item = opencode.OpenCodeAdapter(cache_path=str(tmp_path / "models.json"))
    item.discover_models()
    assert [m.model_id for m in item.declared_models] == ["opencode/free-one"]


def test_successful_inference_temporarily_verifies_provider(monkeypatch, tmp_path):
    monkeypatch.setattr(opencode, "_OPENCODE_CLI", "opencode")
    item = opencode.OpenCodeAdapter(cache_path=str(tmp_path / "models.json"))
    item._catalog = {"opencode/free-one": {"id": "opencode/free-one"}}
    monkeypatch.setattr(item, "_call_opencode_cli", lambda *a: {"text": "OK"})
    assert item.probe().availability is Availability.UNKNOWN
    result = item.complete(prompt="Reply exactly OK", model="opencode/free-one")
    assert result.ok and result.duration_ms >= 0
    assert item.probe().availability is Availability.AVAILABLE
    item._last_success_at -= 301
    assert item.probe().availability is Availability.UNKNOWN


def test_read_only_probe_never_starts_cli_and_explicit_refresh_has_own_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(opencode, "_OPENCODE_CLI", "opencode")
    timeouts = []

    def slow_catalog(*args, **kwargs):
        timeouts.append(kwargs["timeout"])
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(opencode.subprocess, "run", slow_catalog)
    item = opencode.OpenCodeAdapter(cache_path=str(tmp_path / "models.json"))
    assert timeouts == []
    assert item.probe().availability is Availability.UNKNOWN
    assert item.probe().availability is Availability.UNKNOWN
    assert timeouts == []
    assert item.discover_models(timeout_s=15) == []
    assert timeouts == [15]

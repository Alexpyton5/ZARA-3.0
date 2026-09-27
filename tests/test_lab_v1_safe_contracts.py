from __future__ import annotations

import pytest

from core.lab_v1.research_pipeline import (
    EvidenceReceipt,
    ObsidianContractError,
    ResearchSummary,
    URLContractError,
    URLReference,
    publish_summary_to_obsidian,
)
from core.lab_v1.skill_lifecycle import (
    DangerousActivationDenied,
    LifecycleTransitionDenied,
    RollbackUnavailable,
    SkillLifecycle,
)
from core.lab_v1.skill_registry import SkillRegistry


class MemorySink:
    def __init__(self):
        self.calls = []

    def add_memory(self, title, content, tags=None, category="memories"):
        self.calls.append((title, content, tags, category))
        return "node-1"


class Router:
    def authorize(self, **kwargs):
        return {"allowed": True, "action": kwargs["action"]}


def manifest(skill_id, version, permissions=("metadata.inspect",)):
    return {
        "skill_id": skill_id,
        "version": version,
        "permissions": list(permissions),
        "checksum": "0" * 64,
        "name": skill_id,
    }


def test_url_evidence_summary_and_obsidian_are_offline_and_provenance_bound():
    ref = URLReference.capture("HTTPS://Example.com:443/research?q=1", title="Example")
    assert ref.url == "https://example.com/research?q=1"
    receipt = EvidenceReceipt.create(ref, claim="A bounded claim", support="A source-supported statement")
    summary = ResearchSummary.create(
        "What is the claim?", [receipt], summary="A concise evidence-backed summary", limitations=["No fetch performed"]
    )
    sink = MemorySink()
    result = publish_summary_to_obsidian(summary, sink)
    assert result == {"summary_id": summary.summary_id, "obsidian_id": "node-1", "published": True}
    assert sink.calls[0][3] == "knowledge"
    assert receipt.evidence_id in sink.calls[0][1]


def test_url_contract_rejects_local_credentials_and_fragments():
    for value in ("http://127.0.0.1/admin", "https://user:pass@example.com", "https://example.com/a#fragment"):
        with pytest.raises(URLContractError):
            URLReference.capture(value)


def test_summary_requires_evidence_and_obsidian_requires_sink():
    with pytest.raises(ValueError):
        ResearchSummary.create("question", [], summary="summary")
    ref = URLReference.capture("https://example.com")
    evidence = EvidenceReceipt.create(ref, claim="claim", support="support")
    summary = ResearchSummary.create("question", [evidence], summary="summary")
    with pytest.raises(ObsidianContractError):
        publish_summary_to_obsidian(summary, object())


def test_lifecycle_requires_ordered_gates_and_rolls_back_known_good_version():
    lifecycle = SkillLifecycle(SkillRegistry())
    first = lifecycle.register(manifest("demo", "1.0.0"))
    evidence = lifecycle.record_evidence("demo", "1.0.0", {"evidence_id": "ev-1", "kind": "test", "summary": "safe"}, sync_obsidian=False)
    lifecycle.record_test_result("demo", "1.0.0", "test-1", passed=True, summary="pass", evidence_ids=[evidence["evidence_id"]], sync_obsidian=False)
    lifecycle.transition("demo", "1.0.0", "TESTING", actor="tester", sync_obsidian=False)
    lifecycle.transition("demo", "1.0.0", "READY", actor="tester", sync_obsidian=False)
    lifecycle.activate("demo", "1.0.0", owner_approved=True, router=Router(), sync_obsidian=False)

    second = lifecycle.register(manifest("demo", "2.0.0", ("metadata.inspect", "filesystem.write")))
    ev2 = lifecycle.record_evidence("demo", "2.0.0", {"evidence_id": "ev-2", "kind": "test", "summary": "safe"}, sync_obsidian=False)
    lifecycle.record_test_result("demo", "2.0.0", "test-2", passed=True, summary="pass", evidence_ids=[ev2["evidence_id"]], sync_obsidian=False)
    lifecycle.transition("demo", "2.0.0", "TESTING", actor="tester", sync_obsidian=False)
    lifecycle.transition("demo", "2.0.0", "READY", actor="tester", sync_obsidian=False)
    with pytest.raises(DangerousActivationDenied):
        lifecycle.activate("demo", "2.0.0", owner_approved=True, router=Router(), sync_obsidian=False)
    lifecycle.activate("demo", "2.0.0", owner_approved=True, dangerous_approved=True, router=Router(), sync_obsidian=False)

    restored = lifecycle.rollback("demo", owner_approved=True, router=Router(), target_version="1.0.0", sync_obsidian=False)
    assert restored["status"] == "ACTIVE"
    assert lifecycle.snapshot("demo", "1.0.0")["active"] is True
    assert lifecycle.snapshot("demo", "2.0.0")["manifest"]["status"] == "RETIRED"


def test_autoactivation_and_invalid_rollback_stay_fail_closed():
    lifecycle = SkillLifecycle(SkillRegistry())
    lifecycle.register(manifest("demo", "1.0.0"))
    with pytest.raises(LifecycleTransitionDenied):
        lifecycle.auto_activate("demo", "1.0.0")
    with pytest.raises(RollbackUnavailable):
        lifecycle.rollback("demo", owner_approved=True, router=Router(), sync_obsidian=False)

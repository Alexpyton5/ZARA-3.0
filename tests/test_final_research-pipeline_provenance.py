from __future__ import annotations

import pytest

from core.lab_v1.research_pipeline import (
    EvidenceReceipt,
    ResearchPipeline,
    URLContractError,
    URLReference,
    _validate_source,
)
from core.lab_v1.scout import _source_url
from core.lab_v1.store import LabStore


SOURCE = {
    "source": "https://github.com/openai/codex/releases/tag/v1",
    "finding": "The release documents a bounded change.",
    "evidence": "fix agent api",
    "relevance": "It is relevant to the Lab research question.",
    "limitation": "This is release-note evidence only.",
    "source_access": {"status": "READ", "retrieved_at": "2026-09-20T09:00:00+00:00"},
    "read_evidence": {"status": "READ", "excerpt": "fix agent api"},
    "provenance": {"researcher": "scout", "method": "feed"},
    "finding_validation": {"status": "VALIDATED", "validator": "reviewer"},
    "memory": {"reusable": True, "lesson": "Recheck release notes before implementation."},
}


@pytest.fixture
def pipeline(tmp_path):
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    return ResearchPipeline(store)


def test_fictitious_url_fails_for_pipeline_and_contract():
    bad = {**SOURCE, "source": "https://example.com/fake-release"}
    with pytest.raises(ValueError, match="SOURCE_URL_FICTITIOUS|URL_LOCAL_HOST_NOT_ALLOWED"):
        _validate_source(bad)
    with pytest.raises(URLContractError, match="URL_LOCAL_HOST_NOT_ALLOWED"):
        URLReference.capture("https://example.org/not-real")
    with pytest.raises(ValueError, match="SOURCE_URL_FICTITIOUS"):
        _source_url("https://untrusted.invalid/release")


def test_cycle_persists_audit_fields_and_deduplicates_by_question_identity(pipeline):
    first = pipeline.record_cycle(
        "What changed in the release?",
        [SOURCE],
        recommendation="precisa_mais_investigacao",
        question_identity="release-question-v1",
        cycle_id="cycle:one",
        evidence_valid_until="2026-10-01T00:00:00+00:00",
        provenance={"run_id": "run-1", "source_access": "scout"},
        finding_validation={"status": "VALIDATED", "validator": "reviewer"},
        memory={"reusable": True, "lesson": "recheck"},
    )
    assert first["question_identity"] == "release-question-v1"
    assert first["cycle_id"] == "cycle:one"
    assert first["evidence_valid_until"].startswith("2026-10-01")
    assert first["sources"][0]["source_access"]["status"] == "READ"
    assert first["sources"][0]["read_evidence"]["excerpt"] == "fix agent api"
    assert first["sources"][0]["provenance"]["researcher"] == "scout"
    assert first["sources"][0]["finding_validation"]["status"] == "VALIDATED"
    assert first["sources"][0]["memory"]["reusable"] is True

    duplicate = pipeline.record_cycle(
        "A different wording",
        [SOURCE],
        recommendation="nao_implementar",
        question_identity="release-question-v1",
    )
    assert duplicate["cycle_id"] == "cycle:one"
    assert len(pipeline.list_cycles()) == 1


def test_refresh_creates_child_with_parent_and_reason(pipeline):
    parent = pipeline.record_cycle(
        "Is the release useful?", [SOURCE], recommendation="precisa_mais_investigacao",
        question_identity="usefulness-v1", cycle_id="cycle:parent",
    )
    child = pipeline.record_cycle(
        "Is the release useful?", [SOURCE], recommendation="nao_implementar",
        question_identity="usefulness-v1", refresh_reason="evidence expired",
        evidence_valid_until="2026-11-01T00:00:00+00:00",
    )
    assert child["cycle_id"] != parent["cycle_id"]
    assert child["parent_cycle"] == "cycle:parent"
    assert child["refresh_reason"] == "evidence expired"
    assert pipeline.get_cycle("Is the release useful?")["cycle_id"] == child["cycle_id"]
    assert len(pipeline.list_cycles()) == 2


def test_evidence_receipt_contract_rejects_fictitious_source():
    with pytest.raises(URLContractError, match="URL_LOCAL_HOST_NOT_ALLOWED"):
        EvidenceReceipt.create("https://invalid/fake", claim="claim", support="quote")


def test_scout_public_url_canonicalization():
    assert _source_url("HTTPS://github.com/openai/codex/releases/tag/v1#fragment") == (
        "https://github.com/openai/codex/releases/tag/v1"
    )

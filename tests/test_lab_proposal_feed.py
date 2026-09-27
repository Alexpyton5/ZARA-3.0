"""Tests for the independent Lab proposal feed store."""

from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from core.lab_v1.proposal_feed import (
    InvalidProposalState,
    PROPOSAL_STATES,
    ProposalFeedStore,
    ProposalState,
)


def test_register_list_and_update_are_json_safe(tmp_path):
    store = ProposalFeedStore(tmp_path / "proposals.sqlite3")

    proposal = store.register_proposal(
        "proposal-1",
        title="Local-first feed",
        description="Keep proposals available without a provider.",
        evidence_refs=["test://design", {"kind": "note", "id": 7}],
        metadata={"priority": 2, "reviewed_at": datetime(2026, 1, 2, tzinfo=timezone.utc)},
    )

    assert proposal["proposal_id"] == "proposal-1"
    assert proposal["state"] == ProposalState.PROPOSED.value
    assert proposal["evidence_refs"] == [
        "test://design",
        {"kind": "note", "id": 7},
    ]
    assert proposal["priority"] == 2
    assert proposal["reviewed_at"] == "2026-01-02T00:00:00+00:00"
    json.dumps(proposal)

    listed = store.list_proposals()
    assert listed == [proposal]

    updated = store.update_state("proposal-1", ProposalState.DISCUSSING)
    assert updated is not None
    assert updated["state"] == "DISCUSSING"
    assert updated["created_at"] == proposal["created_at"]
    assert updated["updated_at"] >= proposal["updated_at"]
    json.dumps(updated)


def test_registration_is_deduplicated_by_proposal_id_and_persists(tmp_path):
    db_path = tmp_path / "persistent-feed.sqlite3"
    first_store = ProposalFeedStore(db_path)
    first = first_store.register_proposal(
        "same-id",
        title="Original",
        description="Original description",
        evidence_refs=["evidence-1"],
    )
    transitioned = first_store.update_state("same-id", "CANDIDATE")
    assert transitioned is not None

    duplicate = first_store.register_proposal(
        "same-id",
        title="Should not replace",
        description="Should not replace",
        state="APPROVED",
        evidence_refs=["evidence-2"],
    )
    assert duplicate == transitioned
    assert first_store.count() == 1

    second_store = ProposalFeedStore(db_path)
    persisted = second_store.get_proposal("same-id")
    assert persisted == transitioned
    assert second_store.list_proposals("CANDIDATE") == [transitioned]
    assert second_store.list_proposals("APPROVED") == []


def test_all_supported_states_are_accepted():
    store = ProposalFeedStore()
    assert PROPOSAL_STATES == (
        "PROPOSED",
        "DISCUSSING",
        "CANDIDATE",
        "TESTED",
        "APPROVAL_REQUIRED",
        "APPROVED",
        "REJECTED",
        "ACTIVATED",
    )

    store.register_proposal("stateful")
    for state in PROPOSAL_STATES[1:]:
        proposal = store.update_state("stateful", state)
        assert proposal is not None
        assert proposal["state"] == state


def test_mapping_registration_and_unknown_updates_are_safe():
    store = ProposalFeedStore()
    proposal = store.register_proposal(
        {
            "proposal_id": "mapping-id",
            "title": "Mapping input",
            "summary": "A compact proposal.",
            "state": ProposalState.TESTED,
            "evidence_refs": ("a", "b"),
            "owner": "lab",
        }
    )

    assert proposal["description"] == "A compact proposal."
    assert proposal["state"] == "TESTED"
    assert proposal["evidence_refs"] == ["a", "b"]
    assert proposal["summary"] == "A compact proposal."
    assert proposal["owner"] == "lab"
    assert store.update_state("missing", "APPROVED") is None
    assert store.get_proposal("missing") is None


def test_invalid_inputs_are_rejected():
    store = ProposalFeedStore()

    with pytest.raises(InvalidProposalState):
        store.register_proposal("bad-state", state="UNKNOWN")
    with pytest.raises(InvalidProposalState):
        store.list_proposals("UNKNOWN")
    with pytest.raises(InvalidProposalState):
        store.update_state("missing", "UNKNOWN")
    with pytest.raises(ValueError):
        store.register_proposal(" ")
    with pytest.raises(ValueError):
        store.list_proposals(limit=-1)


def test_connect_is_available_and_returns_a_sqlite_connection():
    store = ProposalFeedStore()
    connection = store._connect()
    try:
        assert connection.execute("SELECT 1").fetchone()[0] == 1
    finally:
        # In-memory stores retain their connection for the store lifetime.
        store.close()

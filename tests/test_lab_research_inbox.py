"""Tests for the independent Lab research discovery inbox."""
from __future__ import annotations

from datetime import datetime, timezone
import json

import pytest

from core.lab_v1.research_inbox import (
    DEFAULT_EXCERPT_LIMIT,
    ExcerptTooLong,
    InvalidResearchStatus,
    InvalidSourceURL,
    RESEARCH_STATUSES,
    ResearchInboxStore,
    ResearchStatus,
)


def test_add_returns_complete_json_safe_new_record():
    store = ResearchInboxStore()
    item = store.add(
        source_url="https://example.test/paper",
        title="A local-first discovery",
        excerpt="A short excerpt.",
        captured_at=datetime(2026, 1, 2, 3, 4, tzinfo=timezone.utc),
        researcher="lab",
        relevance=0.9,
        evidence_hash="sha256:one",
    )

    assert item == {
        "source_url": "https://example.test/paper",
        "title": "A local-first discovery",
        "excerpt": "A short excerpt.",
        "captured_at": "2026-01-02T03:04:00+00:00",
        "researcher": "lab",
        "relevance": 0.9,
        "evidence_hash": "sha256:one",
        "status": "NEW",
    }
    json.dumps(item)
    assert store.count() == 1
    assert store.get("https://example.test/paper") == item


def test_mapping_input_generates_captured_at_and_evidence_hash():
    store = ResearchInboxStore()
    item = store.add(
        {
            "source_url": "http://example.test/discovery",
            "title": "Generated provenance",
            "excerpt": "Captured locally.",
            "researcher": "analyst",
            "relevance": 1,
        }
    )

    assert item["status"] == ResearchStatus.NEW.value
    assert item["captured_at"].endswith("+00:00")
    assert len(item["evidence_hash"]) == 64
    assert int(item["relevance"]) == 1
    assert store.get_by_hash(item["evidence_hash"]) == item


def test_url_and_hash_duplicates_are_idempotent_and_preserve_original():
    store = ResearchInboxStore()
    original = store.add(
        "https://example.test/same",
        title="Original",
        excerpt="Original excerpt",
        captured_at="2026-01-01T00:00:00+00:00",
        researcher="one",
        relevance=0.2,
        evidence_hash="same-hash",
    )

    duplicate_url = store.add(
        "https://example.test/same",
        title="Should not replace",
        excerpt="Changed",
        captured_at="2027-01-01T00:00:00+00:00",
        researcher="two",
        relevance=0.8,
        evidence_hash="different-hash",
    )
    duplicate_hash = store.add(
        "https://example.test/other",
        title="Should also not insert",
        excerpt="Changed",
        captured_at="2027-01-01T00:00:00+00:00",
        researcher="three",
        relevance=0.8,
        evidence_hash="same-hash",
    )

    assert duplicate_url == original
    assert duplicate_hash == original
    assert store.count() == 1


def test_only_http_and_https_urls_are_accepted():
    store = ResearchInboxStore()
    for url in (
        "",
        "   ",
        "ftp://example.test/file",
        "file:///tmp/evidence",
        "javascript:alert(1)",
        "https://",
        "https://example.test/path with spaces",
    ):
        with pytest.raises(InvalidSourceURL):
            store.add(url, title="x", excerpt="x")

    assert store.add("HTTP://example.test/ok", title="x", excerpt="x")["source_url"] == (
        "http://example.test/ok"
    )


def test_excerpt_limit_is_enforced_and_can_be_configured():
    store = ResearchInboxStore()
    with pytest.raises(ExcerptTooLong):
        store.add(
            "https://example.test/too-long",
            title="x",
            excerpt="x" * (DEFAULT_EXCERPT_LIMIT + 1),
        )

    custom = ResearchInboxStore(excerpt_limit=4)
    assert custom.add(
        "https://example.test/short",
        title="x",
        excerpt="four",
    )["excerpt"] == "four"
    with pytest.raises(ExcerptTooLong):
        custom.add("https://example.test/long", title="x", excerpt="five!")


def test_status_lifecycle_listing_and_unknown_update_are_safe():
    store = ResearchInboxStore()
    first = store.add("https://example.test/a", title="a", excerpt="a")
    second = store.add(
        "https://example.test/b",
        title="b",
        excerpt="b",
        status=ResearchStatus.REVIEWED,
    )

    assert RESEARCH_STATUSES == ("NEW", "REVIEWED", "REJECTED", "ADOPTED")
    for status in RESEARCH_STATUSES[1:]:
        updated = store.update_status(first["source_url"], status)
        assert updated is not None
        assert updated["status"] == status
    assert store.update_status("https://example.test/missing", "ADOPTED") is None
    assert store.list_items("ADOPTED") == [updated]
    assert store.list_items("REVIEWED") == [second]
    assert store.count("REJECTED") == 0
    with pytest.raises(InvalidResearchStatus):
        store.add("https://example.test/bad", title="x", excerpt="x", status="PENDING")
    with pytest.raises(InvalidResearchStatus):
        store.list_items("PENDING")


def test_file_backed_store_persists_without_external_services(tmp_path):
    db_path = tmp_path / "research-inbox.sqlite3"
    first_store = ResearchInboxStore(db_path)
    item = first_store.add(
        "https://example.test/persisted",
        title="Persisted",
        excerpt="Local only",
        evidence_hash="persisted-hash",
    )
    first_store.close()

    second_store = ResearchInboxStore(db_path)
    assert second_store.list_items() == [item]
    assert second_store.get_by_hash("persisted-hash") == item
    second_store.close()

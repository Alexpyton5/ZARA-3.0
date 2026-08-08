from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

import core.actions.web as web_actions
from core.action_registry import ActionResult, get_registry
from core.realtime_web import (
    RealtimeWebResearch,
    ResearchResult,
    SourceRecord,
    SQLiteWebCache,
    canonicalize_url,
    content_sha256,
)


def _result(
    *,
    success: bool = True,
    output: str = "",
    data: dict | None = None,
    error: str = "",
) -> ActionResult:
    return ActionResult(success=success, output=output, data=data, error=error)


def _source(*, retrieved_at: datetime, url: str = "https://example.com/article") -> SourceRecord:
    content = "verified source body"
    return SourceRecord(
        citation_number=0,
        url=url,
        canonical_url=canonicalize_url(url),
        title="Source",
        content=content,
        content_hash=content_sha256(content),
        retrieved_at=retrieved_at,
    )


def test_source_requires_aware_utc_retrieval_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        _source(retrieved_at=datetime(2026, 8, 8, 12, 0))

    offset_time = datetime.fromisoformat("2026-08-08T09:00:00-03:00")
    source = _source(retrieved_at=offset_time)

    assert source.retrieved_at == datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    assert source.retrieved_at.tzinfo is UTC


def test_canonical_url_removes_tracking_fragment_and_normalizes_query() -> None:
    canonical = canonicalize_url(
        " HTTPS://Example.COM.:443/a%20b?utm_source=test&b=2&a=1&fbclid=x#fragment "
    )

    assert canonical == "https://example.com/a%20b?a=1&b=2"


def test_sqlite_cache_is_injectable_and_obeys_ttl() -> None:
    connection = sqlite3.connect(":memory:")
    cache = SQLiteWebCache(connection, ttl_seconds=60)
    retrieved_at = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    source = _source(retrieved_at=retrieved_at)
    cache.put(source)

    fresh = cache.lookup(source.url, now=retrieved_at + timedelta(seconds=59))
    stale = cache.lookup(source.url, now=retrieved_at + timedelta(seconds=61))

    assert fresh is not None and fresh.is_fresh is True
    assert fresh.record.from_cache is True
    assert stale is not None and stale.is_fresh is False
    assert stale.age_seconds == 61

    cache.close()
    assert connection.execute("SELECT COUNT(*) FROM realtime_web_cache").fetchone()[0] == 1


def test_research_revalidates_stale_cache_with_http_validators() -> None:
    current_time = [datetime(2026, 8, 8, 12, 0, tzinfo=UTC)]
    fetch_calls: list[dict | None] = []

    def search(_query: str, **_kwargs) -> ActionResult:
        return _result(
            data={
                "results": [
                    {
                        "url": "https://example.com/news",
                        "title": "Current report",
                        "snippet": "A summary",
                    }
                ]
            }
        )

    def fetch(url: str, *, headers: dict | None = None) -> ActionResult:
        fetch_calls.append(headers)
        if len(fetch_calls) == 1:
            return _result(
                output="original body",
                data={
                    "url": url,
                    "status": 200,
                    "headers": {
                        "ETag": '"revision-1"',
                        "Last-Modified": "Fri, 08 Aug 2026 11:00:00 GMT",
                        "Date": "Fri, 08 Aug 2026 12:00:00 GMT",
                    },
                },
            )
        return _result(
            data={
                "url": url,
                "status": 304,
                "headers": {"ETag": '"revision-1"'},
            }
        )

    cache = SQLiteWebCache(ttl_seconds=60)
    researcher = RealtimeWebResearch(
        search_action=search,
        fetch_action=fetch,
        cache=cache,
        clock=lambda: current_time[0],
    )

    first = researcher.research("zara current state")
    current_time[0] += timedelta(seconds=30)
    fresh = researcher.research("zara current state")
    current_time[0] += timedelta(seconds=31)
    revalidated = researcher.research("zara current state")

    assert len(fetch_calls) == 2
    assert fetch_calls[0] is None
    assert fetch_calls[1] == {
        "If-None-Match": '"revision-1"',
        "If-Modified-Since": "Fri, 08 Aug 2026 11:00:00 GMT",
    }
    assert first.sources[0].from_cache is False
    assert fresh.sources[0].from_cache is True
    assert revalidated.sources[0].content == "original body"
    assert revalidated.sources[0].retrieved_at == current_time[0]
    # Date and Last-Modified are cache validators, never publication evidence.
    assert revalidated.sources[0].published_at is None


def test_research_deduplicates_canonical_urls_and_content_hashes() -> None:
    fetched: list[str] = []
    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)

    def search(_query: str, **_kwargs) -> ActionResult:
        return _result(
            data={
                "results": [
                    {"url": "https://EXAMPLE.com/a?utm_source=x", "title": "A"},
                    {"url": "https://example.com/a", "title": "A duplicate"},
                    {"url": "https://example.org/copy", "title": "Content duplicate"},
                    {
                        "url": "https://example.net/unique",
                        "title": "Unique",
                        "published_at": "2026-08-08T10:00:00Z",
                    },
                ]
            }
        )

    def fetch(url: str, *, headers: dict | None = None) -> ActionResult:
        assert headers is None
        fetched.append(url)
        body = "same body" if "unique" not in url else "different body"
        return _result(output=body, data={"url": url, "status": 200, "headers": {}})

    result = RealtimeWebResearch(
        search_action=search,
        fetch_action=fetch,
        cache=SQLiteWebCache(),
        clock=lambda: now,
    ).research("deduplication", max_results=10)

    assert fetched == [
        "https://example.com/a",
        "https://example.org/copy",
        "https://example.net/unique",
    ]
    assert [source.citation for source in result.sources] == ["[1]", "[2]"]
    assert [source.title for source in result.sources] == ["A", "Unique"]
    assert result.sources[0].published_at is None
    assert result.sources[1].published_at == datetime(2026, 8, 8, 10, 0, tzinfo=UTC)
    assert result.verify_citations() is True
    assert result.verify_citation(
        1,
        url="https://example.com/a?utm_campaign=ignored",
        content_hash=content_sha256("same body"),
    )


def test_web_research_action_is_read_only_and_returns_numbered_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
    cited = _source(retrieved_at=now)
    expected = ResearchResult(
        query="current facts",
        sources=(replace(cited, citation_number=1),),
        retrieved_at=now,
    )

    class FakeResearcher:
        def research(self, query: str, **_kwargs) -> ResearchResult:
            assert query == "current facts"
            return expected

    monkeypatch.setattr(web_actions, "_get_realtime_researcher", lambda: FakeResearcher())

    action_result = web_actions.web_research_action("current facts")
    spec = get_registry().get_spec("web_research")

    assert action_result.success is True
    assert action_result.data["citations"][0]["marker"] == "[1]"
    assert json.loads(action_result.output)["sources"][0]["citation"] == "[1]"
    assert "content" not in json.loads(action_result.output)["sources"][0]
    assert spec is not None
    assert spec.risk == "LOW"
    assert spec.capability == "READ_ONLY"


def test_web_fetch_exposes_not_modified_for_cache_revalidation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status_code = 304
        url = "https://example.com/news"
        headers = {"etag": '"revision-1"'}
        encoding = "utf-8"

        def iter_bytes(self):
            return iter(())

        def raise_for_status(self) -> None:
            raise AssertionError("304 must not be raised as an action failure")

    class FakeStream:
        def __enter__(self) -> FakeResponse:
            return FakeResponse()

        def __exit__(self, _exc_type, _exc, _traceback) -> None:
            return None

    monkeypatch.setattr(web_actions, "_public_stream", lambda *_args, **_kwargs: FakeStream())
    monkeypatch.setattr(web_actions.httpx, "Client", lambda **_kwargs: FakeStream())

    result = web_actions.web_fetch_action(
        "https://example.com/news",
        headers={"If-None-Match": '"revision-1"'},
    )

    assert result.success is True
    assert result.output == ""
    assert result.data["status"] == 304
    assert result.data["headers"]["etag"] == '"revision-1"'

"""
Web Action — Web search and HTTP requests.
"""
from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from urllib.parse import parse_qs, urljoin, urlsplit

import httpx

from core.action_registry import ActionResult, action, get_registry
from core.paths import data_dir
from core.realtime_web import RealtimeWebResearch, SQLiteWebCache
from core.url_security import (
    URLSecurityError,
    validate_connected_peer,
    validate_public_http_url,
)

# DuckDuckGo HTML scraping (no API key needed)
DDG_HTML_URL = "https://html.duckduckgo.com/html/"
MAX_REDIRECTS = 5
MAX_FETCH_BYTES = 5 * 1024 * 1024
MAX_SEARCH_BYTES = 2 * 1024 * 1024
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_ALLOWED_FETCH_HEADERS = frozenset(
    {
        "accept",
        "accept-language",
        "cache-control",
        "if-modified-since",
        "if-none-match",
        "user-agent",
    }
)
_EXPOSED_RESPONSE_HEADERS = frozenset(
    {"cache-control", "content-length", "content-type", "date", "etag", "last-modified"}
)


def _sanitize_fetch_headers(headers: dict | None) -> dict[str, str]:
    safe: dict[str, str] = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    for raw_name, raw_value in (headers or {}).items():
        name = str(raw_name).strip()
        value = str(raw_value)
        if name.lower() not in _ALLOWED_FETCH_HEADERS:
            raise URLSecurityError(f"Request header is not allowed for read-only fetch: {name}")
        if not name or any(char in name + value for char in ("\r", "\n")):
            raise URLSecurityError("Request headers contain unsafe characters")
        safe[name] = value
    return safe


@contextmanager
def _public_stream(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    content: str | bytes | None = None,
    form_data: dict[str, str] | None = None,
    deadline: float | None = None,
) -> Iterator[httpx.Response]:
    """Open a streamed response while validating DNS, peers and every redirect."""

    current = validate_public_http_url(url)
    request_method = method.upper()
    request_content = content
    request_form = form_data

    for redirect_count in range(MAX_REDIRECTS + 1):
        timeout: float | None = None
        if deadline is not None:
            timeout = deadline - time.monotonic()
            if timeout <= 0:
                raise TimeoutError("Web request deadline reached")
        request_kwargs = {
            "headers": headers,
            "content": request_content,
            "data": request_form,
        }
        if timeout is not None:
            request_kwargs["timeout"] = timeout
        request = client.build_request(request_method, current.url, **request_kwargs)
        response = client.send(request, stream=True, follow_redirects=False)
        try:
            validate_connected_peer(response)
        except Exception:
            response.close()
            raise

        if response.status_code not in REDIRECT_STATUSES:
            try:
                yield response
            finally:
                response.close()
            return

        location = response.headers.get("location", "").strip()
        status_code = response.status_code
        response.close()
        if not location:
            raise URLSecurityError("Redirect response did not include a Location header")
        if redirect_count >= MAX_REDIRECTS:
            raise URLSecurityError(f"Too many redirects (maximum: {MAX_REDIRECTS})")

        # Resolve and validate each new target before the next network request.
        current = validate_public_http_url(urljoin(current.url, location))
        if status_code == 303 or (status_code in {301, 302} and request_method == "POST"):
            request_method = "GET"
            request_content = None
            request_form = None


def _read_limited_bytes(
    response: httpx.Response,
    limit: int,
    *,
    deadline: float | None = None,
) -> tuple[bytes, bool]:
    """Read at most ``limit`` bytes plus one sentinel byte from a stream."""

    if limit < 1:
        raise ValueError("Response byte limit must be positive")
    buffer = bytearray()
    sentinel_limit = limit + 1
    iterator = iter(response.iter_bytes())
    while True:
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("Web response deadline reached")
        try:
            chunk = next(iterator)
        except StopIteration:
            break
        if deadline is not None and time.monotonic() >= deadline:
            raise TimeoutError("Web response deadline reached")
        if not chunk:
            continue
        remaining = sentinel_limit - len(buffer)
        if remaining <= 0:
            break
        buffer.extend(chunk[:remaining])
        if len(buffer) >= sentinel_limit:
            break
    truncated = len(buffer) > limit
    return bytes(buffer[:limit]), truncated


def _public_response_headers(response: httpx.Response) -> dict[str, str]:
    return {
        name: value
        for name, value in response.headers.items()
        if name.lower() in _EXPOSED_RESPONSE_HEADERS
    }


def _normalize_ddg_result_url(href: str) -> str:
    """Resolve scheme-relative links and unwrap DuckDuckGo's ``uddg`` redirect."""

    resolved = urljoin(DDG_HTML_URL, str(href or "").strip())
    parts = urlsplit(resolved)
    host = (parts.hostname or "").casefold().rstrip(".")
    if host in {"duckduckgo.com", "www.duckduckgo.com", "html.duckduckgo.com"}:
        target = parse_qs(parts.query).get("uddg", [""])[0].strip()
        target_parts = urlsplit(target)
        if target_parts.scheme.casefold() in {"http", "https"} and target_parts.hostname:
            return target
    return resolved


@action(
    name="web_search",
    category="web",
    description="Search the web using DuckDuckGo (no API key required)",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Max results (default: 10)", "default": 10},
            "region": {"type": "string", "description": "Region code (default: wt-wt)", "default": "wt-wt"},
            "timeout": {
                "type": "number",
                "description": "Total search deadline in seconds",
                "default": 30,
                "minimum": 0.1,
                "maximum": 30,
            },
        },
        "required": ["query"],
    },
)
def web_search_action(
    query: str,
    max_results: int = 10,
    region: str = "wt-wt",
    timeout: float = 30,
) -> ActionResult:
    """Search web via DuckDuckGo HTML."""
    try:
        max_results = max(1, min(int(max_results), 50))
        params = {
            "q": query,
            "kl": region,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        safe_timeout = max(0.1, min(float(timeout), 30.0))
        deadline = time.monotonic() + safe_timeout

        with httpx.Client(timeout=safe_timeout, follow_redirects=False, trust_env=False) as client:
            with _public_stream(
                client,
                "POST",
                DDG_HTML_URL,
                headers=headers,
                form_data=params,
                deadline=deadline,
            ) as resp:
                resp.raise_for_status()
                raw_html, truncated = _read_limited_bytes(
                    resp,
                    MAX_SEARCH_BYTES,
                    deadline=deadline,
                )
                if truncated:
                    raise RuntimeError("Search response exceeded the safe size limit")
                html = raw_html.decode(resp.encoding or "utf-8", errors="replace")

        # Parse HTML results
        from html.parser import HTMLParser

        class DDGParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.results = []
                self._in_result = False
                self._in_title = False
                self._in_snippet = False
                self._current = {}

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                classes = set(attrs.get("class", "").split())
                if tag == "a" and "result__snippet" in classes:
                    self._in_snippet = True
                elif tag == "a" and classes.intersection({"result__a", "result__url"}):
                    self._in_title = True
                    self._current["url"] = _normalize_ddg_result_url(attrs.get("href", ""))
                elif tag == "div" and "result__snippet" in classes:
                    self._in_snippet = True

            def handle_endtag(self, tag):
                if tag == "a" and self._in_title:
                    self._in_title = False
                elif tag in ("a", "div") and self._in_snippet:
                    self._in_snippet = False

            def handle_data(self, data):
                data = data.strip()
                if not data:
                    return
                if self._in_title and "title" not in self._current:
                    self._current["title"] = data
                elif self._in_snippet:
                    self._current["snippet"] = data
                    if self._current.get("title") or self._current.get("url"):
                        self.results.append(self._current.copy())
                        self._current = {}

        parser = DDGParser()
        parser.feed(html)

        results = parser.results[:max_results]

        return ActionResult(
            success=True,
            output=json.dumps(results, indent=2, ensure_ascii=False),
            data={"results": results, "query": query, "count": len(results)}
        )

    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="web_fetch",
    category="web",
    description="Fetch a web page content",
    risk="LOW",
    capability="READ_ONLY",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "method": {"type": "string", "description": "Read-only HTTP method", "default": "GET", "enum": ["GET", "HEAD"]},
            "headers": {"type": "object", "description": "Safe read-only request headers"},
            "timeout": {"type": "number", "description": "Timeout in seconds (default: 30)", "default": 30},
            "max_size": {"type": "integer", "description": "Max response size in bytes (hard maximum: 5MB)", "default": 5242880, "minimum": 1, "maximum": 5242880},
        },
        "required": ["url"],
    },
)
def web_fetch_action(
    url: str,
    method: str = "GET",
    headers: dict = None,
    data: str = None,
    timeout: float = 30,
    max_size: int = 5242880,
) -> ActionResult:
    """Fetch a web page."""
    try:
        safe_method = str(method or "GET").upper()
        if safe_method not in {"GET", "HEAD"}:
            raise URLSecurityError("Read-only web_fetch allows only GET or HEAD")
        if data not in (None, "", b""):
            raise URLSecurityError("Read-only web_fetch does not accept a request body")
        safe_headers = _sanitize_fetch_headers(headers)
        safe_timeout = max(0.1, min(float(timeout), 120.0))
        safe_limit = max(1, min(int(max_size), MAX_FETCH_BYTES))
        deadline = time.monotonic() + safe_timeout

        with httpx.Client(timeout=safe_timeout, follow_redirects=False, trust_env=False) as client:
            with _public_stream(
                client,
                safe_method,
                url,
                headers=safe_headers,
                deadline=deadline,
            ) as resp:
                # A conditional cache revalidation returns no body by design.
                # Preserve its status and validators for the research layer.
                if resp.status_code != 304:
                    resp.raise_for_status()
                raw_content, truncated = _read_limited_bytes(
                    resp,
                    safe_limit,
                    deadline=deadline,
                )
                encoding = resp.encoding or "utf-8"
                content_text = raw_content.decode(encoding, errors="replace")
                if truncated:
                    content_text += "\n... [truncated]"

                response_data = {
                    "url": str(resp.url),
                    "status": resp.status_code,
                    "headers": _public_response_headers(resp),
                    "size": len(raw_content),
                    "truncated": truncated,
                }

        return ActionResult(
            success=True,
            output=content_text,
            data=response_data,
        )
    except Exception as e:
        return ActionResult(success=False, error=str(e))


_realtime_research_lock = threading.Lock()
_realtime_researcher: RealtimeWebResearch | None = None


def _get_realtime_researcher() -> RealtimeWebResearch:
    """Create the persistent default researcher only when the action is used."""

    global _realtime_researcher
    if _realtime_researcher is None:
        with _realtime_research_lock:
            if _realtime_researcher is None:
                cache = SQLiteWebCache(data_dir() / "realtime_web_cache.sqlite3")
                _realtime_researcher = RealtimeWebResearch(cache=cache)
    return _realtime_researcher


@action(
    name="web_research",
    category="web",
    description="Collect current web sources with cached, verifiable citations",
    risk="LOW",
    capability="READ_ONLY",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Research query"},
            "max_results": {
                "type": "integer",
                "description": "Maximum cited sources (default: 5)",
                "default": 5,
                "minimum": 1,
                "maximum": 10,
            },
            "region": {
                "type": "string",
                "description": "Search region code (default: wt-wt)",
                "default": "wt-wt",
            },
            "force_refresh": {
                "type": "boolean",
                "description": "Revalidate cached sources immediately",
                "default": False,
            },
        },
        "required": ["query"],
    },
)
def web_research_action(
    query: str,
    max_results: int = 5,
    region: str = "wt-wt",
    force_refresh: bool = False,
) -> ActionResult:
    """Collect live sources without generating or inferring an answer."""

    try:
        result = _get_realtime_researcher().research(
            query,
            max_results=max_results,
            region=region,
            force_refresh=force_refresh,
        )
        # IPC receives provenance and hashes, not up to megabytes of raw pages.
        payload = result.to_dict(include_content=False)
        return ActionResult(
            success=True,
            output=result.to_json(include_content=False),
            data=payload,
        )
    except Exception as exc:
        return ActionResult(success=False, error=str(exc))


@action(
    name="web_download",
    category="web",
    description="Download a file from URL",
    risk="MEDIUM",
    capability="FILES_MUTATE",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to download"},
            "dest": {"type": "string", "description": "Destination path"},
            "overwrite": {"type": "boolean", "description": "Overwrite if exists (default: true)", "default": True},
        },
        "required": ["url", "dest"],
    },
)
def web_download_action(url: str, dest: str, overwrite: bool = True) -> ActionResult:
    """Download a file from URL."""
    try:
        from pathlib import Path
        dest_path = Path(dest).resolve()

        if dest_path.exists() and not overwrite:
            return ActionResult(success=False, error=f"File exists: {dest}")

        with httpx.Client(timeout=60.0, follow_redirects=False, trust_env=False) as client:
            with _public_stream(client, "GET", url) as resp:
                resp.raise_for_status()
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with open(dest_path, "wb") as f:
                    for chunk in resp.iter_bytes(chunk_size=8192):
                        f.write(chunk)

        size = dest_path.stat().st_size
        return ActionResult(
            success=True,
            output=f"Downloaded {size} bytes to {dest_path}",
            data={"path": str(dest_path), "size": size}
        )
    except Exception as e:
        return ActionResult(success=False, error=str(e))


get_registry()

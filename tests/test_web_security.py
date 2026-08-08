from __future__ import annotations

import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

import core.actions.browser as browser_actions
import core.actions.web as web_actions
import core.url_security as url_security
from core.url_security import URLSecurityError, validate_connected_peer, validate_public_http_url

PUBLIC_V4 = "93.184.216.34"


def _dns_answer(address: str, port: int) -> list[tuple]:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (address, port, 0, 0) if family == socket.AF_INET6 else (address, port)
    return [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)]


def _install_public_dns(monkeypatch: pytest.MonkeyPatch, calls: list[str] | None = None) -> None:
    def resolve(host: str, port: int, **_kwargs):
        if calls is not None:
            calls.append(host)
        return _dns_answer(PUBLIC_V4, port)

    monkeypatch.setattr(url_security.socket, "getaddrinfo", resolve)


def test_public_url_is_normalized_and_dns_is_rechecked(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    _install_public_dns(monkeypatch, calls)

    first = validate_public_http_url(" HTTPS://Example.COM./news?q=1#fragment ")
    second = validate_public_http_url("https://example.com/other")

    assert first.url == "https://example.com/news?q=1"
    assert first.addresses == (PUBLIC_V4,)
    assert second.host == "example.com"
    assert calls == ["example.com", "example.com"]


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/file",
        "http://localhost/admin",
        "http://service.local/status",
        "http://user:password@example.com/",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://10.0.0.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/computeMetadata/v1/",
    ],
)
def test_url_security_blocks_unsafe_targets(url: str) -> None:
    with pytest.raises(URLSecurityError):
        validate_public_http_url(url)


def test_url_security_rejects_private_or_mixed_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def mixed_resolver(_host: str, port: int, **_kwargs):
        return [
            *_dns_answer(PUBLIC_V4, port),
            *_dns_answer("192.168.1.8", port),
        ]

    monkeypatch.setattr(url_security.socket, "getaddrinfo", mixed_resolver)
    with pytest.raises(URLSecurityError, match="non-public"):
        validate_public_http_url("https://example.com/")


def test_connected_private_peer_is_rejected() -> None:
    stream = SimpleNamespace(get_extra_info=lambda _name: ("127.0.0.1", 443))
    response = SimpleNamespace(extensions={"network_stream": stream})

    with pytest.raises(URLSecurityError, match="non-public"):
        validate_connected_peer(response)


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_read_only_fetch_rejects_mutating_methods(method: str) -> None:
    result = web_actions.web_fetch_action("https://example.com/", method=method)

    assert result.success is False
    assert "GET or HEAD" in result.error


def test_read_only_fetch_rejects_body_and_sensitive_headers() -> None:
    with_body = web_actions.web_fetch_action("https://example.com/", data="payload")
    with_auth = web_actions.web_fetch_action(
        "https://example.com/",
        headers={"Authorization": "Bearer secret"},
    )

    assert with_body.success is False
    assert "request body" in with_body.error
    assert with_auth.success is False
    assert "header is not allowed" in with_auth.error


def test_fetch_blocks_private_redirect_before_second_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_public_dns(monkeypatch)
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/secret"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(web_actions.httpx, "Client", lambda **_kwargs: client)

    result = web_actions.web_fetch_action("https://example.com/start")

    assert result.success is False
    assert "non-public" in result.error
    assert requests == ["https://example.com/start"]


def test_fetch_revalidates_dns_for_public_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dns_calls: list[str] = []
    _install_public_dns(monkeypatch, dns_calls)
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "https://example.org/final"})
        return httpx.Response(200, text="verified")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(web_actions.httpx, "Client", lambda **_kwargs: client)

    result = web_actions.web_fetch_action("https://example.com/start")

    assert result.success is True
    assert result.output == "verified"
    assert requests == ["https://example.com/start", "https://example.org/final"]
    assert dns_calls == ["example.com", "example.org"]


class _CountingStream(httpx.SyncByteStream):
    def __init__(self) -> None:
        self.chunks_read = 0

    def __iter__(self):
        for chunk in (b"a" * 8, b"b" * 8, b"c" * 8):
            self.chunks_read += 1
            yield chunk


def test_fetch_stops_stream_before_accumulating_past_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_public_dns(monkeypatch)
    stream = _CountingStream()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/plain; charset=utf-8"},
            stream=stream,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(web_actions.httpx, "Client", lambda **_kwargs: client)

    result = web_actions.web_fetch_action("https://example.com/large", max_size=10)

    assert result.success is True
    assert result.data["size"] == 10
    assert result.data["truncated"] is True
    assert result.output.startswith("a" * 8 + "b" * 2)
    assert stream.chunks_read == 2


def test_download_rejects_private_url_before_touching_destination(tmp_path) -> None:
    destination = tmp_path / "not-created" / "payload.bin"

    result = web_actions.web_download_action("http://127.0.0.1/file", str(destination))

    assert result.success is False
    assert not destination.exists()
    assert not destination.parent.exists()


@pytest.mark.asyncio
async def test_browser_navigation_rejects_private_url_before_browser_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_browser = AsyncMock()
    monkeypatch.setattr(browser_actions, "_get_browser", get_browser)

    result = await browser_actions.browser_navigate_action("http://127.0.0.1/admin")

    assert result.success is False
    get_browser.assert_not_awaited()


@pytest.mark.asyncio
async def test_browser_navigation_rejects_private_connected_peer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_public_dns(monkeypatch)
    response = SimpleNamespace(
        status=200,
        server_addr=AsyncMock(return_value={"ipAddress": "127.0.0.1", "port": 443}),
    )
    page = SimpleNamespace(
        url="https://example.com/",
        goto=AsyncMock(return_value=response),
        title=AsyncMock(return_value="Example"),
    )
    context = SimpleNamespace(new_page=AsyncMock(return_value=page))
    monkeypatch.setattr(browser_actions, "_get_browser", AsyncMock(return_value=context))

    result = await browser_actions.browser_navigate_action("https://example.com/")

    assert result.success is False
    assert "non-public" in result.error


@pytest.mark.asyncio
async def test_browser_request_guard_aborts_unsafe_request() -> None:
    route = SimpleNamespace(
        request=SimpleNamespace(url="http://169.254.169.254/latest/meta-data/"),
        abort=AsyncMock(),
        continue_=AsyncMock(),
    )

    await browser_actions._guard_public_request(route)

    route.abort.assert_awaited_once_with("blockedbyclient")
    route.continue_.assert_not_awaited()


@pytest.mark.asyncio
async def test_browser_request_guard_allows_public_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_public_dns(monkeypatch)
    route = SimpleNamespace(
        request=SimpleNamespace(url="https://example.com/app.js"),
        abort=AsyncMock(),
        continue_=AsyncMock(),
    )

    await browser_actions._guard_public_request(route)

    route.continue_.assert_awaited_once_with()
    route.abort.assert_not_awaited()

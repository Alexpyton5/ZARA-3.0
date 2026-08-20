"""lab-send routing proofs (ZARA-NIGHT-SHIFT 042).

Ensures the LAB send path routes by recipient, keeps normal chat working, and
reports the REAL mentor relay status in the ACK so the UI cannot show a false
"relay offline" warning (or hide a real one).

No runtime, no network: the IPC handler is exercised with light fakes.
"""
from __future__ import annotations

import types

import pytest

from core.ipc_handlers import IPCHandler, IPCMessage


class _FakeRelayStatus:
    def __init__(self, online: bool):
        self.online = online


class _FakeRelay:
    def __init__(self, online: bool = True, raises: bool = False):
        self._online = online
        self._raises = raises

    def status(self):
        if self._raises:
            raise RuntimeError("relay path unreadable")
        return _FakeRelayStatus(self._online)


class _FakeLab:
    def __init__(self, relay=None, fail: bool = False):
        self.mentor_relay = relay or _FakeRelay()
        self.calls: list[tuple[str, str, str]] = []
        self.fail = fail

    async def send_message(self, author, target, content):
        self.calls.append((author, target, content))
        if self.fail:
            raise RuntimeError("worker indisponivel")
        return {"success": True, "state": "QUEUED", "target": target}


def _handler(lab):
    h = IPCHandler.__new__(IPCHandler)
    h.lab = lab
    h._lab_background_tasks = set()
    h.responses = []
    h.errors = []

    async def send_response(request_id, response=None, error=None, result=None):
        h.responses.append({"request_id": request_id, "response": response})

    async def send_error(msg, error):
        h.errors.append(error)

    h.send_response = send_response  # type: ignore[method-assign]
    h.send_error = types.MethodType(lambda self, msg, error: send_error(msg, error), h)  # type: ignore
    return h


def _msg(target: str, content: str = "ola"):
    return IPCMessage(
        type="lab-send",
        payload={"author": "alex", "target": target, "content": content},
        request_id=f"req-{target}",
    )


async def _drain(handler):
    for task in list(handler._lab_background_tasks):
        try:
            await task
        except Exception:
            pass


@pytest.mark.asyncio
async def test_lab_send_acks_queued_for_normal_chat():
    lab = _FakeLab()
    h = _handler(lab)
    await h.handle_lab_send(_msg("zara"))
    await _drain(h)
    ack = h.responses[0]["response"]
    assert ack["success"] is True
    assert ack["state"] == "QUEUED"
    assert ack["target"] == "zara"
    # chat normal nao deve carregar status de relay
    assert "relay_online" not in ack
    assert lab.calls == [("alex", "zara", "ola")]


@pytest.mark.asyncio
async def test_lab_send_routes_to_requested_recipient():
    lab = _FakeLab()
    h = _handler(lab)
    for target in ("zara", "mentor", "hermes", "opencode"):
        await h.handle_lab_send(_msg(target))
    await _drain(h)
    assert [c[1] for c in lab.calls] == ["zara", "mentor", "hermes", "opencode"]
    assert [r["response"]["target"] for r in h.responses] == [
        "zara",
        "mentor",
        "hermes",
        "opencode",
    ]


@pytest.mark.asyncio
async def test_mentor_ack_reports_relay_online_when_heartbeat_is_fresh():
    h = _handler(_FakeLab(relay=_FakeRelay(online=True)))
    await h.handle_lab_send(_msg("mentor"))
    await _drain(h)
    assert h.responses[0]["response"]["relay_online"] is True


@pytest.mark.asyncio
async def test_mentor_ack_reports_relay_offline_truthfully():
    h = _handler(_FakeLab(relay=_FakeRelay(online=False)))
    await h.handle_lab_send(_msg("mentor"))
    await _drain(h)
    ack = h.responses[0]["response"]
    assert ack["relay_online"] is False
    assert ack["state"] == "QUEUED"  # mensagem preservada na fila, nao perdida


@pytest.mark.asyncio
async def test_mentor_ack_degrades_to_offline_when_status_raises():
    h = _handler(_FakeLab(relay=_FakeRelay(raises=True)))
    await h.handle_lab_send(_msg("mentor"))
    await _drain(h)
    ack = h.responses[0]["response"]
    assert ack["relay_online"] is False
    assert ack["relay_status_error"] is True


@pytest.mark.asyncio
async def test_lab_send_rejects_empty_content():
    h = _handler(_FakeLab())
    await h.handle_lab_send(
        IPCMessage(type="lab-send", payload={"author": "alex", "target": "zara", "content": "   "},
                   request_id="r0")
    )
    assert h.errors == ["Mensagem vazia"]
    assert h.responses == []


@pytest.mark.asyncio
async def test_lab_send_errors_when_lab_unavailable():
    h = _handler(None)
    await h.handle_lab_send(_msg("zara"))
    assert h.errors == ["ZARA Lab indisponível"]


@pytest.mark.asyncio
async def test_background_worker_failure_does_not_break_ack():
    """A falha do turno acontece em background; o ACK ja saiu como QUEUED."""
    lab = _FakeLab(fail=True)
    h = _handler(lab)
    await h.handle_lab_send(_msg("hermes"))
    await _drain(h)
    assert h.responses[0]["response"]["state"] == "QUEUED"
    assert h.errors == []

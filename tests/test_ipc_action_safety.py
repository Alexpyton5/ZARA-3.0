"""IPC action truth with the retired Supercerebro key."""

import asyncio

import pytest

import core.ipc_handlers as ipc_handlers
from core.action_confirmation import ConfirmationProof
from core.action_registry import ActionResult, get_registry
from core.ipc_handlers import IPCHandler, IPCMessage


class FakeHermes:
    def __init__(self, *, connects: bool = True, disable_raises: bool = False):
        self.connects = connects
        self.disable_raises = disable_raises
        self.enabled = False
        self.is_connected = False
        self.enable_calls = 0
        self.disable_calls = 0

    async def enable_supercerebro(self) -> bool:
        self.enable_calls += 1
        self.enabled = self.connects
        self.is_connected = self.connects
        return self.connects

    async def disable_supercerebro(self) -> None:
        self.disable_calls += 1
        if self.disable_raises:
            raise RuntimeError("fake disconnect failure")
        self.enabled = False
        self.is_connected = False


class FakeAutoOff:
    def __init__(self, callback=None):
        self.callback = callback
        self.started = 0
        self.stopped = 0

    def start(self):
        self.started += 1

    def stop(self):
        self.stopped += 1

    async def trigger(self, reason):
        await self.callback(reason)


@pytest.fixture(autouse=True)
def restore_global_policy():
    registry = get_registry()
    previous_pc_control = registry.pc_control_allowed
    previous_medium = registry.medium_risk_open
    registry.pc_control_allowed = False
    registry.medium_risk_open = False
    yield
    registry.pc_control_allowed = previous_pc_control
    registry.medium_risk_open = previous_medium


def _grant_ok(monkeypatch, tmp_path):
    """Portão do PC exige grant WhatsApp válido (ordem do Alex, 02/10/2026)."""
    from core import supercerebro_grant as sg
    p = tmp_path / "whatsapp_grant.json"
    sg.write_grant(minutes=30, path=p)
    monkeypatch.setenv("ZARA_WHATSAPP_GRANT_PATH", str(p))


def _handler():
    sent: list[IPCMessage] = []

    async def send(message: IPCMessage) -> None:
        sent.append(message)

    handler = IPCHandler(send)
    handler._supercerebro_auto_off = FakeAutoOff(handler._auto_disable_supercerebro)
    return handler, sent


def test_toggle_rejects_truthy_non_boolean_input():
    handler, sent = _handler()
    hermes = FakeHermes()
    handler.hermes = hermes

    asyncio.run(
        handler.handle_supercerebro_toggle(
            IPCMessage(type="supercerebro-toggle", request_id="1", payload={"active": "false"})
        )
    )

    assert handler.supercerebro_active
    assert get_registry().pc_control_allowed
    assert hermes.enable_calls == 0
    assert sent[-1].error == "Active state must be a boolean"


def test_toggle_controls_capability_but_does_not_remove_risk_gate():
    handler, sent = _handler()
    handler.hermes = FakeHermes()

    asyncio.run(
        handler.handle_supercerebro_toggle(
            IPCMessage(type="supercerebro-toggle", request_id="1", payload={"active": True})
        )
    )

    assert handler.supercerebro_active
    assert get_registry().pc_control_allowed
    assert not get_registry().medium_risk_open
    assert sent[-1].response["active"] is True


def test_retired_key_never_starts_idle_monitor_or_hermes():
    handler, sent = _handler()
    handler.hermes = FakeHermes(connects=False)

    asyncio.run(
        handler.handle_supercerebro_toggle(
            IPCMessage(type="supercerebro-toggle", request_id="1", payload={"active": True})
        )
    )

    assert handler.supercerebro_active
    assert get_registry().pc_control_allowed
    assert handler.hermes.enable_calls == 0
    assert handler._supercerebro_auto_off.started == 0
    assert sent[-1].response["active"] is True
    assert sent[-1].response["key_required"] is False


def test_old_disable_request_cannot_revoke_permanent_control():
    handler, sent = _handler()
    handler.hermes = FakeHermes(disable_raises=True)
    asyncio.run(
        handler.handle_supercerebro_toggle(
            IPCMessage(type="supercerebro-toggle", request_id="1", payload={"active": True})
        )
    )

    asyncio.run(
        handler.handle_supercerebro_toggle(
            IPCMessage(type="supercerebro-toggle", request_id="2", payload={"active": False})
        )
    )

    assert handler.supercerebro_active
    assert get_registry().pc_control_allowed
    assert handler.hermes.disable_calls == 0
    assert handler._supercerebro_auto_off.stopped == 0
    assert sent[-1].response["active"] is True


def test_status_reports_the_current_local_key_state():
    handler, sent = _handler()
    handler._set_supercerebro_state(True)

    asyncio.run(
        handler.handle_supercerebro_status(
            IPCMessage(type="supercerebro-status", request_id="status")
        )
    )

    assert sent[-1].response["active"] is True
    assert sent[-1].response["enabled"] is True
    assert sent[-1].response["key_required"] is False


def test_old_auto_off_callback_does_not_revoke_control():
    handler, sent = _handler()
    handler._set_supercerebro_state(True)

    asyncio.run(handler._supercerebro_auto_off.trigger("idle-timeout"))

    assert handler.supercerebro_active
    assert get_registry().pc_control_allowed
    assert sent == []


def test_ipc_pc_action_with_grant_and_does_not_log_private_params(capsys, monkeypatch, tmp_path):
    _grant_ok(monkeypatch, tmp_path)
    handler, sent = _handler()
    registry = get_registry()
    calls: list[str] = []
    action_name = "test_ipc_pc_control"
    registry.register(
        action_name,
        lambda secret="": calls.append(secret) or "done",
        capability="PC_CONTROL",
    )
    try:
        asyncio.run(
            handler.handle_action_execute(
                IPCMessage(
                    type="action-execute",
                    request_id="1",
                    payload={
                        "action": action_name,
                        "params": {"confirm": True, "secret": "must-not-be-logged"},
                    },
                )
            )
        )
    finally:
        registry.unregister(action_name)

    response = next(message for message in reversed(sent) if message.type == "response")
    result = response.response["result"]
    assert result.success
    assert calls == ["must-not-be-logged"]
    assert "must-not-be-logged" not in capsys.readouterr().out


def test_action_execute_rejects_non_object_params():
    handler, sent = _handler()

    asyncio.run(
        handler.handle_action_execute(
            IPCMessage(
                type="action-execute",
                request_id="1",
                payload={"action": "anything", "params": ["not", "an", "object"]},
            )
        )
    )

    assert sent[-1].error == "Action params must be an object"


def test_action_execute_rejects_confirmation_proof_on_normal_route():
    handler, sent = _handler()

    asyncio.run(
        handler.handle_action_execute(
            IPCMessage(
                type="action-execute",
                request_id="1",
                payload={
                    "action": "terminal",
                    "params": {"confirmation_id": "not-accepted-here"},
                },
            )
        )
    )

    assert sent[-1].error == "Confirmation proof is only accepted by action-confirm"


def test_action_confirm_forwards_direct_contract_without_logging_params(monkeypatch, capsys):
    handler, sent = _handler()
    observed = {}

    async def fake_execute(action, confirmation_id, action_fingerprint, **params):
        observed.update(
            action=action,
            confirmation_id=confirmation_id,
            action_fingerprint=action_fingerprint,
            params=params,
        )
        return ActionResult(success=True, output="done")

    monkeypatch.setattr(ipc_handlers, "execute_confirmed_action", fake_execute)
    asyncio.run(
        handler.handle_action_confirm(
            IPCMessage(
                type="action-confirm",
                request_id="1",
                payload={
                    "confirmation_id": "c" * 32,
                    "action_fingerprint": "hmac-sha256:" + "f" * 64,
                    "action": "terminal",
                    "params": {"command": "private-command-value"},
                },
            )
        )
    )

    assert observed == {
        "action": "terminal",
        "confirmation_id": "c" * 32,
        "action_fingerprint": "hmac-sha256:" + "f" * 64,
        "params": {"command": "private-command-value"},
    }
    assert sent[-1].response["result"].success
    assert "private-command-value" not in capsys.readouterr().out


def test_action_confirm_cancel_consumes_pending_challenge():
    handler, sent = _handler()
    registry = get_registry()
    challenge = registry._confirmation_broker.issue(
        action="terminal",
        metadata={"risk": "HIGH"},
        params={"command": "echo safe"},
        summary="Executar comando: echo safe",
    )

    asyncio.run(
        handler.handle_action_confirm_cancel(
            IPCMessage(
                type="action-confirm-cancel",
                request_id="1",
                payload={"confirmation_id": challenge.confirmation_id},
            )
        )
    )
    allowed, status = registry._confirmation_broker.consume(
        ConfirmationProof(
            challenge.confirmation_id,
            challenge.action_fingerprint,
        ),
        action="terminal",
        metadata={"risk": "HIGH"},
        params={"command": "echo safe"},
    )

    assert sent[-1].response == {"success": True, "cancelled": True}
    assert not allowed
    assert status == "CONFIRMATION_INVALID"


def test_action_list_exposes_risk_and_capability():
    handler, sent = _handler()
    registry = get_registry()
    action_name = "test_action_metadata"
    registry.register(action_name, lambda: "safe", risk="MEDIUM", capability="FILES_MUTATE")
    try:
        asyncio.run(
            handler.handle_action_list(
                IPCMessage(type="action-list", request_id="1")
            )
        )
    finally:
        registry.unregister(action_name)

    metadata = sent[-1].response[action_name]
    assert metadata["risk"] == "MEDIUM"
    assert metadata["capability"] == "FILES_MUTATE"

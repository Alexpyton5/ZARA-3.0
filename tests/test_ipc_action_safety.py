"""IPC safety tests using only in-memory actions and a fake Hermes session."""

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

    async def enable_supercerebro(self) -> bool:
        self.enable_calls += 1
        self.enabled = self.connects
        self.is_connected = self.connects
        return self.connects

    async def disable_supercerebro(self) -> None:
        if self.disable_raises:
            raise RuntimeError("fake disconnect failure")
        self.enabled = False
        self.is_connected = False


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


def _handler():
    sent: list[IPCMessage] = []

    async def send(message: IPCMessage) -> None:
        sent.append(message)

    return IPCHandler(send), sent


def test_toggle_rejects_truthy_non_boolean_input():
    handler, sent = _handler()
    hermes = FakeHermes()
    handler.hermes = hermes

    asyncio.run(
        handler.handle_supercerebro_toggle(
            IPCMessage(type="supercerebro-toggle", request_id="1", payload={"active": "false"})
        )
    )

    assert not handler.supercerebro_active
    assert not get_registry().pc_control_allowed
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


def test_failed_enable_is_fail_closed():
    handler, sent = _handler()
    handler.hermes = FakeHermes(connects=False)

    asyncio.run(
        handler.handle_supercerebro_toggle(
            IPCMessage(type="supercerebro-toggle", request_id="1", payload={"active": True})
        )
    )

    assert not handler.supercerebro_active
    assert not get_registry().pc_control_allowed
    assert sent[-1].error == "Hermes Gateway is offline"


def test_disable_revokes_permission_even_if_remote_disable_fails():
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

    assert not handler.supercerebro_active
    assert not get_registry().pc_control_allowed
    assert sent[-1].response["active"] is False


def test_ipc_cannot_bypass_supercerebro_off_with_confirm_true(capsys):
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
    assert not result.success
    assert calls == []
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

import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from core.lab_v1.operation_ledger import OperationLedger
from core.lab_v1.service import LabV1Service
from core.lab_v1.store import LabStore

# Keep the archived compatibility contract as a portable test fixture, not
# as a second live voice package in the application root.
_LEGACY_VOICE_TEST_ROOT = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(_LEGACY_VOICE_TEST_ROOT))

from voice.operation_ledger_contract import (
    VoiceOperationRequest,
    admit_voice_operation,
)


@dataclass
class FakeAck:
    request_id: str
    operation_id: str
    command: str
    accepted: bool = True
    newly_admitted: bool = True


class FakeLedger:
    def __init__(self):
        self.calls = []

    def admit(self, request_id, command, payload):
        self.calls.append((request_id, command, payload))
        return FakeAck(request_id, "op-1", command)


class FakeWakeup:
    def __init__(self):
        self.set_calls = 0

    def set(self):
        self.set_calls += 1


def test_voice_request_builds_stable_ledger_payload():
    request = VoiceOperationRequest(
        request_id=" voice-42 ", command="lab.v1.submit", transcript="  execute a missão  "
    )
    ledger = FakeLedger()

    ack = admit_voice_operation(ledger, request)

    assert ack.operation_id == "op-1"
    assert ledger.calls == [
        (
            "voice-42",
            "lab.v1.submit",
            {
                "source": "voice",
                "transcript": "execute a missão",
                "objective": "execute a missão",
            },
        )
    ]


def test_voice_request_rejects_blank_values_before_ledger_call():
    ledger = FakeLedger()

    with pytest.raises(ValueError, match="transcript"):
        admit_voice_operation(
            ledger,
            VoiceOperationRequest(request_id="r1", command="cmd", transcript=" "),
        )

    assert ledger.calls == []


def test_voice_request_requires_ledger_admit_contract():
    request = VoiceOperationRequest("r1", "cmd", "hello")

    with pytest.raises(TypeError, match="admit"):
        admit_voice_operation(object(), request)


def test_successful_voice_admission_wakes_the_existing_consumer_event():
    ledger = FakeLedger()
    wakeup = FakeWakeup()

    ack = admit_voice_operation(
        ledger,
        VoiceOperationRequest(
            "voice-1", "lab.v1.cancel", "cancele a missão", session_id="s-1"
        ),
        wakeup=wakeup,
    )

    assert ack.operation_id == "op-1"
    assert wakeup.set_calls == 1


def test_invalid_voice_request_does_not_emit_a_wakeup():
    ledger = FakeLedger()
    wakeup = FakeWakeup()

    with pytest.raises(ValueError, match="transcript"):
        admit_voice_operation(
            ledger,
            VoiceOperationRequest("voice-1", "lab.v1.cancel", " "),
            wakeup=wakeup,
        )

    assert wakeup.set_calls == 0


def test_failed_ledger_admission_does_not_emit_a_wakeup():
    class FailingLedger:
        def admit(self, request_id, command, payload):
            raise RuntimeError("ledger unavailable")

    wakeup = FakeWakeup()

    with pytest.raises(RuntimeError, match="ledger unavailable"):
        admit_voice_operation(
            FailingLedger(),
            VoiceOperationRequest(
                "voice-1", "lab.v1.cancel", "cancele", session_id="s-1"
            ),
            wakeup=wakeup,
        )

    assert wakeup.set_calls == 0


def test_wakeup_must_expose_the_event_set_contract():
    with pytest.raises(TypeError, match="set"):
        admit_voice_operation(
            FakeLedger(),
            VoiceOperationRequest("voice-1", "lab.v1.cancel", "cancele"),
            wakeup=object(),
        )


def test_real_ledger_is_durable_before_the_wakeup_observer_runs(tmp_path):
    ledger = OperationLedger(tmp_path / "lab.db")

    class InspectingWakeup:
        observed = None

        def set(self):
            self.observed = ledger.get("voice-1")

    wakeup = InspectingWakeup()

    ack = admit_voice_operation(
        ledger,
        VoiceOperationRequest(
            "voice-1", "lab.v1.cancel", "cancele a missão", session_id="s-1"
        ),
        wakeup=wakeup,
    )

    assert wakeup.observed == ack
    assert OperationLedger(tmp_path / "lab.db").get("voice-1") == ack


@pytest.mark.parametrize(
    ("command", "session_id", "expected_payload"),
    [
        (
            "lab.v1.submit",
            None,
            {"source": "voice", "transcript": "faça A", "objective": "faça A"},
        ),
        (
            "lab.v1.message",
            "s-1",
            {
                "source": "voice",
                "transcript": "continue A",
                "session_id": "s-1",
                "content": "continue A",
            },
        ),
        (
            "lab.v1.cancel",
            "s-1",
            {"source": "voice", "transcript": "cancele", "session_id": "s-1"},
        ),
        (
            "lab.v1.resume",
            "s-1",
            {"source": "voice", "transcript": "retome", "session_id": "s-1"},
        ),
    ],
)
def test_voice_payload_matches_each_existing_dispatch_contract(
    command, session_id, expected_payload
):
    ledger = FakeLedger()
    transcript = expected_payload["transcript"]

    admit_voice_operation(
        ledger,
        VoiceOperationRequest(
            "voice-1", command, transcript, session_id=session_id
        ),
    )

    assert ledger.calls == [("voice-1", command, expected_payload)]


@pytest.mark.parametrize("command", ["lab.v1.message", "lab.v1.cancel", "lab.v1.resume"])
def test_session_bound_voice_commands_reject_missing_session_before_admission(command):
    ledger = FakeLedger()
    wakeup = FakeWakeup()

    with pytest.raises(ValueError, match="session_id"):
        admit_voice_operation(
            ledger,
            VoiceOperationRequest("voice-1", command, "continue"),
            wakeup=wakeup,
        )

    assert ledger.calls == []
    assert wakeup.set_calls == 0


def test_unknown_voice_command_is_rejected_before_admission():
    ledger = FakeLedger()

    with pytest.raises(ValueError, match="unsupported voice command"):
        admit_voice_operation(
            ledger,
            VoiceOperationRequest("voice-1", "provider.call", "faça algo"),
        )

    assert ledger.calls == []


@pytest.mark.parametrize(
    "ack",
    [None, FakeAck("voice-1", "", "lab.v1.submit"), FakeAck("voice-1", "op", "lab.v1.submit", accepted=False)],
)
def test_invalid_or_rejected_ack_never_emits_wakeup(ack):
    class InvalidAckLedger:
        def admit(self, request_id, command, payload):
            return ack

    wakeup = FakeWakeup()

    with pytest.raises((TypeError, ValueError), match="ack"):
        admit_voice_operation(
            InvalidAckLedger(),
            VoiceOperationRequest("voice-1", "lab.v1.submit", "faça algo"),
            wakeup=wakeup,
        )

    assert wakeup.set_calls == 0


def test_idempotent_replay_emits_wakeup_again_for_a_possibly_pending_operation(tmp_path):
    ledger = OperationLedger(tmp_path / "lab.db")
    wakeup = FakeWakeup()
    request = VoiceOperationRequest("voice-1", "lab.v1.submit", "faça algo")

    first = admit_voice_operation(ledger, request, wakeup=wakeup)
    replay = admit_voice_operation(ledger, request, wakeup=wakeup)

    assert replay == first
    assert replay.newly_admitted is False
    assert wakeup.set_calls == 2


def test_wakeup_failure_keeps_the_admission_replayable(tmp_path):
    ledger = OperationLedger(tmp_path / "lab.db")
    request = VoiceOperationRequest("voice-1", "lab.v1.submit", "faça algo")

    class FailingWakeup:
        def set(self):
            raise RuntimeError("consumer unavailable")

    with pytest.raises(RuntimeError, match="consumer unavailable"):
        admit_voice_operation(ledger, request, wakeup=FailingWakeup())

    wakeup = FakeWakeup()
    replay = admit_voice_operation(ledger, request, wakeup=wakeup)
    assert replay.newly_admitted is False
    assert wakeup.set_calls == 1


@pytest.mark.parametrize(
    ("command", "transcript", "session_id", "method", "args", "kwargs"),
    [
        ("lab.v1.submit", "Improve", None, "start_autopilot", ("Improve",), {"session_id": None}),
        ("lab.v1.message", "continue", "s", "submit", ("s", "continue"), {}),
        ("lab.v1.cancel", "cancel", "s", "cancel_autopilot", ("s",), {}),
        ("lab.v1.resume", "resume", "s", "resume_source_autopilot", ("s",), {}),
    ],
)
def test_voice_admission_wakeup_dispatch_and_terminal_result_use_existing_contracts(
    tmp_path, command, transcript, session_id, method, args, kwargs
):
    service = LabV1Service()
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    service._store = store
    service._runtime = Mock(store=store)
    service._get_runtime = Mock(side_effect=AssertionError("provider bootstrap forbidden"))
    target = AsyncMock(return_value={"success": True, "state": "DONE"})
    setattr(service, method, target)
    wakeup = FakeWakeup()

    ack = admit_voice_operation(
        service._get_operation_ledger(),
        VoiceOperationRequest(
            "voice-1", command, transcript, session_id=session_id
        ),
        wakeup=wakeup,
    )
    result = asyncio.run(service.dispatch_operation(ack.operation_id))

    assert wakeup.set_calls == 1
    assert result["state"] == "COMPLETED"
    target.assert_awaited_once_with(*args, **kwargs)
    service._get_runtime.assert_not_called()

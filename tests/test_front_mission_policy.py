"""The public facade enforces executable workforce policy before mission work."""
import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

from core.lab_v1.service import LabV1Service


def test_disabled_mission_policy_blocks_before_autopilot():
    service = LabV1Service()
    service._supervisor = SimpleNamespace(policy=lambda: {
        'mission_entry_enabled': False, 'background_enabled': False})
    service._autopilot = Mock()
    result = asyncio.run(service.start_autopilot('Audite a ZARA'))
    assert result['code'] == 'WORKFORCE_POLICY_REQUIRED'
    service._autopilot.start.assert_not_called()


def test_public_run_uses_same_canonical_autopilot():
    service = LabV1Service()
    service._autopilot = SimpleNamespace(run=Mock(return_value={'success': True, 'state': 'COMPLETED'}))
    result = asyncio.run(service.run_autopilot('session'))
    assert result['state'] == 'COMPLETED'
    service._autopilot.run.assert_called_once_with('session')


def test_mission_chat_cannot_be_a_second_worker_trigger():
    service = LabV1Service()
    service._autopilot = SimpleNamespace(controller=SimpleNamespace(
        snapshot=lambda sid: {'session_id': sid, 'state': 'RUNNING'}))
    result = asyncio.run(service.submit('session', 'continue'))
    assert result['code'] == 'MISSION_CONTROLLED'


def test_background_policy_can_be_paused_without_provider_access():
    service = LabV1Service()
    service._supervisor = SimpleNamespace(policy=lambda: {
        'mission_entry_enabled': True, 'background_enabled': False})
    result = asyncio.run(service.start_background())
    assert result == {'success': True, 'state': 'PAUSED'}

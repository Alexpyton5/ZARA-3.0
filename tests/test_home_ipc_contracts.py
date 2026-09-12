"""Home IPC contracts: fake stores and temporary paths, no live integrations."""
import asyncio
from unittest.mock import AsyncMock

import pytest

from core.ipc_handlers import IPCHandler, IPCMessage

pytestmark = pytest.mark.safe


def test_project_context_does_not_mislabel_legacy_docs_as_projects():
    class FakeMemory:
        def list_projects(self): return ['zara']
        def list_project_docs(self, _project): return ['state']
        def get_project_doc(self, _project, _key):
            return {'updated_at': 123, 'content': 'private project content'}
        def get_active_project(self): return 'zara'
        def list_docs(self): return ['roadmap', 'charter']

    handler = IPCHandler(AsyncMock())
    handler.project_memory = FakeMemory()
    asyncio.run(handler.handle_message(IPCMessage(type='project-memory-context', request_id='home')))
    result = handler.send.call_args.args[0].response
    assert result == {
        'success': True, 'active_project_id': 'zara',
        'projects': [{'id': 'zara', 'keys': ['state'], 'updated_at': 123}],
        'legacy_document_keys': ['roadmap', 'charter'],
    }
    assert 'private project content' not in str(result)


def test_project_context_reports_missing_store_as_error():
    handler = IPCHandler(AsyncMock())
    asyncio.run(handler.handle_project_memory_context(IPCMessage(type='project-memory-context', request_id='home')))
    assert handler.send.call_args.args[0].error == 'Project Memory indisponível'


@pytest.mark.parametrize('channel', ['voice-start', 'action-execute', 'send-message', 'config-set', 'reminder-create'])
def test_smoke_mode_blocks_side_effect_channels(monkeypatch, channel):
    monkeypatch.setenv('ZARA_SMOKE_TEST', '1')
    handler = IPCHandler(AsyncMock())
    handler.handle_action_execute = AsyncMock()
    handler.handle_voice_start = AsyncMock()
    asyncio.run(handler.handle_message(IPCMessage(type=channel, request_id='blocked', payload={})))
    assert handler.send.call_args.args[0].error.startswith('SMOKE_READ_ONLY')
    handler.handle_action_execute.assert_not_called()
    handler.handle_voice_start.assert_not_called()


def test_runtime_override_isolates_config_in_source_mode(monkeypatch, tmp_path):
    from core.paths import config_dir
    monkeypatch.setenv('ZARA3_HOME', str(tmp_path))
    assert config_dir() == tmp_path / 'config'


def test_smoke_mode_without_marked_temp_home_fails_before_initializing(monkeypatch, tmp_path):
    import main
    monkeypatch.setenv('ZARA_SMOKE_TEST', '1')
    monkeypatch.setenv('ZARA3_HOME', str(tmp_path))
    setup = AsyncMock()
    monkeypatch.setattr(main, 'setup_environment', setup)
    assert main.main() == 1
    setup.assert_not_called()

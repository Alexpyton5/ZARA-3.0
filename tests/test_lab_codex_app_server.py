"""Official protocol fixtures; no external account or paid inference in tests."""
import json
import pytest
from core.lab_v1.providers.codex_app_server import CodexAppServerAdapter, _safe_config, RpcError
from core.lab_v1.providers.base import InvocationOptions


class Rpc:
    items = []
    calls = []

    def __init__(self, *args, **kwargs):
        self.events = list(self.items)

    def __enter__(self): return self
    def __exit__(self, *_): pass

    def call(self, method, params):
        self.calls.append((method, params))
        if method == 'account/read': return {'account': {'type': 'chatgpt', 'email': 'private@example.invalid', 'secret': 'never-cache'}}
        if method == 'model/list': return {'data': [{'model': 'gpt-6-astra', 'displayName': 'Astra', 'defaultReasoningEffort': 'low', 'supportedReasoningEfforts': [{'reasoningEffort': 'low'}]}]}
        if method == 'thread/start': return {'thread': {'id': 'thread1'}, 'model': params['model']}
        if method == 'turn/start': return {'turn': {'id': 'turn1'}}
        raise AssertionError(method)

    def receive(self): raise AssertionError('Unexpected extra receive')


def adapter(tmp_path, items=()):
    Rpc.calls = []
    Rpc.items = list(items)
    item = CodexAppServerAdapter(cache_path=tmp_path / 'models.json', binary='test.exe', rpc_factory=Rpc)
    item.discover_models()
    return item


def event(method, **params): return {'method': method, 'params': {'threadId': 'thread1', **params}}


def test_discovery_does_not_persist_account_data(tmp_path):
    item = adapter(tmp_path)
    assert item.probe().authenticated
    content = item.cache_path.read_text()
    assert 'private@' not in content and 'never-cache' not in content
    count = len(Rpc.calls)
    assert item.declared_models[0].model_id == 'gpt-6-astra'
    item.probe()
    assert len(Rpc.calls) == count


def test_provenance_is_not_invented_and_reasoning_not_saved(tmp_path):
    item = adapter(tmp_path, [event('item/completed', item={'type': 'reasoning', 'text': 'private reasoning'}),
        event('item/completed', item={'type': 'agentMessage', 'text': 'OK'}),
        event('thread/tokenUsage/updated', tokenUsage={'last': {'inputTokens': 7, 'outputTokens': 2}}),
        event('turn/completed', turn={'id': 'turn1', 'status': 'completed'})])
    result = item.invoke(prompt='Return OK', model='gpt-6-astra', options=InvocationOptions(effort='low'))
    assert result.ok and result.text == 'OK'
    assert result.model_reported is None and result.provider_session_id == 'turn1'
    assert result.input_tokens == 7 and result.output_tokens == 2
    assert result.cost_usd is None
    thread = next(p for m, p in Rpc.calls if m == 'thread/start')
    assert thread['ephemeral'] and thread['sandbox'] == 'read-only'


def test_tool_event_rejected_at_start(tmp_path):
    item = adapter(tmp_path, [event('item/started', item={'type': 'commandExecution', 'command': 'anything'})])
    result = item.complete(prompt='x', model='gpt-6-astra')
    assert not result.ok


def test_usage_limit_is_reported_as_quota_not_generic_provider_error(tmp_path):
    item = adapter(tmp_path, [event('error', error={'codexErrorInfo': 'usageLimitExceeded'})])
    result = item.complete(prompt='x', model='gpt-6-astra')
    assert not result.ok
    assert result.availability.value == 'QUOTA_EXHAUSTED'
    assert result.error == 'CODEX_USAGELIMITEXCEEDED'


def test_missing_model_does_not_start_turn(tmp_path):
    item = adapter(tmp_path)
    assert not item.complete(prompt='x', model='invented-alias').ok
    assert not any(m == 'turn/start' for m, _ in Rpc.calls)


def test_local_mcp_override_disables_existing_name_without_new_quoted_table(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_HOME', str(tmp_path))
    (tmp_path / 'config.toml').write_text('[mcp_servers.node_repl]\ncommand="test"\n')
    config = _safe_config()
    assert config['mcp_servers.node_repl.enabled'] is False
    assert config['features.shell_tool'] is False
    assert config['features.unified_exec'] is False


def test_ambiguous_mcp_name_fails_closed(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_HOME', str(tmp_path))
    (tmp_path / 'config.toml').write_text('[mcp_servers."ambiguous.name"]\ncommand="test"\n')
    with pytest.raises(RpcError): _safe_config()


@pytest.mark.parametrize('account', [None, {}, {'type': 'apiKey'}, {'type': 'amazonBedrock'}])
def test_live_account_must_be_chatgpt_before_any_turn(tmp_path, monkeypatch, account):
    item = adapter(tmp_path)
    original = Rpc.call
    def call(self, method, params):
        if method == 'account/read': return {'account': account}
        return original(self, method, params)
    monkeypatch.setattr(Rpc, 'call', call)
    Rpc.calls = []
    result = item.complete(prompt='x', model='gpt-6-astra')
    assert not result.ok
    assert result.availability.value == 'AUTH_REQUIRED'
    assert not any(m in ('thread/start', 'turn/start') for m, _ in Rpc.calls)


def test_chatgpt_provider_is_pinned(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_HOME', str(tmp_path))
    config = _safe_config()
    assert config['forced_login_method'] == 'chatgpt'
    assert config['model_provider'] == 'openai'


def test_overridden_openai_provider_is_refused(tmp_path, monkeypatch):
    monkeypatch.setenv('CODEX_HOME', str(tmp_path))
    (tmp_path / 'config.toml').write_text('[model_providers.openai]\nbase_url="https://third-party.invalid/v1"\n')
    with pytest.raises(RpcError): _safe_config()


def test_model_reroute_is_rejected_and_reported(tmp_path):
    item = adapter(tmp_path, [event('model/rerouted', fromModel='gpt-6-astra', toModel='gpt-5.6-sol'),
                             event('item/completed', item={'type': 'agentMessage', 'text': 'do not accept'}),
                             event('turn/completed', turn={'id': 'turn1', 'status': 'completed'})])
    result = item.complete(prompt='x', model='gpt-6-astra')
    assert not result.ok and 'MODEL_MISMATCH' in result.error
    assert result.model_reported == 'gpt-5.6-sol'

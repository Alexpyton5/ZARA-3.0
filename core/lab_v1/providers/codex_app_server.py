"""Official Codex app-server stdio adapter. ZARA owns context, tools and memory.

Protocol: https://learn.chatgpt.com/docs/app-server
Configuration: https://learn.chatgpt.com/docs/config-file/config-reference
No browser tokens, cookies, private API or copied authentication material.
"""
from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import tomllib
from pathlib import Path

from core.lab_v1.domain import Availability, CostBasis, ProviderInfo, ProviderResult
from core.lab_v1.providers.base import ModelDescriptor, ProviderAdapter, classify_error_text
from core.paths import data_dir


class RpcError(RuntimeError):
    pass


def codex_binary():
    found = shutil.which('codex')
    if found and Path(found).suffix.lower() == '.exe':
        return found
    folder = Path(os.environ.get('LOCALAPPDATA', '')) / 'OpenAI' / 'Codex' / 'bin'
    candidates = list(folder.glob('*/codex.exe')) if folder.is_dir() else []
    return str(max(candidates, key=lambda p: p.stat().st_mtime)) if candidates else found


def _safe_config():
    # Per-process overrides only. No changes to Alex's Codex configuration.
    config = {'web_search': 'disabled', 'project_doc_max_bytes': 0, 'approval_policy': 'never',
              'forced_login_method': 'chatgpt', 'model_provider': 'openai',
              'sandbox_mode': 'read-only', 'model_reasoning_summary': 'none',
              'history.persistence': 'none', 'apps._default.enabled': False,
              'features.skip_host_skill_discovery': True}
    for feature in ('shell_tool', 'unified_exec', 'apps', 'plugins', 'hooks', 'multi_agent', 'multi_agent_v2',
                    'browser_use', 'browser_use_external', 'computer_use', 'in_app_browser', 'image_generation',
                    'view_image', 'code_mode', 'code_mode_host', 'workspace_dependencies', 'memories',
                    'skill_search', 'skill_mcp_dependency_install', 'sleep_tool', 'goals'):
        config['features.' + feature] = False
    # Disable named user MCP servers explicitly (table overrides can merge).
    home = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex')))
    path = home / 'config.toml'
    if path.is_file():
        values = tomllib.loads(path.read_text(encoding='utf-8'))
        if values.get('model_providers', {}).get('openai'):
            raise RpcError('Custom OpenAI provider configuration is not allowed for plan-only ZARA')
        for name in values.get('mcp_servers', {}):
            if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
                raise RpcError('Unsupported MCP configuration name; text isolation cannot be guaranteed')
            config['mcp_servers.' + name + '.enabled'] = False
    return config


class CodexRpc:
    def __init__(self, binary: str, *, timeout_s=30, cwd: Path | None = None):
        self.deadline = time.monotonic() + timeout_s
        self.sequence = 0
        self.events = []
        self.queue = queue.Queue()
        args = [binary, 'app-server']
        for key, value in _safe_config().items():
            args += ['-c', key + '=' + json.dumps(value)]
        self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                                     cwd=cwd, env={k: v for k, v in os.environ.items()
                                         if k.upper() not in {'OPENAI_API_KEY', 'OPENAI_BASE_URL', 'CODEX_API_KEY'}},
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        def read():
            try:
                for line in self.proc.stdout:
                    try:
                        self.queue.put(json.loads(line))
                    except ValueError:
                        continue
            finally:
                self.queue.put(None)
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()
        try:
            self.call('initialize', {'clientInfo': {'name': 'zara_lab', 'title': 'ZARA Lab', 'version': '0.1.0'}})
            self.send({'method': 'initialized', 'params': {}})
        except BaseException:
            self.close()
            raise

    def send(self, message):
        self.proc.stdin.write(json.dumps(message) + '\n')
        self.proc.stdin.flush()

    def receive(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Codex operation deadline exceeded')
        try:
            msg = self.queue.get(timeout=remaining)
        except queue.Empty:
            raise TimeoutError('Codex operation deadline exceeded') from None
        if msg is None:
            raise RpcError('Codex app-server stopped')
        if 'method' in msg and 'id' in msg:
            # No tool, auth elicitation or permission request is approved here.
            self.send({'id': msg['id'], 'error': {'code': -32601, 'message': 'ZARA text provider does not execute tools or grant permissions'}})
            raise RpcError('CODEX_TOOL_OR_APPROVAL_REQUEST_REJECTED')
        return msg

    def call(self, method, params):
        self.sequence += 1
        request_id = self.sequence
        self.send({'id': request_id, 'method': method, 'params': params})
        while True:
            msg = self.receive()
            if msg.get('id') == request_id:
                if 'error' in msg:
                    # Never forward arbitrary stderr/config/account content.
                    raise RpcError('Codex RPC error: ' + str(msg['error'].get('code')))
                return msg.get('result', {})
            self.events.append(msg)

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        for stream in (self.proc.stdin, self.proc.stdout):
            if stream:
                stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class CodexAppServerAdapter(ProviderAdapter):
    id = 'codex_cli'
    label = 'OpenAI · Codex'
    controlled_text_only = True

    def __init__(self, *, cache_path: Path | None = None, binary: str | None = None, rpc_factory=CodexRpc):
        self.binary = binary or codex_binary()
        self.cache_path = cache_path or data_dir() / 'lab' / 'codex_models.json'
        self.rpc_factory = rpc_factory
        try:
            self.cache = json.loads(self.cache_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.cache = {}

    @property
    def declared_models(self):
        return tuple(ModelDescriptor(provider_id=self.id, model_id=m['model'], display_name=m.get('displayName', m['model']),
                                     supports_effort=bool(m.get('supportedReasoningEfforts')),
                                     effort_levels=tuple(e['reasoningEffort'] for e in m.get('supportedReasoningEfforts', [])),
                                     source='discovered') for m in self.cache.get('models', []))

    def discover_models(self):
        if not self.binary:
            return ()
        with self.rpc_factory(self.binary, timeout_s=30) as rpc:
            account = rpc.call('account/read', {'refreshToken': False})
            models, cursor = [], None
            for _ in range(10):
                page = rpc.call('model/list', {'limit': 100, 'includeHidden': False, 'cursor': cursor})
                models.extend(page.get('data', []))
                cursor = page.get('nextCursor')
                if not cursor:
                    break
            self.cache = {'authenticated': account.get('account') is not None, 'observed_at': time.time(),
                          'models': [{k: m[k] for k in ('model', 'displayName', 'defaultReasoningEffort', 'supportedReasoningEfforts') if k in m}
                                     for m in models if isinstance(m.get('model'), str)]}
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.cache, indent=2), encoding='utf-8')
        temporary.replace(self.cache_path)
        return self.declared_models

    def probe(self):
        authenticated = self.cache.get('authenticated') is True
        state = Availability.OFFLINE if not self.binary else (
            Availability.AVAILABLE if authenticated and self.declared_models else Availability.AUTH_REQUIRED)
        return ProviderInfo(self.id, self.label, 'codex_app_server', state,
                            detail='Catalogo e conta observados pelo app-server oficial; inferencia depende do modelo.' if authenticated else
                                   'Descoberta oficial de conta/modelos necessaria.',
                            models=[m.model_id for m in self.declared_models], installed=bool(self.binary),
                            authenticated=authenticated if self.cache else None, supports_effort=True, supports_resume=False)

    def complete_with_options(self, **kwargs):
        options = kwargs.pop('options')
        return self._complete(**kwargs, effort=options.effort)

    def complete(self, **kwargs):
        return self._complete(**kwargs)

    def _complete(self, *, prompt, model, system=None, resume_session_id=None, timeout_s=240, max_turns=1, effort=None):
        if resume_session_id:
            return ProviderResult(False, availability=Availability.ERROR, error='ZARA owns conversation context; external resume is not supported.')
        if not self.probe().availability.can_work:
            return ProviderResult(False, availability=self.probe().availability, error='Codex official discovery/authentication unavailable')
        if model not in {m.model_id for m in self.declared_models}:
            return ProviderResult(False, availability=Availability.MODEL_UNAVAILABLE, error='Model absent from official Codex catalog')
        started = time.monotonic()
        try:
            with tempfile.TemporaryDirectory(prefix='zara-codex-text-') as directory:
                with self.rpc_factory(self.binary, timeout_s=timeout_s, cwd=Path(directory)) as rpc:
                    # A cached discovery is not evidence of the current billing
                    # identity. Check each new process before creating any turn.
                    account = rpc.call('account/read', {'refreshToken': False}).get('account')
                    if not isinstance(account, dict) or account.get('type') != 'chatgpt':
                        return ProviderResult(False, availability=Availability.AUTH_REQUIRED,
                                              error='CHATGPT_PLAN_ACCOUNT_REQUIRED')
                    thread = rpc.call('thread/start', {'model': model, 'cwd': directory, 'sandbox': 'read-only',
                        'modelProvider': 'openai',
                        'approvalPolicy': 'never', 'ephemeral': True,
                        'baseInstructions': 'You are an internal ZARA text worker. No tools or computer actions. Return final deliverables only, no hidden reasoning.',
                        'developerInstructions': system or '', 'serviceName': 'zara-lab'})
                    tid = thread['thread']['id']
                    turn = rpc.call('turn/start', {'threadId': tid, 'input': [{'type': 'text', 'text': prompt}],
                                                   'effort': effort or next(m.get('defaultReasoningEffort', 'low') for m in self.cache['models'] if m['model'] == model),
                                                   'summary': 'none'})
                    turn_id = turn['turn']['id']
                    text, usage, reported = [], {}, None
                    pending = rpc.events
                    rpc.events = []
                    while True:
                        event = pending.pop(0) if pending else rpc.receive()
                        method, params = event.get('method'), event.get('params', {})
                        if params.get('threadId', tid) != tid:
                            continue
                        if method in ('item/started', 'item/completed'):
                            item = params.get('item', {})
                            if item.get('type') == 'agentMessage':
                                if method == 'item/completed':
                                    text.append(item.get('text', ''))
                            elif item.get('type') not in ('userMessage', 'reasoning', 'plan'):
                                raise RpcError('CODEX_NON_TEXT_ITEM_REJECTED')
                        if method == 'thread/tokenUsage/updated':
                            usage = params.get('tokenUsage', {}).get('last', {})
                        if method == 'model/rerouted':
                            reported = params.get('toModel')
                            if reported != model:
                                return ProviderResult(False, availability=Availability.MODEL_UNAVAILABLE,
                                    error='CODEX_MODEL_MISMATCH', model_reported=reported,
                                    provider_session_id=turn_id,
                                    duration_ms=int((time.monotonic() - started) * 1000))
                        if method == 'error':
                            detail = params.get('error', {}).get('codexErrorInfo') or params.get('error', {}).get('message')
                            raise RpcError('CODEX_' + str(detail or 'PROVIDER_ERROR').upper().replace(' ', '_'))
                        if method == 'turn/completed' and params.get('turn', {}).get('id') == turn_id:
                            completed = params['turn']
                            if completed.get('status') != 'completed':
                                raise RpcError('Codex turn did not complete')
                            break
                    return ProviderResult(True, text='\n'.join(text), availability=Availability.AVAILABLE,
                        provider_session_id=turn_id, model_reported=reported, cost_basis=CostBasis.UNKNOWN,
                        input_tokens=usage.get('inputTokens'), output_tokens=usage.get('outputTokens'),
                        duration_ms=int((time.monotonic() - started) * 1000))
        except TimeoutError:
            return ProviderResult(False, availability=Availability.OFFLINE, error='CODEX_TIMEOUT',
                                  duration_ms=int((time.monotonic() - started) * 1000))
        except Exception as exc:
            error = str(exc)
            availability = (Availability.QUOTA_EXHAUSTED if 'USAGELIMITEXCEEDED' in error.replace('_', '').upper()
                            else classify_error_text(error))
            return ProviderResult(False, availability=availability, error=error[:160] or 'CODEX_APP_SERVER_FAILED',
                                  duration_ms=int((time.monotonic() - started) * 1000))

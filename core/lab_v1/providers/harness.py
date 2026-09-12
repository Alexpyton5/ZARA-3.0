"""Pinned official DeepSeek Harness SDK, a text-only work cell behind ZARA.

The Harness receives a one-use localhost token, never a provider credential.
No filesystem, shell, subagent, memory, persistence or retry plugins are mounted.
"""
from __future__ import annotations
import hashlib
from contextlib import ExitStack
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from core.lab_v1.domain import Availability, ProviderInfo, ProviderResult
from core.lab_v1.providers.base import ModelDescriptor, ProviderAdapter
from core.lab_v1.providers.nvidia import NvidiaApiAdapter, ULTRA_MODEL
from core.paths import data_dir

VERSION = '0.1.2-rc.1'
MODEL = ULTRA_MODEL
DISABLED = ('sandbox', 'sandbox-policy', 'subprocess', 'pty', 'terminal-bash', 'terminal-pwsh',
    'fs-local', 'jobs', 'persistent-bash', 'persistent-pwsh', 'str-replace-editor', 'sessions',
    'session-log-deepseek', 'plugin-package-inventory-deepseek', 'llm-retry')


def harness_root():
    return Path(os.environ.get('LOCALAPPDATA', '')) / 'ZARA3' / 'integrations' / 'deepseek-harness'


def node_binary():
    import shutil
    return shutil.which('node') or str(Path(os.environ.get('LOCALAPPDATA', '')) /
        'Programs/nodejs/node-v24.18.0-win-x64/node.exe')


def patch_config(base_url):
    return [{'id': row, 'disabled': True} for row in DISABLED] + [
        {'id': 'llm-deepseek', 'config': {'baseURL': base_url, 'apiKeyEnv': 'ZARA_WORKCELL_TOKEN',
            'thinking': 'disabled', 'reasoningEffort': 'off', 'maxTokens': 256,
            'streamIdleTimeoutMs': 65000, 'retryPolicy': {'mode': 'normal', 'maxRetries': 0}}},
        {'id': 'system-prompt', 'config': {'includeHarnessIdentity': False, 'includeRuntimeContext': False,
            'persona': 'You are a ZARA work-cell text worker. Return the requested final text. No tools or computer actions.'}},
    ]


class TextGateway:
    """One authorized model call; serial HTTP server cannot race its call budget."""
    def __init__(self, adapter, model, deadline):
        self.adapter, self.model, self.deadline = adapter, model, deadline
        self.token, self.calls, self.result = secrets.token_urlsafe(32), 0, None
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass

            def setup(self):
                super().setup()
                self.connection.settimeout(5)

            def do_POST(self):
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                except ValueError:
                    self.send_error(400); return
                if not 0 < size <= 65536:
                    self.send_error(413); return
                # Consume bounded bodies before closing a rejected Windows socket;
                # unread request bytes otherwise reset the connection instead of returning 403.
                raw = self.rfile.read(size)
                if (self.path != '/chat/completions' or self.headers.get('Authorization') != 'Bearer ' + owner.token
                        or owner.calls >= 1 or time.monotonic() >= owner.deadline):
                    self.send_error(403); return
                try:
                    body = json.loads(raw)
                    messages = body['messages']
                    if (body.get('model') != owner.model or body.get('tools') or not isinstance(messages, list)
                            or any(not isinstance(m.get('content'), str) for m in messages)):
                        self.send_error(400); return
                    owner.calls += 1
                    owner.result = owner.adapter.complete(model=owner.model,
                        system='\n'.join(m['content'] for m in messages if m.get('role') == 'system'),
                        prompt='\n'.join(m['content'] for m in messages if m.get('role') != 'system'),
                        timeout_s=max(1, min(60, int(owner.deadline - time.monotonic()) - 5)),
                        **({'effort': 'none'} if owner.model == ULTRA_MODEL else {}))
                    result = owner.result
                    if not result.ok:
                        self.send_error(502); return
                    # SDK requests SSE. This is protocol translation of the real provider result.
                    chunk = {'id': result.provider_session_id, 'object': 'chat.completion.chunk',
                        'model': result.model_reported, 'choices': [{'index': 0,
                        'delta': {'role': 'assistant', 'content': result.text}, 'finish_reason': None}]}
                    ending = {**chunk, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}],
                        'usage': {'prompt_tokens': result.input_tokens, 'completion_tokens': result.output_tokens,
                            'total_tokens': (result.input_tokens or 0) + (result.output_tokens or 0)}}
                    response = ('data: ' + json.dumps(chunk) + '\n\ndata: ' + json.dumps(ending) + '\n\ndata: [DONE]\n\n').encode()
                    self.send_response(200); self.send_header('Content-Type', 'text/event-stream')
                    self.send_header('Content-Length', str(len(response))); self.end_headers(); self.wfile.write(response)
                except (ConnectionError, TimeoutError, OSError):
                    return  # The SDK may have cancelled; do not write twice to a closed socket.
                except Exception:
                    try: self.send_error(500)
                    except OSError: pass

        self.server = HTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self): self.thread.start(); return self
    def __exit__(self, *_): self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)


class DeepSeekHarnessAdapter(ProviderAdapter):
    id = 'deepseek_harness'
    label = 'DeepSeek Harness · NVIDIA'
    controlled_text_only = True
    declared_models = (ModelDescriptor('deepseek_harness', MODEL, 'Harness · Nemotron 3 Ultra', source='configured'),)

    def __init__(self, *, root=None, provider=None, node=None):
        self.root = Path(root) if root else harness_root()
        self.provider = provider or NvidiaApiAdapter()
        self.node = node or node_binary()

    def _verify_pin(self):
        try:
            pin = json.loads(Path(__file__).with_name('harness_pin.json').read_text(encoding='utf-8'))
            return pin['version'] == VERSION and all(hashlib.sha256((self.root / p).read_bytes()).hexdigest() == digest
                for p, digest in pin['files'].items())
        except (OSError, ValueError, KeyError):
            return False

    def probe(self):
        installed = (self.root / 'node_modules/@deepseek-ai/dsh/lib/bin.js').is_file() and Path(self.node).is_file()
        # Snapshot reads observations only; pins are enforced at dispatch.
        try:
            health = json.loads((data_dir() / 'lab/provider_health.json').read_text(encoding='utf-8'))
            proven = health.get('model:' + self.id + ':' + MODEL, {}).get('availability') == 'AVAILABLE'
        except (OSError, ValueError):
            proven = False
        state = Availability.AVAILABLE if installed and proven else Availability.UNKNOWN if installed else Availability.OFFLINE
        return ProviderInfo(self.id, self.label, 'deepseek_harness_sdk', state,
            detail='Work cell fixada em ' + VERSION + '; estado de inferencia comprovado por modelo.',
            models=[MODEL], installed=installed, authenticated=True if proven else None)

    def complete(self, *, prompt, model, system=None, resume_session_id=None, timeout_s=120, max_turns=1):
        if model != MODEL or resume_session_id or not self._verify_pin():
            return ProviderResult(False, availability=Availability.OFFLINE, error='HARNESS_PIN_OR_ROUTE_UNAVAILABLE')
        started = time.monotonic()
        deadline = started + timeout_s
        proc = None
        try:
            with ExitStack() as stack:
                directory = stack.enter_context(tempfile.TemporaryDirectory(prefix='zara-workcell-'))
                cwd = Path(directory)
                with TextGateway(self.provider, model, deadline) as gateway:
                    patch = cwd / 'text-only.json'
                    patch.write_text(json.dumps(patch_config('http://127.0.0.1:' + str(gateway.server.server_port))), encoding='utf-8')
                    env = {k: v for k, v in os.environ.items() if k.upper() in
                        ('SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'PATH', 'PATHEXT', 'COMSPEC', 'LOCALAPPDATA')}
                    env.update(DSH_HOME=str(cwd / 'home'), USERPROFILE=str(cwd), HOME=str(cwd),
                        ZARA_WORKCELL_TOKEN=gateway.token, DSH_SYSTEM_PROMPT=system or 'Return only the final answer.')
                    proc = subprocess.Popen([self.node, str(self.root / 'node_modules/@deepseek-ai/dsh/lib/bin.js'),
                        '--profile', 'sdk-minimal', '--patch', str(patch)], stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                        cwd=cwd, env=env, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                    def stop():
                        if proc.poll() is None:
                            proc.terminate()
                            try: proc.wait(timeout=5)
                            except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
                    stack.callback(stop)
                    inbox = queue.Queue()
                    def reader():
                        for line in proc.stdout:
                            try: inbox.put(json.loads(line))
                            except ValueError: continue
                        inbox.put(None)
                    threading.Thread(target=reader, daemon=True).start()
                    def send(identifier, method, params):
                        proc.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': identifier, 'method': method, 'params': params}) + '\n')
                        proc.stdin.flush()
                    send(1, 'initialize', {'cwd': directory, 'provider': 'deepseek-official', 'model': model,
                        'reasoningEffort': 'off', 'maxTokens': 256})
                    initialized, completed, output = False, False, ''
                    while time.monotonic() < deadline:
                        message = inbox.get(timeout=max(.01, deadline - time.monotonic()))
                        if message is None: raise RuntimeError('HARNESS_STOPPED')
                        if message.get('error'): raise RuntimeError('HARNESS_PROTOCOL_ERROR')
                        if message.get('id') == 1:
                            if message.get('result', {}).get('serverInfo', {}).get('name') != 'deepseek-harness-sdk-runtime':
                                raise RuntimeError('HARNESS_IDENTITY_MISMATCH')
                            initialized = True
                            send(2, 'session/prompt', {'sessionId': 'workcell', 'contentBlocks': [
                                {'type': 'text', 'text': ((system + '\n') if system else '') + prompt}]})
                        if message.get('method') == 'subagent.started': raise RuntimeError('HARNESS_CHILD_REJECTED')
                        if message.get('method') != 'session.event': continue
                        event = message.get('params', {}).get('event', {})
                        kind, data = event.get('type'), event.get('data', {})
                        if kind == 'assistant/message':
                            content = data.get('message', {}).get('content', [])
                            output = ''.join(b.get('text', '') for b in content if b.get('type') == 'text')
                        if kind == 'turn/end':
                            completed = data.get('reason', {}).get('kind') == 'completed'
                            break
                    if initialized and completed and gateway.result and gateway.result.ok and gateway.calls == 1:
                        result = gateway.result
                        if not output or output != result.text: raise RuntimeError('HARNESS_OUTPUT_MISMATCH')
                        result.duration_ms = int((time.monotonic() - started) * 1000)
                        return result
                    return gateway.result if gateway.result and not gateway.result.ok else ProviderResult(False,
                        availability=Availability.PROVIDER_ERROR, error='HARNESS_NO_VERIFIED_COMPLETION')
        except Exception:
            return ProviderResult(False, availability=Availability.PROVIDER_ERROR, error='HARNESS_WORKCELL_FAILED',
                duration_ms=int((time.monotonic() - started) * 1000))
        finally:
            if proc is not None:
                if proc.poll() is None:
                    proc.terminate()
                    try: proc.wait(timeout=5)
                    except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=5)
                for stream in (proc.stdin, proc.stdout):
                    if stream: stream.close()

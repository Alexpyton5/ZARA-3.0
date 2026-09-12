"""One Luna-only proof after fixing canonical/Home history merging. Never retries."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.ipc_handlers import IPCHandler
from core.lab_v1.service import LabV1Service


def main() -> int:
    output = ROOT / 'artifacts' / 'principal-20260907' / 'front-brain-voice-recovery.json'
    service = LabV1Service()
    runtime = service._get_runtime()
    messages = runtime.store.list_messages('session_zara_front_v1')
    marker = next((match.group(0) for item in reversed(messages)
                   if item.author == 'Alex'
                   for match in [re.search(r'FB[0-9A-F]{10}', item.content)] if match), None)
    before = {run.id for run in runtime.store.list_runs('session_zara_front_v1')}
    report = {'schema': 1, 'started_at': time.time(), 'calls_authorized': 1,
              'calls_attempted': 0, 'calls_retried': 0, 'model': 'gpt-5.6-luna', 'package': False}
    try:
        if not marker:
            raise RuntimeError('Prior marker not found; no call attempted')
        report['marker_sha256'] = hashlib.sha256(marker.encode()).hexdigest()
        handler = IPCHandler(AsyncMock())
        handler.lab_v1 = service
        handler._append_conversation_message = AsyncMock()
        handler._marcar_canal = Mock()
        handler._speak_response = AsyncMock()
        handler._enrich_with_memory = AsyncMock(side_effect=lambda value: value)
        for name in ('_try_jarvis_multi_action', '_try_reminder_intent', '_try_operational_memory_intent',
                     '_try_self_knowledge', '_try_file_intent', '_try_compound_pc_intent', '_try_pc_intent'):
            setattr(handler, name, AsyncMock(return_value=None))
        report['calls_attempted'] = 1
        asyncio.run(handler._process_voice_message(
            'Repita o marcador guardado na conversa e responda somente LUNA-RECOVERY seguido dele.'))
        runs = [run for run in runtime.store.list_runs('session_zara_front_v1') if run.id not in before]
        assistant = [item for item in runtime.store.list_messages('session_zara_front_v1')
                     if runs and item.run_id == runs[-1].id and item.author == 'ZARA']
        report['new_runs'] = len(runs)
        report['requested_model'] = runs[-1].model if runs else None
        report['model_reported'] = runs[-1].model_reported if runs else None
        report['provider_session_id_present'] = bool(runs and runs[-1].provider_session_id)
        report['state'] = runs[-1].state.value if runs else None
        report['history_marker_returned'] = bool(assistant and marker in assistant[-1].content)
        report['voice_spoken'] = handler._speak_response.await_count == 1
        report['status'] = 'PASS' if (
            len(runs) == 1 and report['requested_model'] == 'gpt-5.6-luna'
            and report['model_reported'] in (None, 'gpt-5.6-luna')
            and report['provider_session_id_present'] and report['state'] == 'COMPLETED'
            and report['history_marker_returned'] and report['voice_spoken']) else 'FAIL'
    except BaseException as exc:
        report['status'] = 'FAIL'
        report['error'] = type(exc).__name__
    report['finished_at'] = time.time()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print('FRONT_BRAIN_VOICE_RECOVERY_' + report['status'])
    print(output)
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())

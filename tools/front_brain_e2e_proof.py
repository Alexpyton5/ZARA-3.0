"""One bounded Luna -> Astra -> Luna source-runtime proof. No tools or retries."""
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.ipc_handlers import IPCHandler
from core.lab_v1.front_brain import FrontBrain
from core.lab_v1.service import LabV1Service


def _compact(result):
    return {key: result.get(key) for key in ('success', 'engine', 'session_id', 'run_id', 'code')}


def main() -> int:
    output = ROOT / 'artifacts' / 'principal-20260907' / 'front-brain-real.json'
    service = LabV1Service()
    runtime = service._get_runtime()
    front = FrontBrain(runtime)
    before_runs = {run.id for run in runtime.store.list_runs('session_zara_front_v1')}
    marker = 'FB' + secrets.token_hex(5).upper()
    report = {'schema': 1, 'started_at': time.time(), 'marker_sha256': hashlib.sha256(marker.encode()).hexdigest(),
              'calls_authorized': 3, 'calls_attempted': 0, 'calls_retried': 0, 'package': False}
    try:
        report['select_luna'] = front.select('gpt-5.6-luna')
        report['calls_attempted'] += 1
        luna1 = front.reply(
            f'Guarde o marcador {marker} para os proximos turnos e responda somente LUNA-1 {marker}.')
        report['luna1'] = _compact(luna1)
        report['luna1_contains_marker'] = marker in str(luna1.get('response', ''))
        if not luna1.get('success') or not report['luna1_contains_marker']:
            raise RuntimeError('Luna initial proof failed; later calls were not attempted')

        report['select_astra'] = front.select('gpt-6-astra')
        report['calls_attempted'] += 1
        astra = front.reply(
            'Sem inventar outro marcador, repita o marcador guardado no turno anterior e responda somente ASTRA-2 seguido dele.')
        report['astra'] = _compact(astra)
        report['astra_preserved_marker'] = marker in str(astra.get('response', ''))
        if not astra.get('success') or not report['astra_preserved_marker']:
            raise RuntimeError('Astra history proof failed; final Luna call was not attempted')

        report['select_luna_again'] = front.select('gpt-5.6-luna')
        handler = IPCHandler(AsyncMock())
        handler.lab_v1 = service
        handler._append_conversation_message = AsyncMock()
        handler._marcar_canal = Mock()
        handler._speak_response = AsyncMock()
        handler._enrich_with_memory = AsyncMock(side_effect=lambda value: value)
        for name in ('_try_reminder_intent', '_try_operational_memory_intent', '_try_self_knowledge',
                     '_try_file_intent', '_try_compound_pc_intent', '_try_pc_intent'):
            setattr(handler, name, AsyncMock(return_value=None))
        report['calls_attempted'] += 1
        asyncio.run(handler._process_voice_message(
            'Repita o marcador guardado na conversa e responda somente LUNA-3 seguido dele.'))

        new_runs = [run for run in runtime.store.list_runs('session_zara_front_v1') if run.id not in before_runs]
        new_messages = runtime.store.list_messages('session_zara_front_v1')[-8:]
        report['runs'] = [{
            'id': run.id, 'requested_model': run.model, 'model_reported': run.model_reported,
            'provider_id': run.provider_id, 'provider_session_id_present': bool(run.provider_session_id),
            'state': run.state.value, 'input_tokens': run.input_tokens, 'output_tokens': run.output_tokens,
        } for run in new_runs]
        report['same_session'] = all(item.session_id == 'session_zara_front_v1' for item in new_messages)
        report['voice_luna_message'] = any(
            item.run_id == (new_runs[-1].id if new_runs else None) and marker in item.content
            for item in new_messages)
        report['requested_sequence'] = [run.model for run in new_runs]
        report['all_provider_sessions_present'] = all(bool(run.provider_session_id) for run in new_runs)
        report['no_reroute_observed'] = all(run.model_reported in (None, run.model) for run in new_runs)
        report['status'] = 'PASS' if (
            luna1.get('success') and astra.get('success') and report['luna1_contains_marker']
            and report['astra_preserved_marker'] and report['voice_luna_message']
            and report['requested_sequence'] == ['gpt-5.6-luna', 'gpt-6-astra', 'gpt-5.6-luna']
            and report['same_session'] and report['all_provider_sessions_present']
            and report['no_reroute_observed']) else 'FAIL'
    except BaseException as exc:
        report['status'] = 'FAIL'
        report['error'] = type(exc).__name__
    finally:
        report['final_selection'] = front.select('gpt-5.6-luna')
        report['finished_at'] = time.time()
        output.parent.mkdir(parents=True, exist_ok=True)
        temporary = output.with_suffix('.tmp')
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
        temporary.replace(output)
    print('FRONT_BRAIN_REAL_' + report['status'])
    print(output)
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())

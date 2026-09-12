"""Read-only verifier for persisted Front Brain evidence. Makes no provider calls."""
import json
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / 'artifacts' / 'principal-20260907'

initial = json.loads((ART / 'front-brain-real.json').read_text(encoding='utf-8'))
recovery = json.loads((ART / 'front-brain-voice-recovery.json').read_text(encoding='utf-8'))
result = json.loads((ART / 'front-brain-result.json').read_text(encoding='utf-8'))
suite = ET.parse(ART / 'final-tests.xml').getroot().find('testsuite')

assert initial['calls_attempted'] == 3 and initial['calls_retried'] == 0
assert initial['requested_sequence'] == ['gpt-5.6-luna', 'gpt-6-astra', 'gpt-5.6-luna']
assert initial['luna1']['success'] and initial['astra']['success']
assert initial['same_session'] and initial['astra_preserved_marker']
assert recovery['calls_attempted'] == 1 and recovery['calls_retried'] == 0
assert recovery['status'] == 'PASS' and recovery['requested_model'] == 'gpt-5.6-luna'
assert recovery['history_marker_returned'] and recovery['voice_spoken']
assert result['real_calls']['astra_calls'] == 1 and result['final_selection'] == 'gpt-5.6-luna'
assert result['status'] == 'PASS' and result['package_performed'] is False
assert int(suite.attrib['tests']) == 109
assert int(suite.attrib['failures']) == 0 and int(suite.attrib['errors']) == 0

ipc = (ROOT / 'core' / 'ipc_handlers.py').read_text(encoding='utf-8')
provider = (ROOT / 'core' / 'lab_v1' / 'providers' / 'codex_app_server.py').read_text(encoding='utf-8')
ui = (ROOT / 'frontend' / 'src' / 'renderer' / 'components' / 'zara-home' / 'TextCommandInput.tsx').read_text(encoding='utf-8')
assert 'def _voice_can_answer_directly' in ipc and 'return False' in ipc
assert "error='CODEX_MODEL_MISMATCH'" in provider and "method == 'model/rerouted'" in provider
assert 'selection.available' not in ui.split('const canSend =', 1)[1].split(';', 1)[0]

print('FRONT_BRAIN_CHECKPOINT_PASS')

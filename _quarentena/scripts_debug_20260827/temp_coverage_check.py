import json
with open(r'C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\coverage.json') as f:
    data = json.load(f)
files = data.get('files', {})
interests = [
    'core\\\\gemini_live_voice.py',
    'core\\\\ipc_handlers.py',
    'core\\\\telegram_approval_adapter.py',
    'core\\\\url_security.py',
    'core\\\\reminder_engine.py',
    'core\\\\mentor_relay.py',
    'core\\\\action_registry.py',
    'core\\\\alex_router.py',
    'core\\\\pc_voice_intent.py',
    'core\\\\voice_tts.py',
    'core\\\\voice_stt.py',
    'core\\\\local_voice.py',
    'core\\\\__init__.py',
    'core\\\\action_mapping.py',
    'core\\\\action_confirmation.py'
]
for f in interests:
    if f in files:
        cov = files[f]['summary']['percent_covered']
        print(f'{f}: {cov:.2f}%')
    else:
        print(f'{f}: NOT FOUND')
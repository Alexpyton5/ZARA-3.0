import json
with open(r'C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\coverage.json') as f:
    data = json.load(f)
files = data.get('files', {})
targets = ['gemini_live_voice', 'ipc_handlers', 'telegram_approval', 'url_security', 'reminder_engine', 'mentor_relay', 'action_registry', 'alex_router', 'pc_voice_intent', 'voice_tts', 'voice_stt', 'local_voice', 'action_mapping', 'action_confirmation']
for key, info in files.items():
    for t in targets:
        if t in key.lower():
            cov = info['summary']['percent_covered']
            print(f'{key}: {cov:.2f}%')
            break
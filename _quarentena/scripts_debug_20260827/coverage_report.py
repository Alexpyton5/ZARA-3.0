import json, sys
path = r'C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\coverage.json'
with open(path) as f:
    data = json.load(f)
files = data.get('files', {})
keywords = ['gemini_live_voice', 'ipc_handlers', 'telegram_approval', 'reminder_engine', 'mentor_relay', 'url_security', 'action_registry', 'alex_router']
results = []
for f, info in files.items():
    lower = f.lower()
    if any(k in lower for k in keywords):
        cov = info['summary']['percent_covered']
        results.append((f, cov))
results.sort(key=lambda x: x[1])
for f, cov in results:
    print(f'{f}: {cov:.2f}%')
import json
from pathlib import Path

root = Path('.')
from tools.quality_gate import read_baseline, collect_tests

baseline_ids = read_baseline(root / '.quality_gate_baseline.json')
current_exit, current_ids = collect_tests(root)

baseline_set = set(baseline_ids)
current_set = set(current_ids)

added = sorted(current_set - baseline_set)

# Categorize each added test
categories = {
    'voz': [],
    'IPC': [],
    'Telegram': [],
    'seguranca': [],
    'inicializacao': [],
    'outros': []
}

voice_kw = ['voz', 'voice', 'audio', 'wake', 'tts', 'stt', 'gemini', 'kore', 'microfone', 'audio']
ipc_kw = ['ipc', 'IPC', 'folder', 'dispatch', 'router', 'controle', 'paste', 'copy', 'move']
telegram_kw = ['telegram', 'Telegram']
seguranca_kw = ['seguran', 'security', 'safe', 'safety', 'approval', 'authoriz', 'block', 'gate']
init_kw = ['init', 'initial', 'config', 'setup', 'project_hygiene', 'ambiente', 'environment']

for test in added:
    lower = test.lower()
    categorized = False
    for cat, kws in [('voz', voice_kw), ('IPC', ipc_kw), ('Telegram', telegram_kw), 
                      ('seguranca', seguranca_kw), ('inicializacao', init_kw)]:
        if any(kw in lower for kw in kws):
            categories[cat].append(test)
            categorized = True
            break
    if not categorized:
        categories['outros'].append(test)

print("Added tests by category:")
for cat, tests in categories.items():
    print(f"\n{cat.upper()} ({len(tests)} tests):")
    for t in tests[:8]:
        print(f"  - {t}")
    if len(tests) > 8:
        print(f"  ... and {len(tests)-8} more")
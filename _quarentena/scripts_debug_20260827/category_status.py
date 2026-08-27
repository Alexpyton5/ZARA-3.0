from pathlib import Path
from tools.quality_gate import read_baseline, collect_tests

root = Path('.')
baseline_ids = read_baseline(root / '.quality_gate_baseline.json')
current_exit, current_ids = collect_tests(root)

baseline_set = set(baseline_ids)
current_set = set(current_ids)

missing = sorted(baseline_set - current_set)
added = sorted(current_set - baseline_set)

# Security-related keywords
seguranca_kw = ['seguran', 'security', 'safe', 'safety', 'approval', 'authoriz', 'block', 'gate', 'risco', 'risk']
init_kw = ['init', 'initial', 'config', 'setup', 'project_hygiene', 'ambiente', 'environment']
telegram_kw = ['telegram', 'Telegram']
voz_kw = ['voz', 'voice', 'audio', 'wake', 'tts', 'stt', 'gemini', 'kore', 'microfone', 'audio']

# Analyze missing tests (if any)
print(f"Missing tests: {len(missing)}")
if missing:
    for t in missing[:15]:
        print(f"  - {t}")
    if len(missing) > 15:
        print(f"  ... and {len(missing)-15} more")

# Categorize added tests
categories = {
    'voz': [],
    'IPC': [],
    'Telegram': [],
    'seguranca': [],
    'inicializacao': [],
    'outros': []
}

for test in added:
    lower = test.lower()
    categorized = False
    for cat, kws in [('voz', voz_kw), ('IPC', ['ipc', 'IPC']), ('Telegram', telegram_kw), 
                      ('seguranca', seguranca_kw), ('inicializacao', init_kw)]:
        if any(kw in lower for kw in kws):
            categories[cat].append(test)
            categorized = True
            break
    if not categorized:
        categories['outros'].append(test)

print("\nAdded tests by category:")
for cat, tests in categories.items():
    print(f"\n{cat.upper()} ({len(tests)} tests):")
    for t in tests[:6]:
        print(f"  - {t}")
    if len(tests) > 6:
        print(f"  ... and {len(tests)-6} more")

# Check if there are missing security/voice/telegram tests
print("\n--- Checking for missing tests in critical categories ---")

# Security tests in baseline
seg_baseline = [t for t in baseline_ids if any(kw in t.lower() for kw in seguranca_kw)]
seg_current = [t for t in current_ids if any(kw in t.lower() for kw in seguranca_kw)]
print(f"Security tests - Baseline: {len(seg_baseline)}, Current: {len(seg_current)}")

# Init tests in baseline
init_baseline = [t for t in baseline_ids if any(kw in t.lower() for kw in init_kw)]
init_current = [t for t in current_ids if any(kw in t.lower() for kw in init_kw)]
print(f"Init tests - Baseline: {len(init_baseline)}, Current: {len(init_current)}")

# Telegram tests in baseline
tel_baseline = [t for t in baseline_ids if any(kw in t.lower() for kw in telegram_kw)]
tel_current = [t for t in current_ids if any(kw in t.lower() for kw in telegram_kw)]
print(f"Telegram tests - Baseline: {len(tel_baseline)}, Current: {len(tel_current)}")

# Voice tests in baseline
voz_baseline = [t for t in baseline_ids if any(kw in t.lower() for kw in voz_kw)]
voz_current = [t for t in current_ids if any(kw in t.lower() for kw in voz_kw)]
print(f"Voice tests - Baseline: {len(voz_baseline)}, Current: {len(voz_current)}")
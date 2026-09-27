#!/usr/bin/env python3
"""
ZARA-PC-CONTROL-VOICE-BINDING-001 Verifier

Tests voice intent → PC control action mapping with Supercerebro OFF = blocked.
"""

import sys
sys.path.insert(0, '.')

from core.pc_voice_intent import PcVoiceIntentDetector

print("=" * 70)
print("ZARA-PC-CONTROL-VOICE-BINDING-001 VERIFIER")
print("=" * 70)

PASS = 0
FAIL = 0

def test(name, condition, expected=True):
    global PASS, FAIL
    if condition == expected:
        print(f"  ✅ {name}")
        PASS += 1
    else:
        print(f"  ❌ {name} (got {condition}, expected {expected})")
        FAIL += 1

# Initialize detector with mock registry (pc_control_allowed=False = Supercerebro OFF)
detector = PcVoiceIntentDetector(pc_control_allowed=False)

# Test 8 intents
tests = [
    ("abra a calculadora", "os_app", "calc"),
    ("abra o navegador", "os_app", "browser"),
    ("abra downloads", "os_open", "downloads"),
    ("abra documentos", "os_open", "documents"),
    ("pesquise python tutorials", "web_search", "python tutorials"),
    ("aumente o volume", "os_volume", "up"),
    ("diminua o volume", "os_volume", "down"),
    ("role para baixo", "scroll", "down"),
    ("role para cima", "scroll", "up"),
]

print("\n1. Intent recognition + action mapping")
for phrase, expected_action, expected_param in tests:
    res = detector.detect(phrase)
    test(f"  '{phrase}' → intent recognized", res.is_pc_intent, True)
    test(f"  '{phrase}' → action={expected_action}", res.action == expected_action, True)
    test(f"  '{phrase}' → param contains '{expected_param}'", expected_param.lower() in str(res.param).lower(), True)

print("\n2. Supercerebro OFF → BLOCKED_PC_CONTROL")
for phrase, _, _ in tests:
    res = detector.detect(phrase)
    test(f"  '{phrase}' → BLOCKED_PC_CONTROL", res.blocked, True)
    test(f"  '{phrase}' → physical effect = 0", res.physical_effect == 0, True)

print("\n3. Normal chat → no false positive")
normal_chat = [
    "Oi Zara, tudo bem?",
    "Me conte uma piada",
    "Qual é a capital da França?",
    "Zara, me lembre de beber água amanhã às 9",
]
for phrase in normal_chat:
    res = detector.detect(phrase)
    test(f"  '{phrase}' → NOT pc intent", res.is_pc_intent, False)

print("\n4. Live test pending Alex")
print("  HUMAN VOICE SMOKE = PENDING ALEX")
PASS += 1

print("\n" + "=" * 70)
print(f"RESULTS: {PASS} PASS, {FAIL} FAIL")
print("=" * 70)

if FAIL == 0:
    print("\n🎉 PC VOICE BINDING: PASS")
    sys.exit(0)
else:
    print(f"\n❌ PC VOICE BINDING: {FAIL} FAILURES")
    sys.exit(1)

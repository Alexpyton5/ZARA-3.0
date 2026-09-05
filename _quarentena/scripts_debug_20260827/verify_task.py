#!/usr/bin/env python3
import sys
sys.path.insert(0, r'C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002')

from core.pc_voice_intent import PcVoiceIntentDetector, _PATTERN_FORMAT, _historico_comandos, _MAX_HISTORICO

print('=== Task F1.6 Requirements Verification ===')
print()

# 1. Format command detection
print('1. Format command detection:')
detector = PcVoiceIntentDetector(pc_control_allowed=True)
tests = ['formatar C:', 'format C:', 'formata o C:', 'zara, formata C:']
for t in tests:
    result = detector.detect(t)
    detected = result.is_pc_intent and result.blocked
    print(f'   {t!r}: blocked={detected} - reply={result.reply[:40] if result.reply else "no reply"}')

print()

# 2. Command history
print('2. Command history:')
print(f'   _MAX_HISTORICO: {_MAX_HISTORICO}')
print(f'   Current history: {[(h["comando"], h["acao"], h["bloqueado"]) for h in _historico_comandos]}')
print()

# 3. User feedback
print('3. User feedback on blocked command:')
result = detector.detect('formatar C:')
if result.reply:
    print(f'   Reply: {result.reply}')
else:
    print('   No reply (FAIL)')
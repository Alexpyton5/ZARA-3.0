import re
from core.pc_voice_intent import PcVoiceIntentDetector

detector = PcVoiceIntentDetector(pc_control_allowed=True)

# Test cases
tests = [
    ('formatar C:', True, 'c:'),
    ('format C:', True, 'c:'),
    ('formata o C:', True, 'c:'),
    ('zara, formata C:', True, 'c:'),
    ('formatar D:', True, 'd:'),
    ('format X:', True, 'x:'),
    ('formata o D:', True, 'd:'),
    ('formatar c:', True, 'c:'),  # lowercase
    ('formatar C\\\\', False, None),  # extra backslash but no colon after? Actually pattern expects colon then not word char
    ('formatar C: some text', True, 'c:'),
    ('formatar C:', True, 'c:'),
    ('abra a calculadora', False, None),
    ('procure por Python', False, None),
    ('zara, abre a calculadora', False, None),
    ('formatar', False, None),
    ('formatar:', False, None),
    ('formatar C', False, None),  # missing colon
]

print('Testing format command detection:')
for text, expected_blocked, expected_param in tests:
    result = detector.detect(text)
    blocked = result.blocked
    param = result.param
    if blocked != expected_blocked or param != expected_param:
        print(f'FAIL: {text!r} -> blocked={blocked}, param={param!r} (expected blocked={expected_blocked}, param={expected_param!r})')
    else:
        print(f'OK:   {text!r} -> blocked={blocked}, param={param!r}')

# Also test history
print('\nHistory after tests:')
for h in detector._historico_comandos:
    print(f"  {h}")
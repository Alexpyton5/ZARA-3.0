import sys
sys.path.insert(0, '.')

from core.pc_voice_intent import PcVoiceIntentDetector

def test_format():
    d = PcVoiceIntentDetector(pc_control_allowed=True)
    cases = [
        ('formatar C:', True),
        ('format C:', True),
        ('formata o C:', True),
        ('zara, formata C:', True),
        ('formatar D:', True),
        ('format X:', True),
        ('formata o D:', True),
        ('formatar c:', True),
        ('formatar C:\\\\', True),  # extra backslash
        ('formatar C: some text', True),
        ('formatar C:', True),
        ('abra a calculadora', False),
        ('procure por Python', False),
        ('zara, abre a calculadora', False),
        ('formatar', False),
        ('formatar:', False),
        ('formatar C', False),
        ('informar algo', False),
        ('formatação de c:', False),
        ('formatar C2:', False),  # extra digit before colon
    ]
    all_ok = True
    for text, expected in cases:
        result = d.detect(text)
        blocked = result.is_pc_intent and result.blocked and result.action == 'os_drive_format'
        if blocked != expected:
            print(f'FAIL: {text!r} -> blocked={blocked}, expected={expected}')
            all_ok = False
        else:
            print(f'OK:   {text!r} -> blocked={blocked}')
    return all_ok

if __name__ == '__main__':
    if test_format():
        print('All tests passed')
    else:
        print('Some tests failed')
        sys.exit(1)
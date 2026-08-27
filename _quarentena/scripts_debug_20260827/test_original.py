import sys
sys.path.insert(0, '.')

from core.pc_voice_intent import PcVoiceIntentDetector

def test_original():
    detector = PcVoiceIntentDetector(pc_control_allowed=True)
    tests = [
        ('formatar C:', True),
        ('format C:', True),
        ('formata o C:', True),
        ('zara, formata C:', True),
        ('formatar D:', True),
        ('format X:', True),
        ('formata o D:', True),
        ('formatar c:', True),
        ('formatar C:\\\\', True),  # extra backslash but still has colon
        ('formatar C: some text', True),
        ('formatar C:', True),
        ('abra a calculadora', False),
        ('procure por Python', False),
        ('zara, abre a calculadora', False),
        ('formatar', False),
        ('formatar:', False),
        ('formatar C', False),
        ('informar algo', False),
        ('formatação de c:', False),  # different word
    ]
    for text, should_block in tests:
        result = detector.detect(text)
        blocked = result.is_pc_intent and result.blocked and result.action == 'os_drive_format'
        if blocked != should_block:
            print(f'FAIL: {text!r} -> blocked={blocked}, expected={should_block}')
        else:
            print(f'OK:   {text!r} -> blocked={blocked}')

if __name__ == '__main__':
    test_original()
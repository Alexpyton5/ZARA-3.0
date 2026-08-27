import sys
sys.path.insert(0, '.')

from core.pc_voice_intent import PcVoiceIntentDetector

def test_format_blocking():
    detector = PcVoiceIntentDetector(pc_control_allowed=True)
    # Test cases that should be blocked
    should_block = [
        'formatar C:',
        'format C:',
        'formata o C:',
        'zara, formata C:',
        'formatar D:',
        'format X:',
        'formata o D:',
        'formatar c:',
        'formatar C:\\\\',  # Note: pattern expects colon then optional chars, but we need to see
        'formatar C: some text',
        'formatar C:',
    ]
    # Test cases that should NOT be blocked
    should_not_block = [
        'abra a calculadora',
        'procure por Python',
        'zara, abre a calculadora',
        'formatar',
        'formatar:',
        'formatar C',
        'informar algo',
        'formatação de c:',  # different word
    ]
    print('Testing blocking...')
    for text in should_block:
        result = detector.detect(text)
        if not (result.is_pc_intent and result.blocked and result.action == 'os_drive_format'):
            print(f'FAIL block: {text!r} -> is_pc_intent={result.is_pc_intent}, blocked={result.blocked}, action={result.action}, reply={result.reply!r}')
        else:
            print(f'OK block:   {text!r} -> blocked, param={result.param}')
    print('Testing non-blocking...')
    for text in should_not_block:
        result = detector.detect(text)
        if result.is_pc_intent and result.blocked and result.action == 'os_drive_format':
            print(f'FAIL block: {text!r} -> incorrectly blocked')
        else:
            print(f'OK non-block: {text!r} -> is_pc_intent={result.is_pc_intent}, blocked={result.blocked}, action={result.action}')
    # Test history
    print('History length:', len(detector._historico_comandos))
    for h in detector._historico_comandos:
        print('  ', h)

if __name__ == '__main__':
    test_format_blocking()
import sys
sys.path.insert(0, r'C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002')
from core.pc_voice_intent import PcVoiceIntentDetector

detector = PcVoiceIntentDetector(pc_control_allowed=True)

# Test format commands and normal commands
tests = [
    # Format commands (should be blocked)
    'formatar C:',
    'format C:',
    'formata o C:',
    'zara, formata C:',
    
    # Normal commands (should work)
    'abra a calculadora',
    'zara, abre a calculadora',
    'procure por Python',
    'zara, resuma esta pagina',
    'mova a janela para o lado direito',
]

for t in tests:
    result = detector.detect(t)
    print(f'Input: {t!r}')
    print(f'  is_pc_intent: {result.is_pc_intent}, action: {result.action}, blocked: {result.blocked}')
    reply_val = result.reply if result.reply else '(empty)'
    print(f'  reply: {reply_val}')
    print()
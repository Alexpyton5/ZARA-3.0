import sys
import os
os.chdir(r'C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002')
sys.path.insert(0, '.')
from core.pc_voice_intent import PcVoiceIntentDetector

detector = PcVoiceIntentDetector(pc_control_allowed=True)

# Test format commands
tests = [
    'formatar C:',
    'format C:',
    'formata o C:',
    'zara, formata C:',
    'abra a calculadora',  # should not match format
    'procure por Python',  # should not match format
    'zara, abre a calculadora',  # should work normally
]
for t in tests:
    result = detector.detect(t)
    print(f'Input: {t!r}')
    print(f'  is_pc_intent: {result.is_pc_intent}, action: {result.action}, blocked: {result.blocked}')
    reply_val = result.reply if result.reply else "(empty)"
    print(f'  reply: {reply_val}')
    # Add to history if detected
    if result.is_pc_intent:
        detector._historico_comandos.append({'comando': t, 'acao': result.action, 'bloqueado': result.blocked})
        if len(detector._historico_comandos) > detector._MAX_HISTORICO:
            detector._historico_comandos = detector._historico_comandos[-detector._MAX_HISTORICO:]
    hist = [(h["comando"], h["acao"], h["bloqueado"]) for h in detector._historico_comandos]
    print(f'  History: {hist}')
    print()
#!/usr/bin/env python3
import re
import sys

sys.path.insert(0, r'C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002')

# Read the file
with open('core/pc_voice_intent.py', 'r', encoding='utf-8') as f:
    content = f.read()

# The format pattern check to insert after "if not text:" and before "text_lower ="
format_check = '''

        # ZARA-SEGURANCA-FORMAT-001: bloqueia comandos de formatao de drive
        # Verifica se o comando tenta formatar um drive antes de processar
        format_match = _PATTERN_FORMAT.search(text_lower)
        if format_match:
            return PcVoiceResult(
                is_pc_intent=True,
                action="os_drive_format",
                param=format_match.group(1),
                blocked=True,
                physical_effect=0,
                reply="Não posso executar comandos de formatao de drive. Esse comando e bloqueado por seguranca.",
            )

'''

# Find the position: after "if not text:" and before "text_lower ="
target = "        if not text:\n            return PcVoiceResult(is_pc_intent=False)\n"

replacement = target + format_check

if target in content:
    content = content.replace(target, replacement, 1)
    with open('core/pc_voice_intent.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Successfully inserted format check in detect method')
else:
    print('Target pattern not found')
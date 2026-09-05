#!/usr/bin/env python3
import re

# Read the file
with open('core/pc_voice_intent.py', 'r', encoding='utf-8') as f:
    content = f.read()

# The exact pattern from line 445 (raw string with escaped chars)
# Looking at the actual content: _SINTAXE_PERIGOSA = re.compile(r'(?:&&|\\|\\||[;`]|\\$(\(|\\.[\\/]|[\\/].\\.)')
target = "_SINTAXE_PERIGOSA = re.compile(r'(?:&&|\\\\|\\\\||[;`]|\\$\\\\(|\\.\\.[\\\\/]|[\\\\/]\\.\\.)')"

# New code to insert after target
new_code = """    # ZARA-SEGURANCA-FORMAT-001: bloqueia comandos de formatao de drive
    # para prevenir acidentes acidentais. Quando detectado, zara responde
    # honestamente que nao pode executar esse comando.
    _PATTERN_FORMAT = re.compile(
        r'\\b(?:formata|format(?:ar|ar)\\s+)(?:[/\\\\])?([A-Z]:?)\\b',
        re.IGNORECASE,
    )
    # Historico dos ultimos 5 comandos detectados (memoria volatil)
    _historico_comandos: list[dict] = []
    _MAX_HISTORICO = 5

"""

# Replace
if target in content:
    content = content.replace(target, target + new_code, 1)
    with open('core/pc_voice_intent.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Successfully updated file')
else:
    print('Target pattern not found')
    # Debug
    lines = content.split('\n')
    for i, line in enumerate(lines[444:452], start=445):
        print(f'{i}: {line!r}')
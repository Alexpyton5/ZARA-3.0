#!/usr/bin/env python3
import re

# Read the file
with open('core/pc_voice_intent.py', 'r', encoding='utf-8') as f:
    content = f.read()

# The exact pattern - match line 445 exactly as it appears in the file
# From the debug output: _SINTAXE_PERIGOSA = re.compile(r'(?:&&|\\|\\||[;`]|\\$(\(|\\.[\\/]|[\\/].\\.)')
# In the file it's stored with double backslashes escaped for JSON

# Let me just find the position of "_SINTAXE_PERIGOSA" and insert after it
pos = content.find("_SINTAXE_PERIGOSA")
if pos == -1:
    print("Could not find _SINTAXE_PERIGOSA")
    sys.exit(1)

# Find the end of this line (the \n after the closing paren)
line_start = content.rfind('\n', 0, pos)
line_end = content.find('\n', pos)
original_line = content[line_start:line_end+1]

# The new content to add after this line
new_section = '''
    # ZARA-SEGURANCA-FORMAT-001: bloqueia comandos de formatao de drive
    # para prevenir acidentes acidentais. Quando detectado, zara responde
    # honestamente que nao pode executar esse comando.
    _PATTERN_FORMAT = re.compile(
        r'\\b(?:formata|format(?:ar|ar)\\s+)(?:[/\\\\])?([A-Z]:?)\\b',
        re.IGNORECASE,
    )
    # Historico dos ultimos 5 comandos detectados (memoria volatil)
    _historico_comandos: list[dict] = []
    _MAX_HISTORICO = 5

'''

# Insert after the line
new_content = content[:line_end+1] + new_section + content[line_end+1:]

with open('core/pc_voice_intent.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print('Successfully updated file')
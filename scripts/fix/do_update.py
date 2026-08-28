import sys

with open('core/pc_voice_intent.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the start line
for i, line in enumerate(lines):
    if '# ZARA-SEGURANCA-FORMAT-001: bloqueia comandos de formatao de drive' in line:
        start = i
        new_block = [
            '    # ZARA-SEGURANCA-FORMAT-001: bloqueia comandos de formatao de drive\n',
            '    # para prevenir acidentes acidentais. Quando detectado, zara responde\n',
            '    # honestamente que nao pode executar esse comando.\n',
            '    _PATTERN_FORMAT = re.compile(\n',
            "        r'\\\\b(?:formata|formatar|format)\\\\b.*?(?:[/\\\\\\\\])?([A-Z]):(?!\\\\w)',\n",
            '        re.IGNORECASE,\n',
            '    )\n'
        ]
        # Replace 7 lines (from start to start+6 inclusive)
        lines[start:start+7] = new_block
        break

with open('core/pc_voice_intent.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Pattern updated')
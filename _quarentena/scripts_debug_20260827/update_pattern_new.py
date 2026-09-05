import sys

with open('core/pc_voice_intent.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line numbers for the pattern we want to replace
for i, line in enumerate(lines):
    if '# ZARA-SEGURANCA-FORMAT-001: bloqueia comandos de formatao de drive' in line:
        start = i
        # We'll replace 7 lines (from start to start+6 inclusive) because the original pattern block is 7 lines?
        # Let's count: from line 453 to 459 inclusive is 7 lines.
        new_block = [
            '    # ZARA-SEGURANCA-FORMAT-001: bloqueia comandos de formatao de drive\n',
            '    # para prevenir acidentes acidentais. Quando detectado, zara responde\n',
            '    # honestamente que nao pode executar esse comando.\n',
            '    _PATTERN_FORMAT = re.compile(\n',
            "        r'\\\\b(?:formata|formatar|format)\\\\b.*?\\\\b([A-Z]:)(?!\\\\w)',\n",
            '        re.IGNORECASE,\n',
            '    )\n'
        ]
        # Replace lines[start:start+7] with new_block
        lines[start:start+7] = new_block
        break

with open('core/pc_voice_intent.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Pattern updated to new version')
import re

with open('core/pc_voice_intent.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line numbers for the pattern we want to replace
for i, line in enumerate(lines):
    if '# ZARA-SEGURANCA-FORMAT-001: bloqueia comandos de formatao de drive' in line:
        start = i
        # Find the end of the _PATTERN_FORMAT block (look for the line after re.IGNORECASE,)
        for j in range(i, len(lines)):
            if lines[j].strip() == 're.IGNORECASE,' and j+1 < len(lines) and lines[j+1].strip() == ')':
                end = j+1  # inclusive of the closing parenthesis line
                break
        else:
            end = len(lines)
        # Replace lines[start:end+1] with corrected version
        new_block = [
            '    # ZARA-SEGURANCA-FORMAT-001: bloqueia comandos de formatao de drive\n',
            '    # para prevenir acidentes acidentais. Quando detectado, zara responde\n',
            '    # honestamente que nao pode executar esse comando.\n',
            '    _PATTERN_FORMAT = re.compile(\n',
            '        r\'\\\\b(?:formata|formatar|format)\\\\b.*?\\\\b([A-Z]:)(?!\\\\w)\',\n',
            '        re.IGNORECASE,\n',
            '    )\n'
        ]
        # Keep the indentation level (should be 4 spaces)
        # Actually the lines already have the correct indentation except the content we are replacing.
        # We'll just replace the block.
        lines[start:end+1] = new_block
        break

with open('core/pc_voice_intent.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Fixed indentation')
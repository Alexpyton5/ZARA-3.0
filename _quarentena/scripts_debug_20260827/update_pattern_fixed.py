import sys

with open('core/pc_voice_intent.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the start line
for i, line in enumerate(lines):
    if '# ZARA-SEGURANCA-FORMAT-001: bloqueia comandos de formatao de drive' in line:
        start = i
        # We'll replace 6 lines (from start to start+5 inclusive) because the original pattern block is 6 lines? Let's see:
        # Actually from line 453 to 459 inclusive is 7 lines? We'll replace from start to start+6 (7 lines) to be safe.
        # But we want to keep the comment lines and the blank line? The comment lines are part of the block we want to keep.
        # We'll replace from the line after the comment? Actually we want to keep the comment lines exactly as they are.
        # The comment lines are lines 453, 454, 455? Let's check: line numbers may have shifted.
        # Safer: replace from the line containing '_PATTERN_FORMAT = re.compile(' to the line with the closing parenthesis after re.IGNORECASE,
        # We'll find the start of the pattern line and the end.
        # Let's just replace lines[start:start+7] where start is the line with the comment.
        # But we want to keep the comment lines, so we replace from start to start+6 (7 lines) where start is the comment line.
        # However the comment lines are three lines? Actually we have:
        # 453: # ZARA-SEGURANCA-FORMAT-001: bloqueia comandos de formatao de drive
        # 454: # para prevenir acidentes acidentais. Quando detectado, zara responde
        # 455: # honestamente que nao pode executar esse comando.
        # 456:     _PATTERN_FORMAT = re.compile(
        # 457:         r'...',
        # 458:         re.IGNORECASE,
        # 459:     )
        # That's 7 lines total (453-459). We'll replace those 7 lines with the same comment lines but new pattern.
        new_block = [
            '    # ZARA-SEGURANCA-FORMAT-001: bloqueia comandos de formatao de drive\n',
            '    # para prevenir acidentes acidentais. Quando detectado, zara responde\n',
            '    # honestamente que nao pode executar esse comando.\n',
            '    _PATTERN_FORMAT = re.compile(\n',
            "        r'\\\\b(?:formata|formatar|format)\\\\b.*?\\\\b([A-Z]:)(?!\\\\w)',\n",
            '        re.IGNORECASE,\n',
            '    )\n'
        ]
        # Replace with correct pattern.

<tool_call>
<function=write_file>
<parameter=content>
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
            "        r'\\\\b(?:formata|formatar|format)\\\\b.*?\\\\b([A-Z]:)(?!\\\\w)',\n",
            '        re.IGNORECASE,\n',
            '    )\n'
        ]
        # Replace lines[start:start+7] with new_block
        lines[start:start+7] = new_block
        break

with open('core/pc_voice_intent.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Pattern updated (but likely still wrong due to escaping)')
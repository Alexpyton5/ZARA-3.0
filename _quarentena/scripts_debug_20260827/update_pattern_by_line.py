filepath = r'core/pc_voice_intent.py'
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if '_PATTERN_FORMAT' in line and 're.compile' in line:
        # The next line is the pattern string
        old_line = lines[i+1]
        indentation = old_line[:len(old_line) - len(old_line.lstrip())]
        pattern_inner = "\\\\b(?:formata|formatar|format)\\\\b.*?(?:[/\\\\])?[A-Z]:(?![a-zA-Z0-9])"
        new_line = indentation + \"r'\" + pattern_inner + \"',\\n\"
        lines[i+1] = new_line
        break

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Pattern updated')
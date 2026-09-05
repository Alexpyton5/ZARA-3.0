import re

filepath = r'core/pc_voice_intent.py'
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line with '_PATTERN_FORMAT = re.compile('
for i, line in enumerate(lines):
    if '_PATTERN_FORMAT' in line and 're.compile' in line:
        # The next line is the pattern string
        pattern_line_idx = i + 1
        # Replace that line with the new pattern string, keeping the same indentation
        indentation = lines[pattern_line_idx][:len(lines[pattern_line_idx]) - len(lines[pattern_line_idx].lstrip())]
        new_pattern_line = indentation + r"r'\\\\b(?:formata|formatar|format)\\\\b.*?(?:[/\\\\])?[A-Z]:(?![a-zA-Z0-9])',\\n"
        lines[pattern_line_idx] = new_pattern_line
        break

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Pattern updated')
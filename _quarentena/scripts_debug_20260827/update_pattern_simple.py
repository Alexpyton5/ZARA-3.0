import sys

filepath = r'core/pc_voice_intent.py'
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# We'll look for the line that contains the pattern string.
# We know the line starts with 8 spaces, then r'\\b(?:formata|format(?:ar|ar)\\s+)(?:[/\\\\])?([A-Z]:?)\\b',
# But to be safe, we'll look for the line that contains \"format(?:ar|ar)\" and ends with \"\\b',\"
new_line = "        r'\\\\b(?:formata|formatar|format)\\\\b.*?(?:[/\\\\])?[A-Z]:(?![a-zA-Z0-9])',\n"
for i, line in enumerate(lines):
    if 'format(?:ar|ar)' in line and \"\\b',\" in line:
        lines[i] = new_line
        break

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Pattern updated')
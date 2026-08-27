import re
import sys

with open('core/pc_voice_intent.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the _PATTERN_FORMAT line and the surrounding lines (the comment and the re.compile block)
# We'll replace from the line with the comment to the line with the closing parenthesis after re.IGNORECASE,
# but we want to keep the comment lines exactly as they are.
# Instead, we'll replace only the pattern string inside the re.compile call.
# We'll use a regex to find _PATTERN_FORMAT = re.compile( ... ) and replace the inner pattern.
pattern_to_replace = r'_PATTERN_FORMAT\s*=\s*re\.compile\('
# We'll find the matching parentheses.
# Since the pattern may span multiple lines, we'll do a more robust replacement: replace the whole line range.
# Let's find the start index of the comment line.
lines = content.splitlines(keepends=True)
new_lines = []
i = 0
while i < len(lines):
    if '# ZARA-SEGURANCA-FORMAT-001: bloqueia comandos de formatao de drive' in lines[i]:
        # We have found the comment line. We'll keep the next two comment lines as is.
        new_lines.append(lines[i])   # comment line
        i += 1
        new_lines.append(lines[i])   # second comment line
        i += 1
        new_lines.append(lines[i])   # third comment line
        i += 1
        # Now we expect the line with _PATTERN_FORMAT = re.compile(
        # We'll replace the next 4 lines (the pattern line, the pattern string line, the re.IGNORECASE line, and the closing parenthesis line)
        # But we don't know exactly how many lines the pattern spans. We'll replace until we see a line that starts with '    )' (with exactly 4 spaces?) Actually the indentation is 4 spaces for the closing parenthesis? Let's look at the original:
        #     _PATTERN_FORMAT = re.compile(
        #         r'\\b(?:formata|format(?:ar|ar)\\s+)(?:[/\\\\])?([A-Z]:?)\\b',
        #         re.IGNORECASE,
        #     )
        # So after the comment lines, we have:
        # line i: '    _PATTERN_FORMAT = re.compile('
        # line i+1: '        r'\\b(?:formata|format(?:ar|ar)\\s+)(?:[/\\\\])?([A-Z]:?)\\b','
        # line i+2: '         re.IGNORECASE,'
        # line i+3: '     )'
        # We'll replace these four lines with our new pattern.
        new_lines.append('    _PATTERN_FORMAT = re.compile(\n')
        new_lines.append("        r'\\\\b(?:formata|formatar|format)\\\\b.*?(?:[/\\\\])?([A-Z]):(?!\\\\w)',\n")
        new_lines.append('        re.IGNORECASE,\n')
        new_lines.append('    )\n')
        # Skip the old 4 lines
        i += 4
    else:
        new_lines.append(lines[i])
        i += 1

with open('core/pc_voice_intent.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
print('Pattern updated')
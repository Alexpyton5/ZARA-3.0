import re

filepath = r'core/pc_voice_intent.py'
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line with '_PATTERN_FORMAT = re.compile('
for i, line in enumerate(lines):
    if '_PATTERN_FORMAT' in line and 're.compile' in line:
        # The next line is the pattern string
        pattern_line_idx = i + 1
        # Preserve the indentation of that line
        indentation = lines[pattern_line_idx][:len(lines[pattern_line_idx]) - len(lines[pattern_line_idx].lstrip())]
        # Build the new pattern line
        # We want: indentation + r'\\\\b(?:formata|formatar|format)\\\\b.*?\\\\b([A-Z]:)(?!\\\\w)',\n
        # Note: we need to double the backslashes because we are writing a string that will be interpreted as a string literal.
        # The desired pattern string (as it should appear in the source code) is:
        #   r'\\b(?:formata|formatar|format)\\b.*?\\b([A-Z]:)(?!\w)'
        # To represent that in a string literal, we need to escape the backslashes: each backslash in the pattern must be written as two backslashes.
        # So the string we write should be:
        #   r'\\\\b(?:formata|formatar|format)\\\\b.*?\\\\b([A-Z]):(?!\\\\w)'
        # But wait, we are already in a raw string in the source code? Actually, the line we are writing is:
        #   indentation + r'...' + ',\n'
        # So we are writing a raw string. Therefore, we can write the pattern as we want it to appear in the regex, but we must double the backslashes because the raw string will treat backslashes literally, and we need to get the actual regex pattern correct.
        #
        # Let me clarify: we want the regex pattern to be:
        #   \b(?:formata|formatar|format)\b.*?\b([A-Z]:)(?!\w)
        # In a raw string, we write: r'\\b(?:formata|formatar|format)\\b.*?\\b([A-Z]:)(?!\w)'
        # Because to get a single backslash in the regex, we need two in the raw string.
        #
        # Therefore, the string we want to put inside the r'' is:
        #   \\b(?:formata|formatar|format)\\b.*?\\b([A-Z]:)(?!\w)
        # And we write that as:
        #   r'\\\\b(?:formata|formatar|format)\\\\b.*?\\\\b([A-Z]):(?!\\\\w)'
        #
        # However, note that the colon and the capturing group: we want to capture the letter and the colon, so we put the colon inside the capturing group: ([A-Z]:)
        #
        # So the line we want to write is:
        #   indentation + r"r'\\\\b(?:formata|formatar|format)\\\\b.*?\\\\b([A-Z]:)(?!\\\\w)',\\n"
        new_pattern_line = indentation + r"r'\\\\b(?:formata|formatar|format)\\\\b.*?\\\\b([A-Z]:)(?!\\\\w)',\\n"
        lines[pattern_line_idx] = new_pattern_line
        break

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Pattern updated')
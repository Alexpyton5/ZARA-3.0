import re

filepath = r'core/pc_voice_intent.py'
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line with '_PATTERN_FORMAT = re.compile('
for i, line in enumerate(lines):
    if '_PATTERN_FORMAT' in line and 're.compile' in line:
        # The next line is the pattern string (indented)
        pattern_line_idx = i + 1
        # Preserve the indentation of that line
        indentation = lines[pattern_line_idx][:len(lines[pattern_line_idx]) - len(lines[pattern_line_idx].lstrip())]
        # Build the new pattern line
        # We want: indentation + r'\b(?:formata|formatar|format)\b.*?(?:[/\\])?([A-Z]):(?!\w)',\n
        # Note: we need to escape backslashes for the string literal.
        # The desired regex pattern string (as it should appear in the source) is:
        #   r'\b(?:formata|formatar|format)\b.*?(?:[/\\])?([A-Z]):(?!\w)'
        # To represent that in a string literal, we need to double the backslashes that are meant to be in the regex.
        # However, we are writing a raw string in the source code (r'...'), so we can write the pattern as we want it to appear in the regex, but we must double the backslashes because the raw string will treat backslashes literally, and we need to get the actual regex pattern correct.
        #
        # Let's think: we want the line in the source to be:
        #     _PATTERN_FORMAT = re.compile(
        #         r'\b(?:formata|formatar|format)\b.*?(?:[/\\])?([A-Z]):(?!\w)',
        #         re.IGNORECASE,
        #     )
        #
        # So inside the r'', we need to write the regex pattern with single backslashes where we want a backslash in the regex.
        # However, when we write this string in our Python script, we need to escape backslashes because we are in a regular string.
        # We'll construct the line as:
        #   indentation + r"r'\\b(?:formata|formatar|format)\\b.*?(?:[/\\\\])?([A-Z]):(?!\\w)',\\n"
        # Wait, let's break down:
        # We want the raw string to contain: \b(?:formata|formatar|format)\b.*?(?:[/\\])?([A-Z]):(?!\w)
        # In a raw string, backslashes are treated literally, so to get a single backslash in the raw string we need to write two backslashes in the source code.
        # But we are already writing a string that will be placed in the source code. We want the line in the source code to be exactly:
        #         r'\b(?:formata|formatar|format)\b.*?(?:[/\\])?([A-Z]):(?!\w)',
        #
        # So we need to produce that text. Let's construct it piece by piece.
        # We'll write:
        #   new_pattern_line = indentation + r"r'\\b(?:formata|formatar|format)\\b.*?(?:[/\\\\])?([A-Z]):(?!\\w)',\\n"
        # Let's test what that yields:
        #   r'\\b(?:formata|formatar|format)\\b.*?(?:[/\\\\])?([A-Z]):(?!\\w)'
        # When Python reads that as a raw string, it sees:
        #   \b(?:formata|formatar|format)\b.*?(?:[\\])?([A-Z]):(?!\w)   ??? This is messy.
        #
        # Better approach: write the line without using a raw string in our script, but just write the exact characters we want.
        # We want the line to be (including the indentation):
        #        r'\b(?:formata|formatar|format)\b.*?(?:[/\\])?([A-Z]):(?!\w)',
        #
        # So we can construct:
        #   new_pattern_line = indentation + "r'\\\\b(?:formata|formatar|format)\\\\b.*?(?:[/\\\\])?([A-Z]):(?!\\\\w)',\\n"
        # Because:
        #   To get a single backslash in the output, we need to write \\\\ in the string literal.
        #   We want two backslashes in the output for the regex escape? Actually we want a single backslash in the regex pattern for \b.
        #   In the regex pattern, \b is represented as two characters: backslash and 'b'.
        #   In the source code, to represent a backslash we need to write \\.
        #   So to get \b in the regex pattern, we need to write \\b in the source code string.
        #   However, we are writing a raw string in the source code (r'...'), so the backslashes in the raw string are literal.
        #   Therefore, to get \b in the regex pattern, we need to write \\b in the raw string? Wait:
        #   In a raw string, backslashes are treated as literal backslashes. So if we write r'\b', that's two characters: backslash and 'b'.
        #   That's exactly what we want for the regex pattern.
        #   Therefore, in the source code, we should write: r'\b(?:formata|formatar|format)\b.*?(?:[/\\])?([A-Z]):(?!\w)'
        #   To represent that in a string literal (for our update script), we need to escape the backslashes that we want to appear in the output.
        #   So we write: "r'\\\\b(?:formata|formatar|format)\\\\b.*?(?:[/\\\\])?([A-Z]):(?!\\\\w)'"
        #   Let's verify: the string we write is:
        #       r'\\\\b(?:formata|formatar|format)\\\\b.*?(?:[/\\\\])?([A-Z]):(?!\\\\w)'
        #   When this string is evaluated (as a regular string), it becomes:
        #       r'\b(?:formata|formatar|format)\b.*?(?:[/\\])?([A-Z]):(?!\w)'
        #   Because each \\\\ becomes a single \ in the string.
        #   Then when that string is placed in the source code, it will be exactly:
        #       r'\b(?:formata|formatar|format)\b.*?(?:[/\\])?([A-Z]):(?!\w)'
        #   Which is what we want.
        #
        new_pattern_line = indentation + "r'\\\\b(?:formata|formatar|format)\\\\b.*?(?:[/\\\\])?([A-Z]):(?!\\\\w)',\\n"
        lines[pattern_line_idx] = new_pattern_line
        break

with open(filepath, 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Pattern updated')
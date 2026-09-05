import re
import sys

def update_pattern():
    filepath = r'core/pc_voice_intent.py'
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # We'll look for the line that starts with '_PATTERN_FORMAT = re.compile('
    # and then capture the pattern string (inside the quotes) until the closing quote.
    # We assume the pattern is on the next line (as in the current file) but we'll handle multiline.
    # We'll use a regex to match from '_PATTERN_FORMAT = re.compile(' to the closing parenthesis of the re.compile call.
    # However, note that the pattern string may span multiple lines? In our file it's one line.
    # We'll do a simpler approach: replace the pattern string we know.

    # The current pattern string (as seen in the file) is:
    #   r'\\b(?:formata|format(?:ar|ar)\\s+)(?:[/\\\\])?([A-Z]:?)\\b'
    # We want to replace it with:
    #   r'\\b(?:formata|formatar|format)\\b.*?(?:[/\\\\])?[A-Z]:(?![a-zA-Z0-9])'

    # We'll replace the pattern string inside the re.compile call.
    # We'll use a regex that matches the entire re.compile call and replaces the pattern string.
    # But note: there might be multiple re.compile calls in the file. We'll anchor by the variable name.

    pattern_to_replace = re.compile(
        r'(_PATTERN_FORMAT\s*=\s*re\.compile\()([^)]*)(\))',
        re.DOTALL
    )

    def replace_func(match):
        # match.group(1) is '_PATTERN_FORMAT = re.compile('
        # match.group(2) is the content inside the parentheses (including the pattern string and the re.IGNORECASE flag)
        # match.group(3) is the closing ')'
        # We need to replace the pattern string (the first argument) and leave the second argument (re.IGNORECASE) alone.
        # The inside of the parentheses currently looks like:
        #   r'\\b(?:formata|format(?:ar|ar)\\s+)(?:[/\\\\])?([A-Z]:?)\\b',
        #        re.IGNORECASE,
        # We want to change it to:
        #   r'\\b(?:formata|formatar|format)\\b.*?(?:[/\\\\])?[A-Z]:(?![a-zA-Z0-9])',
        #        re.IGNORECASE,
        # We'll split the inside by the comma that separates the arguments.
        # But note: the pattern string may contain commas? Not in our case.
        # We'll split at the first comma that is outside quotes? Too complex.
        # Instead, we know the structure: the first argument is the pattern string, then a comma, then the flag.
        # We'll replace the first argument and keep the rest.

        # Find the first comma that is not inside quotes? We'll assume the pattern string does not contain a comma.
        # So we can split at the first comma.
        inside = match.group(2)
        # Split at the first comma
        parts = inside.split(',', 1)
        if len(parts) == 2:
            # parts[0] is the pattern string (including leading/trailing whitespace)
            # parts[1] is the rest (starting with the flag)
            new_pattern_str = r"r'\\b(?:formata|formatar|format)\\b.*?(?:[/\\\\])?[A-Z]:(?![a-zA-Z0-9])'"
            new_inside = new_pattern_str + ',' + parts[1]
            return match.group(1) + new_inside + match.group(3)
        else:
            # If we don't find a comma, we just replace the whole inside with the new pattern (and assume no flags)
            # But we know there is a flag, so this shouldn't happen.
            return match.group(1) + r"r'\\b(?:formata|formatar|format)\\b.*?(?:[/\\\\])?[A-Z]:(?![a-zA-Z0-9])', re.IGNORECASE" + match.group(3)

    new_content = pattern_to_replace.sub(replace_func, content)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print('Pattern updated in', filepath)

if __name__ == '__main__':
    update_pattern()
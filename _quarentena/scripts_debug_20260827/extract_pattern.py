import re
with open('core/pc_voice_intent.py', 'r', encoding='utf-8') as f:
    content = f.read()
# Extract the pattern
import re as re2
match = re2.search(r"_PATTERN_FORMAT\s*=\s*re\.compile\((.*?)\)", content, re2.DOTALL)
if match:
    pattern_str = match.group(1)
    print('Pattern string raw:', repr(pattern_str))
    # The string includes the quotes and the escapes as they appear in the source.
    # We need to compile it exactly as Python would.
    # Since it's already a string literal, we can evaluate it? Safer to just use re.compile with the string as is, but note that the string contains escaped backslashes.
    # Actually, the string is exactly what's between the quotes, including the backslashes as they are in the source.
    # Let's just print it and try to compile.
    try:
        p = re.compile(pattern_str, re.IGNORECASE)
        print('Compiled pattern:', p.pattern)
    except Exception as e:
        print('Error compiling:', e)
else:
    print('Pattern not found')
import re
# Read the pattern from the file
with open('core/pc_voice_intent.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Extract the pattern line
import re as re2
# Look for _PATTERN_FORMAT = re.compile(...)
match = re2.search(r"_PATTERN_FORMAT\s*=\s*re\.compile\((.*?)\)", content, re2.DOTALL)
if match:
    pattern_str = match.group(1)
    print('Pattern string raw:', repr(pattern_str))
    # The string may have escaped quotes, we need to compile it as is.
    # Actually the pattern string is what's inside the quotes, including the escapes.
    # Let's try to eval it? Safer to just reconstruct.
    # Instead, let's just print the line and manually see.
else:
    print('Pattern not found')

# Let's just read the lines around the pattern
lines = content.splitlines()
for i, line in enumerate(lines):
    if '_PATTERN_FORMAT' in line:
        print(f'Line {i}: {line}')
        # Print a few lines before and after
        for j in range(max(0, i-2), min(len(lines), i+5)):
            print(f'{j}: {lines[j]}')
        break
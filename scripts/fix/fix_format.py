import re

# Read the file
with open('core/pc_voice_intent.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Old pattern
old_pattern = r'''_PATTERN_FORMAT = re.compile(
        r'\\b(?:formata|format(?:ar|ar)\\s+)(?:[/\\\\])?([A-Z]:?)\\b',
        re.IGNORECASE,
    )'''

# New pattern
new_pattern = r'''_PATTERN_FORMAT = re.compile(
        r'\\b(?:formata|formatar|format)\\b.*?([A-Z]:)(?![a-zA-Z0-9])',
        re.IGNORECASE,
    )'''

# Replace
if old_pattern in content:
    content = content.replace(old_pattern, new_pattern, 1)
    with open('core/pc_voice_intent.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Successfully updated _PATTERN_FORMAT')
else:
    print('Pattern not found, trying alternative...')
    # Try to find it with slight variations
    import re
    pattern = re.compile(r'_PATTERN_FORMAT\s*=\s*re\.compile\([^)]+\)', re.MULTILINE | re.DOTALL)
    match = pattern.search(content)
    if match:
        print('Found pattern:', match.group()[:100])
        # Replace the whole pattern definition
        new_content = re.sub(
            r'_PATTERN_FORMAT\s*=\s*re\.compile\([^)]+\)',
            '_PATTERN_FORMAT = re.compile(\n        r\'\\\\b(?:formata|formatar|format)\\\\b.*?([A-Z]:)(?![a-zA-Z0-9])\',\n        re.IGNORECASE,\n    )',
            content,
            flags=re.MULTILINE | re.DOTALL,
            count=1
        )
        if new_content != content:
            with open('core/pc_voice_intent.py', 'w', encoding='utf-8') as f:
                f.write(new_content)
            print('Successfully updated pattern via regex')
        else:
            print('Regex replacement failed')
    else:
        print('Could not find _PATTERN_FORMAT definition')
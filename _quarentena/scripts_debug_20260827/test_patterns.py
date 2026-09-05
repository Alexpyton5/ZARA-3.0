import re

# Test different patterns
patterns = [
    r'\b(?:formata|formatar|format)\b.*?\b([A-Z]:)(?!\w)',  # our candidate
    r'\b(?:formata|formatar|format)\b.*?([A-Z]:)(?!\w)',    # without \b before [
    r'\b(?:formata|formatar|format)\b[^a-zA-Z0-9]*?([A-Z]:)(?!\w)',  # non-alnum between
]

def test_pattern(pattern_str, tests):
    pattern = re.compile(pattern_str, re.IGNORECASE)
    print(f'Testing pattern: {pattern_str}')
    for text, expected in tests:
        match = pattern.search(text.lower())
        if bool(match) != expected:
            print(f'  FAIL: {text!r} -> expected {expected}, got {bool(match)}')
        else:
            print(f'  OK:   {text!r}')

# Test cases: (text, should_match)
tests = [
    ('formatar C:', True),
    ('format C:', True),
    ('formata o C:', True),
    ('zara, formata C:', True),
    ('formatar D:', True),
    ('format X:', True),
    ('formata o D:', True),
    ('formatar c:', True),
    ('formatar C:\\\\', True),  # extra backslash but colon present
    ('formatar C: some text', True),
    ('formatar C:', True),
    ('abra a calculadora', False),
    ('procure por Python', False),
    ('zara, abre a calculadora', False),
    ('formatar', False),
    ('formatar:', False),
    ('formatar C', False),  # missing colon
    ('informar algo', False),
    ('formatação de c:', False),  # different word
]

for p in patterns:
    test_pattern(p, tests)
    print()
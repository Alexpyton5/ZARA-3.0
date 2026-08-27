import re
# Test different pattern representations
patterns = [
    r'\b(?:formata|formatar|format)\b.*?(?:[/\\])?[A-Z]:(?!\w)',  # candidate
    r'\b(?:formata|formatar|format)\b.*?(?:[/\\\\])?[A-Z]:(?!\w)', # double backslash in class
]
def test_pattern(pat, tests):
    regex = re.compile(pat, re.IGNORECASE)
    for text, expected in tests:
        m = regex.search(text.lower())
        if bool(m) != expected:
            print(f'FAIL {pat!r}: {text!r} -> expected {expected}, got {bool(m)}')
        else:
            print(f'OK   {pat!r}: {text!r}')

tests = [
    ('formatar C:', True),
    ('format C:', True),
    ('formata o C:', True),
    ('zara, formata C:', True),
    ('formatar D:', True),
    ('format X:', True),
    ('formata o D:', True),
    ('formatar c:', True),
    ('formatar C:\\\\', True),  # extra backslash
    ('formatar C: some text', True),
    ('formatar C:', True),
    ('abra a calculadora', False),
    ('procure por Python', False),
    ('zara, abre a calculadora', False),
    ('formatar', False),
    ('formatar:', False),
    ('formatar C', False),
    ('informar algo', False),
    ('formatação de c:', False),
    ('formatar C2:', False),
]

for pat in patterns:
    print('Testing pattern:', pat)
    test_pattern(pat, tests)
    print()
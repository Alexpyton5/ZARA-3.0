import re

# Pattern: verb (whole word) then optional whitespace, then any chars (non-greedy) until drive letter
pattern = re.compile(r'\b(?:formata|formatar|format)\b\s*.*?([A-Z]:)', re.IGNORECASE)

def test(text):
    m = pattern.search(text.lower())
    if m:
        print(f"MATCH: {text!r} -> group={m.group(1)}")
    else:
        print(f"NO: {text!r}")

# Test cases
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
    ('formatar C', False),
    ('informar algo', False),
    ('formatação de c:', False),  # different word
]

print('Testing pattern: r\\b(?:formata|formatar|format)\\b\\s*.*?([A-Z]:)')
for text, expected in tests:
    m = pattern.search(text.lower())
    if bool(m) != expected:
        print(f'FAIL: {text!r} -> expected {expected}, got {bool(m)}')
    else:
        print(f'OK:   {text!r}')
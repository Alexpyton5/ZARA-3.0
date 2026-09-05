import re
pattern = re.compile(r'\b(?:formata|format(?:ar|ar)\s+)(?:[/\\])?([A-Z]:?)\b', re.IGNORECASE)

def test(text):
    m = pattern.search(text.lower())
    if m:
        print(f"MATCH: {text!r} -> group={m.group(1)}")
    else:
        print(f"NO: {text!r}")

tests = [
    ('formatar C:', True),
    ('format C:', True),
    ('formata o C:', True),
    ('zara, formata C:', True),
    ('formatar D:', True),
    ('format X:', True),
    ('formata o D:', True),
    ('formatar c:', True),
    ('formatar C\\\\', True),  # extra backslash but colon present? Actually pattern expects optional slash then colon optional? Let's see.
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

print('Testing backup pattern:')
for text, expected in tests:
    m = pattern.search(text.lower())
    if bool(m) != expected:
        print(f'FAIL: {text!r} -> expected {expected}, got {bool(m)}')
    else:
        print(f'OK:   {text!r}')
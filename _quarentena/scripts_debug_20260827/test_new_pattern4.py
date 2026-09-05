import re
pattern = re.compile(r'\b(?:formata|formatar|format)\b.*?(?:[/\\])?([A-Z]):(?!\w)', re.IGNORECASE)

def test(text):
    m = pattern.search(text.lower())
    if m:
        return True, m.group(1)
    else:
        return False, None

tests = [
    ('formatar C:', True, 'c:'),
    ('format C:', True, 'c:'),
    ('formata o C:', True, 'c:'),
    ('zara, formata C:', True, 'c:'),
    ('formatar D:', True, 'd:'),
    ('format X:', True, 'x:'),
    ('formata o D:', True, 'd:'),
    ('formatar c:', True, 'c:'),
    ('formatar C:\\\\', True, 'c:'),  # extra backslash
    ('formatar C: some text', True, 'c:'),
    ('formatar C:', True, 'c:'),
    ('abra a calculadora', False, None),
    ('procure por Python', False, None),
    ('zara, abre a calculadora', False, None),
    ('formatar', False, None),
    ('formatar:', False, None),
    ('formatar C', False, None),
    ('informar algo', False, None),
    ('formatação de c:', False, None),  # different word
    ('formatar C2:', False, None),  # extra digit before colon
]

print('Testing new pattern:')
all_ok = True
for text, expected, expected_letter in tests:
    matched, letter = test(text)
    if matched != expected or (matched and letter != expected_letter):
        print(f'FAIL: {text!r} -> matched={matched}, letter={letter!r} (expected matched={expected}, letter={expected_letter!r})')
        all_ok = False
    else:
        print(f'OK:   {text!r} -> matched={matched}, letter={letter!r}')

if all_ok:
    print('All tests passed')
else:
    print('Some tests failed')
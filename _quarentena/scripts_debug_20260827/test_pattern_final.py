import re
import sys
sys.path.insert(0, '.')

# Test pattern
pattern = re.compile(r'\b(?:formata|formatar|format)\b.*?(?:[/\\])?([A-Z]):(?!\w)', re.IGNORECASE)

def test(text):
    m = pattern.search(text.lower())
    if m:
        return True, m.group(1)
    else:
        return False, None

# Test cases: (text, should_match, expected_letter)
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
    ('formatar C2:', False, None),  # extra digit after letter before colon? Actually C2: has letter then digit then colon, our pattern expects letter then colon, so fails because after letter we need colon immediately? Wait we have .*? between verb and (?:[/\\])?([A-Z]): so the letter must be immediately before colon? Actually the ([A-Z]) is right before the colon in the pattern: (?:[/\\])?([A-Z]):. So the letter must be directly before colon, with optional slash before it. So 'C2:' would not match because we need letter then colon, but we have letter then digit then colon. Good.
    ('formatar C:', True, 'c:'),
    ('formatar C:', True, 'c:'),
]

print('Testing pattern: r\\b(?:formata|formatar|format)\\b.*?(?:[/\\\\])?([A-Z]):(?!\w)')
all_ok = True
for text, should_match, expected in tests:
    matched, letter = test(text)
    if matched != should_match or (matched and letter != expected):
        print(f'FAIL: {text!r} -> matched={matched}, letter={letter!r} (expected matched={should_match}, letter={expected!r})')
        all_ok = False
    else:
        print(f'OK:   {text!r} -> matched={matched}, letter={letter!r}')

if all_ok:
    print('All tests passed')
else:
    print('Some tests failed')
import re

# Test the pattern
pattern = re.compile(r'\b(?:formata|formatar|format)\b.*?(?:[/\\])?[A-Z]:(?![a-zA-Z0-9])', re.IGNORECASE)

def test(text):
    m = pattern.search(text.lower())
    if m:
        return True, m.group(0)
    else:
        return False, None

# Test cases: (text, should_match, expected_matched_substring)
tests = [
    ('formatar C:', True, 'formatar C:'),
    ('format C:', True, 'format C:'),
    ('formata o C:', True, 'formata o C:'),
    ('zara, formata C:', True, 'zara, formata C:'),
    ('formatar D:', True, 'formatar D:'),
    ('format X:', True, 'format X:'),
    ('formata o D:', True, 'formata o D:'),
    ('formatar c:', True, 'formatar c:'),
    ('formatar C:\\\\', True, 'formatar C:\\\\'),  # extra backslash after colon? Actually the colon is present, then backslash, then nothing. The pattern allows any characters after the colon as long as the next character after colon is not alphanumeric. Here after colon we have backslash (non-alnum) so it matches.
    ('formatar C: some text', True, 'formatar C: some text'),  # after colon we have space, then text. The first char after colon is space (non-alnum) so matches.
    ('formatar C:', True, 'formatar C:'),
    ('abra a calculadora', False, None),
    ('procure por Python', False, None),
    ('zara, abre a calculadora', False, None),
    ('formatar', False, None),
    ('formatar:', False, None),
    ('formatar C', False, None),
    ('informar algo', False, None),
    ('formatação de c:', False, None),  # different word
    ('formatar C2:', False, None),  # letter then digit then colon: after the colon? Actually we have C2: the letter is C, then 2, then colon. Our pattern expects the colon to be immediately after the optional slash/backslash and the letter. Here we have letter then digit then colon, so the colon is not immediately after the letter. The pattern would try to match: verb .*? (?:[/\\])? [A-Z] : ... After the verb we have ' C2:' -> the (?:[/\\])? matches nothing, then [A-Z] matches 'C', then we expect a colon but the next char is '2' (not colon) so fails. Then the .*? can expand to include the '2'? Actually the .*? is lazy, so it will match as little as possible. It will match zero characters, then we try to match (?:[/\\])?[A-Z]: at the position after the verb. At the position after the verb we have space then 'C2:'. The (?:[/\\])? matches nothing, [A-Z] matches 'C', then we need a colon but we have '2', so it fails. Then the .*? will expand to match one character (the space) and try again? Actually the .*? is between the verb and the (?:[/\\])?[A-Z]:. So we can have any characters (including the space and the '2') until we find a place where (?:[/\\])?[A-Z]: matches. After the verb we have ' C2:'. We can skip the space and the '2'? Then we are at the colon: (?:[/\\])? matches nothing, [A-Z] would need to match a letter but we have ':' -> fails. So we cannot match. So it should not block. Good.
    ('formatar C:', True, 'formatar C:'),
]

print('Testing pattern: r\\b(?:formata|formatar|format)\\b.*?(?:[/\\\\])?[A-Z]:(?![a-zA-Z0-9])')
all_ok = True
for text, expected, _ in tests:
    matched, substr = test(text)
    if matched != expected:
        print(f'FAIL: {text!r} -> expected {expected}, got {matched}')
        all_ok = False
    else:
        print(f'OK:   {text!r}')

if all_ok:
    print('All tests passed')
else:
    print('Some tests failed')
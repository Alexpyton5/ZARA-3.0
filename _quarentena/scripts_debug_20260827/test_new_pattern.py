import re

# Test pattern
pattern = re.compile(r'\b(?:formata|formatar|format)\b.*?\b([A-Z]:)(?!\w)', re.IGNORECASE)

def test(text):
    m = pattern.search(text.lower())
    if m:
        print(f"MATCH: {text!r} -> group={m.group(1)}")
    else:
        print(f"NO: {text!r}")

# Expected matches
matches = [
    'formatar C:',
    'format C:',
    'formata o C:',
    'zara, formata C:',
    'formatar D:',
    'format X:',
    'formata o D:',
    'formatar c:',  # lowercase
    'formatar C',   # no colon -> should not match because we require colon
    'formatar C:\\\\', # extra backslash
    'formatar C: some text',
    'formatar C:',  # with colon
    'zara formata C:',
    'zara, formata C:',
    'formatar  C:', # double space
    'formatar\tC:', # tab
]

# Expected non-matches
non_matches = [
    'abra a calculadora',
    'procure por Python',
    'zara, abre a calculadora',
    'formatação', # different word
    'informar', # contains format but not the verb
    'formatar', # just the verb, no drive
    'formatar:', # verb and colon but no drive letter
    'formatar C', # missing colon (we require colon in the pattern now)
]

print('--- Matches ---')
for t in matches:
    test(t)

print('--- Non-matches ---')
for t in non_matches:
    test(t)
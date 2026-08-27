import re
pattern = re.compile(r'\b(?:formata|format(?:ar|ar)\s+)(?:[/\\\\])?([A-Z]:?)\b', re.IGNORECASE)
def test(text):
    m = pattern.search(text.lower())
    if m:
        print(f"MATCH: {text!r} -> group={m.group(1)}")
    else:
        print(f"NO: {text!r}")

tests = [
    'formatar C:',
    'format C:',
    'formata o C:',
    'zara, formata C:',
    'abra a calculadora',
    'procure por Python',
    'zara, abre a calculadora',
    'formatar D:',
    'format X:',
    'formata o D:',
    'formatar c:',  # lowercase
    'formatar C',   # no colon
    'formatar C:\\\\', # extra backslash
    'formatar C: some text',
    'formatar C:',  # typo
]
for t in tests:
    test(t)
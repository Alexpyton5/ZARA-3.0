import re
pattern = re.compile(r'\b(?:formata|format(?:ar|ar)\s+)(?:[/\\])?([A-Z]:?)\b', re.IGNORECASE)

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
    'formatar D:',
    'format X:',
    'formata o D:',
    'formatar c:',
    'formatar C:\\\\',
    'formatar C: some text',
    'formatar C:',
    'abra a calculadora',
    'procure por Python',
    'zara, abre a calculadora',
    'formatar',
    'formatar:',
    'formatar C',
]
for t in tests:
    test(t)
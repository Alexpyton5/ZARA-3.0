#!/usr/bin/env python3
import re

pattern1 = re.compile(r'\b(?:formata|format)\s+[Cc]:', re.IGNORECASE)
pattern2 = re.compile(r'\bformata\s+\S+', re.IGNORECASE)

tests = ['formatar C:', 'format C:', 'formata o C:', 'zara, formata C:', 'abra a calculadora']
for t in tests:
    r1 = pattern1.search(t)
    r2 = pattern2.search(t)
    print(f'Input: {t!r}')
    print(f'  pattern1: {r1.group(0) if r1 else None}')
    print(f'  pattern2: {r2.group(0) if r2 else None}')
    print()
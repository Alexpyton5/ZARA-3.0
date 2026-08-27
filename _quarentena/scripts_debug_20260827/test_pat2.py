#!/usr/bin/env python3
import re

patterns = [
    r'\b(?:formata|format(?:ar|ar)\s+)(?:[/\\])?([A-Z]:?)\b',  # original
    r'\b(?:formata|format(?:ar|ar)\s+)(?:[/\\])?([A-Z]:?)(?:\s|$)',  # with explicit end
    r'\b(?:formata|format(?:ar|ar))\s+(?:[/\\])?([A-Z]:?)',  # no trailing boundary
]

test = 'formatar C:'
for i, p in enumerate(patterns):
    result = re.search(p, test, re.IGNORECASE)
    print(f'Pattern {i+1}: {p}')
    print(f'  Result: {result.group(0) if result else None}')
    print()
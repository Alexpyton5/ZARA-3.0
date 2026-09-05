#!/usr/bin/env python3
with open('core/pc_voice_intent.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines[444:460], start=445):
    print(f'{i}: {line}', end='')
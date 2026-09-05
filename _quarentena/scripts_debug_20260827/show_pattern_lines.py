with open('core/pc_voice_intent.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
for i, line in enumerate(lines):
    if '_PATTERN_FORMAT' in line:
        for j in range(i, min(i+5, len(lines))):
            print(f'{j+1}: {lines[j].rstrip()}')
        break
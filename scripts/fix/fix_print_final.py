import sys
with open('core/gemini_live_voice.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line index of the line that contains '# Log structured metric'
for i, line in enumerate(lines):
    if line.strip() == '# Log structured metric':
        # The next line is the print line we want to fix
        print_line_idx = i + 1
        break
else:
    print_line_idx = -1

if print_line_idx != -1:
    # Replace the print line with the corrected version
    lines[print_line_idx] = '                print(f\'[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}\')\\n'

with open('core/gemini_live_voice.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
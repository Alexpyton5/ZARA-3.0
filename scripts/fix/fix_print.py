import sys
with open('core/gemini_live_voice.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line index of the problematic print statement
for i, line in enumerate(lines):
    if '# Log structured metric' in line:
        # The next line should be the print line
        print_line_idx = i + 1
        break
else:
    print_line_idx = -1

if print_line_idx != -1:
    # Replace the line with the corrected version
    lines[print_line_idx] = '                f\'[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}\'\\n'
    # Actually, we need to keep the print(...) call, not just the f-string.
    # The line currently is:                print(f\"[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}\")
    # We want to change it to:                print(f\'[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}\')
    # But note: we must keep the print( ... ) and the quotes.
    # Let's reconstruct:
    lines[print_line_idx] = '                print(f\'[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}\')\\n'

with open('core/gemini_live_voice.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
import sys

with open('core/gemini_live_voice.py', 'r', encoding='utf-8') as f:
    lines = [line.rstrip('\n') for line in f]

# Find the line index of the comment
comment_idx = -1
for i, line in enumerate(lines):
    if line.strip() == '# Log structured metric':
        comment_idx = i
        break

# Find the line index of the return statement
return_idx = -1
for i, line in enumerate(lines):
    if line.strip() == 'return result':
        return_idx = i
        break

if comment_idx == -1 or return_idx == -1:
    print("Could not find the comment or return line")
    sys.exit(1)

# We want to replace the lines from comment_idx+1 to return_idx (exclusive of return_idx)
# with the corrected block.

new_block = [
    '                # Log structured metric',
    '                print(f\'[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}\')',
    '                # Alert thresholds',
    '                if self._wake_word_checks >= 10:',
    '                    accuracy = self._wake_word_detections / self._wake_word_checks',
    '                    if accuracy < 0.80:',
    '                        print(f\"[WAKE_WORD_ALERT] Low wake word accuracy: {accuracy:.2f} (threshold <0.80)\")',
    '                    if self._wake_word_latency_ms_count > 0:',
    '                        avg_latency = self._wake_word_latency_ms_total / self._wake_word_latency_ms_count',
    '                        if avg_latency > 200.0:',
    '                            print(f\"[WAKE_WORD_ALERT] High wake word latency: {avg_latency:.2f} ms (threshold >200ms)\")',
]

# Replace
lines = lines[:comment_idx+1] + new_block + lines[return_idx:]

# Write back
with open('core/gemini_live_voice.py', 'w', encoding='utf-8') as f:
    for line in lines:
        f.write(line + '\n')
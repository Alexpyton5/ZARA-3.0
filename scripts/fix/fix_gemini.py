import sys
import os

backup_path = 'core/gemini_live_voice.py.bak'
target_path = 'core/gemini_live_voice.py'

# Read backup
with open(backup_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# We'll apply two fixes:

# Fix 1: In _merge_fragment, fix the separator line.
# Find the line containing 'separator = \"\" if current.endswith((\" \", \"\n\")) or fragment.startswith((\" \", \"\n\", \".\", \",\", \"!\", \"?\", \":\", \";\")) else \" \"'
# We'll replace it with the correct version.
for i, line in enumerate(lines):
    if 'separator = \"\" if current.endswith((\" \", \"' in line and '\\n\\")) or fragment.startswith((\" \", \"' in line:
        # Replace the line
        lines[i] = '        separator = \"\" if current.endswith((\" \", \"\\n\")) or fragment.startswith((\" \", \"\\n\", \".\", \",\", \"!\", \"?\", \":\", \";\")) else \" \"\\n'
        break

# Fix 2: In _check_wake_word, fix the print line that has a trailing backslash.
# Find the line containing \"print(f'[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}')\\n\"
for i, line in enumerate(lines):
    if \"print(f'[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}')\" in line and line.endswith('\\\\n\\n'):
        # Actually we need to see the exact line. Let's just replace any line that contains that print and ends with a backslash.
        # We'll do a more robust fix: replace the line with the correct print without backslash.
        lines[i] = \"                print(f'[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}')\\n\"
        break

# Write back
with open(target_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Fixed file')
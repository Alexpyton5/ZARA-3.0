# Fix the gemini_live_voice.py file by restoring from backup and applying two fixes.

import shutil
import os

backup_path = 'core/gemini_live_voice.py.bak'
target_path = 'core/gemini_live_voice.py'

# Step 1: Restore from backup
shutil.copy2(backup_path, target_path)

# Step 2: Read the file
with open(target_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Step 3: Fix the _merge_fragment separator line.
# We are looking for the line that contains the separator assignment.
# We know the exact line from the backup (but we don't have it displayed). We'll search for a pattern.
for i, line in enumerate(lines):
    if 'separator = \"\" if current.endswith((\" \", \"' in line and '\\n\\")) or fragment.startswith((\" \", \"' in line:
        # Replace the line with the corrected version.
        # We need to fix the two occurrences of \"\\n\\\" to \"\\n\".
        corrected_line = line.replace('\"\\n\\\"', '\"\\n\"')
        lines[i] = corrected_line
        break

# Step 4: Fix the _check_wake_word print line that has a trailing backslash.
# We are looking for a line that contains:
# print(f'[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}')\\n
# and replace it with the same line without the trailing backslash.
for i, line in enumerate(lines):
    if \"print(f'[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}')\" in line:
        # If the line ends with a backslash (and then newline), remove the backslash.
        if line.rstrip().endswith('\\\\'):
            lines[i] = line.rstrip('\\\\') + '\\n'
        break

# Step 5: Write the file back.
with open(target_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Fixed gemini_live_voice.py')
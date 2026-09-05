import sys

backup_path = 'core/gemini_live_voice.py.bak'
target_path = 'core/gemini_live_voice.py'

with open(backup_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Fix 1: In _merge_fragment, fix the separator line.
# We are looking for the line that contains:
# separator = \"\" if current.endswith((\" \", \"\n\")) or fragment.startswith((\" \", \"\n\", \".\", \",\", \"!\", \"?\", \":\", \";\")) else \" \"
# But note: in the backup, the line might be broken. We'll look for a line that contains 'separator = \"\" if current.endswith((\" \", \"'
for i, line in enumerate(lines):
    if 'separator = \"\" if current.endswith((\" \", \"' in line:
        # Replace the entire line with the correct one.
        lines[i] = '        separator = \"\" if current.endswith((\" \", \"\\n\")) or fragment.startswith((\" \", \"\\n\", \".\", \",\", \"!\", \"?\", \":\", \";\")) else \" \"\\n'
        break

# Fix 2: In _check_wake_word, fix the print line that has a trailing backslash.
# We are looking for a line that contains:
# print(f'[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}')\\n
# But note: the backup might have the line without the backslash? Actually, we saw in the backup that the line ends with a backslash and then a newline in the string.
# We'll look for the line that contains the print and ends with a backslash.
for i, line in enumerate(lines):
    if \"print(f'[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}')\" in line:
        # Check if the line ends with a backslash (and then newline)
        if line.rstrip().endswith('\\\\'):
            # Remove the backslash and ensure we have a single newline at the end.
            lines[i] = line.rstrip('\\\\') + '\\n'
        break

# Write the fixed lines to the target file.
with open(target_path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print('Fixed gemini_live_voice.py')
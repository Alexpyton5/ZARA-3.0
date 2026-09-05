import sys

with open('core/gemini_live_voice.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# We'll process the lines and fix the print statement in the _check_wake_word method.
new_lines = []
i = 0
while i < len(lines):
    line = lines[i]
    # Look for the comment line that indicates the start of the block we want to fix.
    if line.strip() == '# Log structured metric':
        new_lines.append(line)  # keep the comment
        i += 1
        # The next line should be the print line. We'll replace it.
        if i < len(lines):
            # Replace the print line with the corrected version.
            new_lines.append("                print(f'[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}')\n")
            i += 1
            # Now we continue to add the rest of the lines as they are.
        else:
            # If there is no next line, just break.
            break
    else:
        new_lines.append(line)
        i += 1

with open('core/gemini_live_voice.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
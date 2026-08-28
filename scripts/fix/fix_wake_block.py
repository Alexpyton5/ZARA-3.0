import sys
with open('core/gemini_live_voice.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the index of the line with "# Log structured metric"
for i, line in enumerate(lines):
    if line.strip() == "# Log structured metric":
        start_idx = i
        break
else:
    start_idx = -1

# Find the index of the line with "        return result" (with exactly 8 spaces? Let's just look for "return result")
for i, line in enumerate(lines):
    if line.strip() == "return result":
        end_idx = i
        break
else:
    end_idx = len(lines)

# We want to replace lines[start_idx:end_idx] with the corrected block.
# Keep the line at start_idx (the comment) and then insert the new block, then keep the return line.
# Actually, we want to replace from the line after the comment up to but not including the return line.
new_lines = lines[:start_idx+1]  # up to and including the comment line
# Now add the corrected block:
new_lines.append('                # Log structured metric\n')
new_lines.append('                print(f"[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}")\n')
new_lines.append('                # Alert thresholds\n')
new_lines.append('                if self._wake_word_checks >= 10:\n')
new_lines.append('                    accuracy = self._wake_word_detections / self._wake_word_checks\n')
new_lines.append('                    if accuracy < 0.80:\n')
new_lines.append('                        print(f\"[WAKE_WORD_ALERT] Low wake word accuracy: {accuracy:.2f} (threshold <0.80)\")\n')
new_lines.append('                    if self._wake_word_latency_ms_count > 0:\n')
new_lines.append('                        avg_latency = self._wake_word_latency_ms_total / self._wake_word_latency_ms_count\n')
new_lines.append('                        if avg_latency > 200.0:\n')
new_lines.append('                            print(f\"[WAKE_WORD_ALERT] High wake word latency: {avg_latency:.2f} ms (threshold >200ms)\")\n')
# Now add the rest of the lines from end_idx onward
new_lines.extend(lines[end_idx:])

with open('core/gemini_live_voice.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)
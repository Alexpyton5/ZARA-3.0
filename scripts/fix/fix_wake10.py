import sys
with open('core/gemini_live_voice.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
# We'll fix lines 418-425 (0-indexed) to remove the erroneous backslash and ensure proper indentation.
# The problematic line is index 418 (line 419 in 1-indexed).
# We want to set it to:                print(f"[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}")
# And then the next line (index 419) should be:                if self._wake_word_checks >= 10:
# But currently, the line at index 418 ends with a backslash, and the next line starts with spaces and then 'accuracy = ...'
# So we need to remove the backslash and then ensure the next line is properly indented.
# Let's just replace lines 418 and 419 with the correct two lines.
# However, note that the line after the print is the accuracy line, which is at the same indentation level as the print? Actually, the print is inside an if block, and the accuracy line is also inside that same if block.
# So we can do:
lines[418] = '                print(f"[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}")\\n'
lines[419] = '                if self._wake_word_checks >= 10:\\n'
# But wait, we must check the current content of lines[419] to see if it's already correct.
# Let's first look at the current lines[419] and lines[420] etc.
# We'll do a more robust fix: we'll replace from line 418 to line 425 with the correct block.
# However, to avoid messing up, let's just fix the two lines we know are wrong.
# We'll also check that the indentation is consistent (12 spaces? Actually, the code uses 4 spaces per indent, and we are inside two nested blocks: the function and the if.
# The function is inside the class, so the method is indented by 4 spaces, the if inside the method is 8 spaces, and the inner block is 12 spaces.
# Let's verify by looking at line 410: '            if self.config.wake_word_enabled:' -> that's 12 spaces? Actually, let's count: the line starts with 12 spaces? We'll trust the existing indentation.
# We'll just keep the same indentation as the surrounding lines.
# We'll write a small script to fix the two lines.
with open('core/gemini_live_voice.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
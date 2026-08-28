import sys
with open('core/gemini_live_voice.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
# line 419 is index 418 (0-indexed)
# We want to set it to:                print(f"[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}")
# Note: we need to escape braces for the f-string: double curly braces for literal braces.
# The original line had: print(f\"[WAKE_WORD_METRIC] {{\"checks": ... }})\")\\n
# That is actually correct: the outer f-string uses double quotes, and we want to output a single { at start and } at end.
# But we saw the line had a trailing backslash. Let's just set the line without the backslash.
lines[418] = '                print(f"[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}")\\n'
with open('core/gemini_live_voice.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
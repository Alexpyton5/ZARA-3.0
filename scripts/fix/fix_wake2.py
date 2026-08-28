import sys
with open('core/gemini_live_voice.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()
# line 419 is index 418 (0-indexed)
lines[418] = '                print(f\'[WAKE_WORD_METRIC] {{\"checks\": {self._wake_word_checks}, \"detections\": {self._wake_word_detections}, \"result\": {result}, \"latency_ms\": {latency_ms:.2f}}}\')\\n'
with open('core/gemini_live_voice.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
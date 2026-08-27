import sys
sys.path.insert(0, 'C:/Users/alexp/Downloads/ZARA 3.0 CLEAN 002')
from core.gemini_live_voice import GeminiLiveVoice, GeminiLiveVoiceConfig

config = GeminiLiveVoiceConfig(api_key="test")
voice = GeminiLiveVoice(config)
print("Testing 'Estou frustrado':")
result = voice.detect_emotion_from_text("Estou frustrado")
print(f"Result: {result}")
print("Expected: frustrated")
print("Text lower:", "Estou frustrado".lower())
print("Checking substring 'frustrado':", 'frustrado' in "estou frustrado")
print("All frustrated keywords:", voice.__class__.detect_emotion_from_text.__func__ if hasattr(voice.__class__.detect_emotion_from_text, '__func__') else 'unknown')
# Actually we can't access the list easily, let's just print the function source? Not needed.
# Let's just test each keyword:
for word in ['frustrado', 'irritado', 'chateado', 'puto', 'puta', 'merda', 'caralho', 'foda', 'odesseio']:
    if word in "estou frustrado":
        print(f"Keyword '{word}' matches")
import pytest
from core.gemini_live_voice import GeminiLiveVoice

def test_detect_emotion_from_text():
    voice = GeminiLiveVoice.__new__(GeminiLiveVoice)  # Create instance without calling __init__
    # Test frustrated
    assert voice.detect_emotion_from_text("Estou frustrado") == "frustrated"
    assert voice.detect_emotion_from_text("Estou irritado") == "frustrated"
    assert voice.detect_emotion_from_text("Estou chateado") == "frustrated"
    assert voice.detect_emotion_from_text("Isso é uma merda") == "frustrated"
    # Test happy
    assert voice.detect_emotion_from_text("Estou feliz") == "happy"
    assert voice.detect_emotion_from_text("Estou contente") == "happy"
    assert voice.detect_emotion_from_text("Que ótimo") == "happy"
    assert voice.detect_emotion_from_text("Estou alegre") == "happy"
    # Test neutral
    assert voice.detect_emotion_from_text("") == "neutral"
    assert voice.detect_emotion_from_text("Hello world") == "neutral"
    assert voice.detect_emotion_from_text("Qual é a hora?") == "neutral"

def test_adjust_response_for_emotion():
    voice = GeminiLiveVoice.__new__(GeminiLiveVoice)
    # Test neutral returns same response
    assert voice._adjust_response_for_emotion("Hello", "neutral") == "Hello"
    assert voice._adjust_response_for_emotion("", "neutral") == ""
    assert voice._adjust_response_for_emotion("Hello", "") == "Hello"
    # Test frustrated
    assert voice._adjust_response_for_emotion("Hello", "frustrated") == "Entendo sua frustração. Hello"
    # Test happy
    assert voice._adjust_response_for_emotion("Hello", "happy") == "Que ótimo que você está feliz! Hello"
    # Test unknown emotion defaults to returning response unchanged
    assert voice._adjust_response_for_emotion("Hello", "unknown") == "Hello"
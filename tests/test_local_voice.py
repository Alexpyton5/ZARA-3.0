import os
import sys
import tempfile
from pathlib import Path

# Ensure we are using the project's core
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def faster_whisper_model_exists(config):
    """Check if faster-whisper model exists according to the same logic as in FasterWhisperSTT."""
    # Determine model path
    if config.faster_whisper_model_path:
        model_path = Path(config.faster_whisper_model_path)
        return model_path.exists()
    else:
        # Use default location in user data dir
        from core.paths import user_data_dir
        model_dir = user_data_dir() / "models" / "faster-whisper"
        model_dir.mkdir(parents=True, exist_ok=True)
        model_path = model_dir / config.faster_whisper_model_size
        return model_path.exists()

def test_voice_pipeline_without_api_keys(modelos_de_voz_reais):
    """Test that VoicePipeline initializes without API keys and uses local STT.

    Needs the real (read-only) Vosk model tree; `modelos_de_voz_reais` lends it
    into the isolated ZARA3_HOME so the pipeline can load a real model without
    the test ever writing to the owner's data tree.
    """
    # Backup and unset API key environment variables
    backup = {}
    for key in ['GEMINI_API_KEY', 'GOOGLE_API_KEY', 'PORCUPINE_ACCESS_KEY']:
        backup[key] = os.environ.get(key)
        os.environ[key] = ''

    try:
        from core.voice_stt import create_voice_pipeline, VoiceConfig

        def on_wake(): pass
        def on_speech(text): pass
        def on_partial(text): pass
        def on_level(level): pass

        # This should not raise an error
        pipeline = create_voice_pipeline(
            on_wake=on_wake,
            on_speech=on_speech,
            on_partial=on_partial,
            on_level=on_level,
            access_key=''  # explicit
        )

        # Initialize the pipeline (loads models, etc.)
        pipeline.initialize()

        # We should have an STT backend (VoskSTT)
        # The pipeline uses self.vosk as the active STT
        assert pipeline.vosk is not None
        # We should have audio input
        assert pipeline.audio is not None

        # Check which STT is being used - we expect VoskSTT
        from core.voice_stt import VoskSTT
        assert isinstance(pipeline.vosk, VoskSTT), f"Expected VoskSTT, got {type(pipeline.vosk)}"

        # Clean up
        pipeline.stop()
    finally:
        # Restore environment
        for key, value in backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_tts_manager_without_api_keys():
    """Test that TTSManager initializes without API keys and uses local TTS."""
    # Backup and unset API key environment variables
    backup = {}
    for key in ['GEMINI_API_KEY', 'GOOGLE_API_KEY']:
        backup[key] = os.environ.get(key)
        os.environ[key] = ''

    try:
        from core.voice_tts import create_tts_manager

        # This should not raise an error
        manager = create_tts_manager(
            prefer_local=True,
            gemini_api_key='',  # explicit
            default_voice='pf_dora',
            edge_voice='pt-BR-FranciscaNeural'
        )

        # We should have at least one TTS engine (Edge or Kokoro)
        assert manager.edge is not None or manager.kokoro is not None

        # Clean up
        manager.cleanup()
    finally:
        # Restore environment
        for key, value in backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == '__main__':
    # Rodando fora do pytest não existe fixture: aqui os modelos reais já são
    # os do ambiente real, então basta chamar com o caminho deles.
    from core.paths import user_data_dir

    test_voice_pipeline_without_api_keys(user_data_dir() / "models")
    test_tts_manager_without_api_keys()
    print("All tests passed.")
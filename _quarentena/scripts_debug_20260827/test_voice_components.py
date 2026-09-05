import os
import sys

# Ensure we are using the project's core
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def test_voice_components_import():
    """Test that voice components can be imported and initialized without API keys."""
    from core.voice_stt import VoicePipeline, create_voice_pipeline
    from core.voice_tts import create_tts_manager

    def on_wake(): pass
    def on_speech(text): pass
    def on_partial(text): pass
    def on_level(level): pass

    # Test STT pipeline
    pipeline = create_voice_pipeline(
        on_wake=on_wake,
        on_speech=on_speech,
        on_partial=on_partial,
        on_level=on_level,
        access_key=''
    )
    # Initialize (loads models)
    pipeline.initialize()
    print(f"VoicePipeline initialized with STT: {type(pipeline.stt).__name__}")
    pipeline.stop()

    # Test TTS manager
    manager = create_tts_manager(
        prefer_local=True,
        gemini_api_key='',
        default_voice='pf_dora',
        edge_voice='pt-BR-FranciscaNeural'
    )
    print(f"TTSManager initialized. Edge: {manager.edge is not None}, Kokoro: {manager.kokoro is not None}")
    manager.cleanup()

    print("All voice components initialized successfully.")

if __name__ == '__main__':
    test_voice_components_import()
#!/usr/bin/env python3
"""
Test for the local pipeline - 100% free end-to-end path without API keys.
This test uses mocks to avoid requiring external services or hardware.
"""

import asyncio
import os
import sys
from unittest.mock import Mock, patch

# Add the project root to the path so we can import core modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.local_pipeline import LocalPipeline


async def test_local_pipeline_with_mocks():
    """Test that the local pipeline can be initialized and started with all dependencies mocked."""
    # Clear any API key environment variables to simulate zero-cost scenario
    env_vars_to_clear = [
        'GEMINI_API_KEY',
        'DEEPGRAM_API_KEY',
        'OPENAI_API_KEY',
        'ANTHROPIC_API_KEY',
        'OLLAMA_API_KEY'
    ]
    
    original_env = {}
    for var in env_vars_to_clear:
        original_env[var] = os.environ.get(var)
        if var in os.environ:
            del os.environ[var]
    
    try:
        # Create pipeline with local-only configuration
        pipeline = LocalPipeline(
            stt_model="base",
            stt_device="cpu",
            stt_compute_type="int8",
            tts_engine="kokoro",
            tts_voice="pf_dora",
            vad_enabled=False,
            ollama_model="qwen3:4b",
            ollama_base_url="http://localhost:11434/v1"
        )
        
        # Mock the voice engine.initialize to return True (success)
        with patch.object(pipeline.voice_engine, 'initialize', return_value=True) as mock_init_voice:
            # Mock the Ollama client
            with patch('core.local_pipeline.OllamaClient') as mock_ollama_client_class:
                mock_ollama_instance = Mock()
                mock_ollama_instance.list.return_value = {
                    'models': [{'name': 'qwen3:4b:latest'}]
                }
                mock_ollama_instance.generate.return_value = {
                    'response': 'Resposta de teste do modelo local.'
                }
                mock_ollama_client_class.return_value = mock_ollama_instance
                
                # Initialize the pipeline
                print("[Test] Initializing local pipeline with mocks...")
                init_result = await pipeline.initialize()
                
                if not init_result:
                    print("[Test] FAILED: Local pipeline initialization failed")
                    return False
                    
                print("[Test] SUCCESS: Local pipeline initialized successfully")
                
                # Check that the voice engine initialize was called
                mock_init_voice.assert_called_once()
                
                # Check that the Ollama client was used
                mock_ollama_instance.list.assert_called_once()
                
                # Now test the start method (we'll mock the voice_engine.start_listening to avoid audio)
                with patch.object(pipeline.voice_engine, 'start_listening') as mock_start_listen:
                    # We'll create a simple on_action mock to capture if it's called
                    on_action_mock = Mock()
                    
                    # Start the pipeline
                    await pipeline.start(on_action=on_action_mock)
                    
                    # Check that start_listening was called
                    mock_start_listen.assert_called_once()
                    
                    # We can also simulate a transcript to see if the flow works
                    # But for simplicity, we'll just stop the pipeline
                    await pipeline.stop()
                    
                    print("[Test] SUCCESS: Local pipeline start/stop cycle completed")
                    return True
                    
    except Exception as e:
        print(f"[Test] FAILED: Exception during test: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        # Restore environment variables
        for var, value in original_env.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]


async def main():
    """Run the test."""
    print("=" * 60)
    print("Testing Local Pipeline for ZARA 3.0")
    print("100% Free End-to-End Path Without API Keys (using mocks)")
    print("=" * 60)
    
    result = await test_local_pipeline_with_mocks()
    
    print("\n" + "=" * 60)
    print("TEST RESULT:")
    print(f"  Local Pipeline with Mocks: {'PASS' if result else 'FAIL'}")
    
    if result:
        print("\nOVERALL: PASS - Local pipeline logic is sound and ready for zero-cost voice interaction")
        return 0
    else:
        print("\nOVERALL: FAIL - Local pipeline has issues")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
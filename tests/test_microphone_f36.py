"""
Tests for F3.6: Microphone absent or denied without freezing ZARA.

These tests verify that:
1. Microphone permission denied errors are handled gracefully
2. Missing microphone errors are handled gracefully
3. ZARA continues operating without freezing
4. No retry loops on permanent failures
"""

import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import pytest

# Add project root to path
sys.path.insert(0, "/c/Users/alexp/Downloads/ZARA 3.0 CLEAN 002")

from core.gemini_live_voice import (
    GeminiLiveVoice,
    GeminiLiveVoiceConfig,
)
from core.voice_stt import (
    AudioInput,
    VoiceConfig,
    VoiceNotConfiguredError,
    VoicePipeline,
)


class TestMicrophoneMissingOrDenied:
    """Tests for microphone missing or denied scenarios."""

    @pytest.fixture
    def voice_config(self):
        return GeminiLiveVoiceConfig(api_key="test", audio_transport="local")

    @pytest.mark.asyncio
    async def test_microphone_permission_denied_graceful_failure(self, voice_config, monkeypatch):
        """Test that microphone permission denied fails gracefully without freezing ZARA."""
        _install_live_dependencies(monkeypatch)
        voice = GeminiLiveVoice(voice_config)

        # Mock client.aio.live.connect to succeed
        session = _WaitingSession()
        fake_client = SimpleNamespace()
        fake_client.aio = SimpleNamespace()
        fake_client.aio.live = SimpleNamespace()
        fake_client.aio.live.connect = Mock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=session), __aexit__=AsyncMock()))
        
        import google.genai as genai
        monkeypatch.setattr(genai, "Client", Mock(return_value=fake_client))
        
        # Mock _open_streams to return False with permanent failure flag set
        def failing_open_streams(_sd, _gen):
            import sounddevice as sd
            voice._mic_permanent_failure = True
            return False
        
        monkeypatch.setattr(voice, "_open_streams", failing_open_streams)
        
        # Start should fail gracefully with clear error
        with pytest.raises(RuntimeError, match="VOICE_MIC_PERMANENT_FAILURE"):
            await voice.start(timeout=0.1)
        
        # Verify voice is not active
        assert voice.active is False
        assert voice.connected is False

    @pytest.mark.asyncio
    async def test_microphone_missing_graceful_failure(self, voice_config, monkeypatch):
        """Test that missing microphone fails gracefully without freezing ZARA."""
        _install_live_dependencies(monkeypatch)
        voice = GeminiLiveVoice(voice_config)

        # Mock client connection
        session = _WaitingSession()
        fake_client = SimpleNamespace()
        fake_client.aio = SimpleNamespace()
        fake_client.aio.live = SimpleNamespace()
        fake_client.aio.live.connect = Mock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=session), __aexit__=AsyncMock()))
        
        import google.genai as genai
        monkeypatch.setattr(genai, "Client", Mock(return_value=fake_client))
        
        # Mock _open_streams to return False with permanent failure flag set
        def failing_open_streams(_sd, _gen):
            import sounddevice as sd
            voice._mic_permanent_failure = True
            return False
        
        monkeypatch.setattr(voice, "_open_streams", failing_open_streams)
        
        # Start should fail gracefully
        with pytest.raises(RuntimeError, match="VOICE_MIC_PERMANENT_FAILURE"):
            await voice.start(timeout=0.1)
        
        # Verify voice is not active
        assert voice.active is False

    @pytest.mark.asyncio
    async def test_microphone_invalid_device_graceful_failure(self, voice_config, monkeypatch):
        """Test that invalid device ID fails gracefully."""
        _install_live_dependencies(monkeypatch)
        voice = GeminiLiveVoice(voice_config)

        # Mock client connection
        session = _WaitingSession()
        fake_client = SimpleNamespace()
        fake_client.aio = SimpleNamespace()
        fake_client.aio.live = SimpleNamespace()
        fake_client.aio.live.connect = Mock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=session), __aexit__=AsyncMock()))
        
        import google.genai as genai
        monkeypatch.setattr(genai, "Client", Mock(return_value=fake_client))
        
        # Mock _open_streams to return False with permanent failure flag set
        def failing_open_streams(_sd, _gen):
            import sounddevice as sd
            voice._mic_permanent_failure = True
            return False
        
        monkeypatch.setattr(voice, "_open_streams", failing_open_streams)
        
        with pytest.raises(RuntimeError, match="VOICE_MIC_PERMANENT_FAILURE"):
            await voice.start(timeout=0.1)
        
        assert voice.active is False

    @pytest.mark.asyncio
    async def test_audio_input_permission_denied(self, monkeypatch):
        """Test AudioInput handles permission denied gracefully."""
        config = VoiceConfig()
        
        # Mock sounddevice to raise PortAudioError
        import sounddevice as sd
        
        class MockSoundDevice:
            PortAudioError = sd.PortAudioError
            
            @staticmethod
            def RawInputStream(*args, **kwargs):
                raise sd.PortAudioError("Permission denied", -9985)
        
        monkeypatch.setattr("core.voice_stt.sd", MockSoundDevice())
        
        audio = AudioInput(config)
        
        with pytest.raises(VoiceNotConfiguredError, match="AUDIO_INPUT_FAILED.*permanent=True"):
            audio.start()

    @pytest.mark.asyncio
    async def test_audio_input_device_unavailable(self, monkeypatch):
        """Test AudioInput handles device unavailable gracefully."""
        config = VoiceConfig()
        
        import sounddevice as sd
        
        class MockSoundDevice:
            PortAudioError = sd.PortAudioError
            
            @staticmethod
            def RawInputStream(*args, **kwargs):
                raise sd.PortAudioError("Device unavailable", -9985)
        
        monkeypatch.setattr("core.voice_stt.sd", MockSoundDevice())
        
        audio = AudioInput(config)
        
        with pytest.raises(VoiceNotConfiguredError, match="AUDIO_INPUT_FAILED.*permanent=True"):
            audio.start()

    @pytest.mark.asyncio
    async def test_voice_pipeline_handles_audio_start_failure(self, monkeypatch):
        """Test VoicePipeline handles audio start failure gracefully."""
        config = VoiceConfig()
        config.vosk_model_path = ""  # Will fail to load
        
        # Mock VoskSTT to avoid model loading
        class MockVosk:
            def __init__(self, config):
                pass
            def recognize(self, data):
                return None
            def partial_recognize(self, data):
                return None
            def reset(self):
                pass
        
        monkeypatch.setattr("core.voice_stt.VoskSTT", MockVosk)
        
        # Mock AudioInput to fail
        import sounddevice as sd
        
        class MockSoundDevice:
            PortAudioError = sd.PortAudioError
            
            @staticmethod
            def RawInputStream(*args, **kwargs):
                raise sd.PortAudioError("Permission denied", -9985)
        
        monkeypatch.setattr("core.voice_stt.sd", MockSoundDevice())
        
        from core.voice_stt import VoicePipeline
        
        # Create pipeline with error callback
        errors = []
        def on_error(e):
            errors.append(e)
        
        pipeline = VoicePipeline(
            config,
            on_wake=lambda: None,
            on_speech=lambda t: None,
            on_partial=lambda t: None,
            on_level=lambda l: None,
        )
        # Add on_error attribute
        pipeline.on_error = on_error
        
        # Start should not crash
        pipeline.start()
        
        # Give it time to try starting
        await asyncio.sleep(0.1)
        
        # Pipeline should be in ERROR state
        assert pipeline.state == "ERROR"
        assert len(errors) == 1
        assert "AUDIO_INPUT_FAILED" in str(errors[0])

    def test_audio_input_keeps_first_callback_frame(self, monkeypatch):
        """A synchronous PortAudio callback must not lose the first frame."""
        config = VoiceConfig()
        seen = []

        class Stream:
            def __init__(self, callback):
                self.callback = callback

            def start(self):
                self.callback(bytes([1, 2]), 1, None, None)

            def stop(self):
                pass

            def close(self):
                pass

        class MockSoundDevice:
            PortAudioError = Exception

            @staticmethod
            def RawInputStream(*args, **kwargs):
                callback = kwargs["callback"]
                return Stream(callback)

        monkeypatch.setattr("core.voice_stt.sd", MockSoundDevice())
        audio = AudioInput(config)
        # The callback is installed by AudioInput.start; capture its result
        # through the public queue rather than reaching into implementation.
        audio.start()
        assert audio.read(timeout=0.01) == bytes([1, 2])
        audio.stop()

    @pytest.mark.asyncio
    async def test_voice_pipeline_can_retry_after_audio_open_failure(self, monkeypatch):
        """A failed start must not poison the pipeline's next start attempt."""
        config = VoiceConfig()

        class MockVosk:
            def __init__(self, _config):
                pass

            def reset(self):
                pass

        class FlakyAudio:
            attempts = 0

            def __init__(self, _config):
                self.running = False

            def start(self):
                type(self).attempts += 1
                if type(self).attempts == 1:
                    raise VoiceNotConfiguredError("AUDIO_INPUT_FAILED: denied permanent=True")
                self.running = True

            def stop(self):
                self.running = False

            def read(self, timeout=0.1):
                return None

        monkeypatch.setattr("core.voice_stt.VoskSTT", MockVosk)
        monkeypatch.setattr("core.voice_stt.AudioInput", FlakyAudio)
        errors = []
        pipeline = VoicePipeline(config, lambda: None, lambda _text: None)
        pipeline.on_error = errors.append

        pipeline.start()
        assert pipeline.state == "ERROR"
        assert pipeline._running is False

        pipeline.start()
        await asyncio.sleep(0.02)
        assert pipeline.state == "LISTENING"
        assert pipeline._running is True
        pipeline.stop()

    def test_current_pipeline_reports_native_audio_failure_without_false_listening(
        self, monkeypatch
    ):
        """The removed legacy LocalVoiceEngine is not part of the current runtime."""
        class MockVosk:
            def __init__(self, _config):
                pass

            def reset(self):
                pass

        class BrokenAudio:
            stopped = False

            def __init__(self, _config):
                pass

            def start(self):
                raise OSError("No audio input device")

            def stop(self):
                self.stopped = True

        monkeypatch.setattr("core.voice_stt.VoskSTT", MockVosk)
        monkeypatch.setattr("core.voice_stt.AudioInput", BrokenAudio)
        errors = []
        pipeline = VoicePipeline(VoiceConfig(), lambda: None, lambda _text: None)
        pipeline.on_error = errors.append

        pipeline.start()

        assert pipeline.state == "ERROR"
        assert pipeline._running is False
        assert isinstance(errors[0], OSError)
        assert pipeline.audio.stopped is True


def _install_live_dependencies(monkeypatch):
    """Install fake modules for google.genai and sounddevice."""
    fake_genai = SimpleNamespace()
    fake_types = SimpleNamespace()
    fake_google = SimpleNamespace(genai=fake_genai)
    
    # Mock sounddevice
    import sounddevice as sd
    fake_sd = Mock()
    fake_sd.PortAudioError = sd.PortAudioError
    fake_sd.RawInputStream = Mock()
    fake_sd.query_devices = Mock(return_value=[])
    fake_sd.default = SimpleNamespace(device=(None, None))
    
    monkeypatch.setitem(sys.modules, "sounddevice", fake_sd)
    monkeypatch.setitem(sys.modules, "google", fake_google)
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)
    fake_genai.types = fake_types
    # Add Client to fake_genai
    fake_genai.Client = Mock()
    
    # Mock types
    fake_types.LiveConnectConfig = Mock()
    fake_types.SpeechConfig = Mock()
    fake_types.VoiceConfig = Mock()
    fake_types.PrebuiltVoiceConfig = Mock()
    fake_types.AudioTranscriptionConfig = Mock()
    fake_types.ContextWindowCompressionConfig = Mock()
    fake_types.SlidingWindow = Mock()
    fake_types.SessionResumptionConfig = Mock()
    fake_types.Content = Mock()
    fake_types.Part = Mock()
    fake_types.RealtimeInputConfig = Mock()
    fake_types.AutomaticActivityDetection = Mock()
    fake_types.EndSensitivity = SimpleNamespace(
        END_SENSITIVITY_HIGH=1,
        END_SENSITIVITY_LOW=2
    )
    fake_types.Blob = Mock()


class _WaitingSession:
    def __init__(self):
        self.release = asyncio.Event()

    async def receive(self):
        await self.release.wait()
        if False:
            yield None


if __name__ == "__main__":
    pytest.main([__file__, "-xvs"])

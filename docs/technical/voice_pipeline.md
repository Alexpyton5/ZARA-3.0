# Voice Pipeline in ZARA 3.0

## Overview

ZARA 3.0 uses a sophisticated voice pipeline for low-latency, high-quality voice interactions with Alex. The pipeline handles wake word detection, speech-to-text, and text-to-speech with special considerations for barge-in, echo cancellation, and natural conversation flow.

## Voice Pipeline Components

The voice pipeline consists of several key components working together:

1. **Wake Word Detection** - Uses Porcupine for efficient, always-listening wake word detection
2. **Speech-to-Text (STT)** - Uses Vosk for offline, real-time transcription
3. **Text-to-Speech (TTS)** - Multiple providers available (Edge TTS, ElevenLabs, etc.)
4. **Audio Processing** - Handles microphone input and speaker output with echo cancellation
5. **Conversation Management** - Tracks turn-taking, barge-in detection, and context

## Configuration

Voice pipeline configuration is stored in `~/.hermes/config.yaml` under the `stt` and `tts` sections:

```yaml
stt:
  enabled: true
  provider: local   # local (faster-whisper, free) | groq | openai | mistral | elevenlabs | deepinfra
  local:
    model: base     # tiny, base, small, medium, large-v3

tts:
  provider: edge/elevenlabs/openai/minimax/mistral/neutts/gemini/piper/kittentts/deepinfra/xai
```

For ZARA-specific voice configuration, settings are in `core/gemini_live_voice.py` and can be overridden via `api_keys.json`:

```json
{
  "wake_word_mode": "local",  // or "disabled" for Gemini Live wake word
  "vad_silencio_ms": 300,     // Voice activity detection silence threshold
  "audio_transport": "renderer" // or "local" for direct audio
}
```

## Voice Pipeline Flow

### Initialization
1. Load voice configuration from config files
2. Initialize Vosk STT model (downloads if needed)
3. Initialize Porcupine wake word detection (if access key provided)
4. Set up audio input/output devices
5. Prepare TTS engine

### Listening Loop
1. Continuously capture audio from microphone
2. Process audio through Porcupine for wake word detection
3. When wake word detected, switch to listening mode
4. Capture audio until voice activity ends
5. Process captured audio through Vosk for transcription
6. Send transcribed text to intent processing

### Response Generation
1. Process intent and generate response text
2. Send response text to TTS engine
3. Play audio through speakers
4. Apply echo cancellation to prevent self-listening
5. Return to listening mode

### Barge-in Handling
1. During TTS playback, continue monitoring microphone
2. If user speaks during response, detect as barge-in
3. Interrupt TTS and process the interruption as a new command
4. This enables natural conversation flow

## ZARA-Specific Features

### Wake Word Modes
- **Local Wake Word** (Porcupine): Always listening, low power, customizable wake words
- **Gemini Live Wake Word**: Uses Gemini's built-in wake word detection (requires audio to be sent to Gemini continuously)

### Echo Cancellation
ZARA implements two levels of echo cancellation:
1. **Hardware/Echo Cancellation**: Uses Chromium's AEC when audio_transport is set to "renderer"
2. **Software Echo Cancellation**: Uses content-based filtering in `_looks_like_own_echo` to filter out ZARA's own speech from microphone input

### Voice Activity Detection (VAD)
Configurable VAD parameters:
- `vad_silencio_ms`: Silence threshold to detect end of utterance
- `vad_padding_ms`: Padding added to speech segments
- `vad_fim_sensibel`: Whether to use sensitive VAD for end detection

### Vocabulary Correction
Deterministic correction of known misrecognitions:
- "Cláudio" → "Claude"
- "corei" → "Kore"
- "zarah" → "ZARA"
- And others defined in `_NOMES_DA_CASA`

## Implementation Details

### Core Files
- `core/gemini_live_voice.py`: Main Gemini Live voice integration
- `core/voice_stt.py`: Vosk + Porcupine voice pipeline
- `core/voice_tts.py`: TTS abstraction layer
- `core/windows_audio.py`: Windows-specific audio controls
- `core/ipc_handlers.py`: IPC handlers that integrate voice with the rest of ZARA

### Voice Pipeline Class
The `VoicePipeline` class in `voice_stt.py` manages:
- Audio input via `sounddevice`
- Wake word detection via `PorcupineWakeWord`
- Speech-to-text via `VoskSTT`
- Callback handling for wake, speech, partial results, and audio levels
- Thread management for real-time processing

### Integration with IPC
Voice events are handled in `ipc_handlers.py`:
- `_on_gemini_live_voice_wake`: Handles wake word detection
- `_on_gemini_live_voice_turn`: Processes transcribed speech
- `_on_gemini_live_voice_level`: Updates audio level visualization
- Voice state tracking for speaking/listening states

## Usage and Commands

### Voice Control Commands
- `/voice on` - Enable voice-to-voice mode
- `/voice tts` - Always respond with voice (even to text input)
- `/voice off` - Disable voice input/output

### Configuration Commands
- `hermes model` - Configure voice models for STT/TTS
- `hermes config set stt.provider <provider>` - Change STT provider
- `hermes config set tts.provider <provider>` - Change TTS provider

### Debugging
- Voice events are logged to `~/.hermes/logs/agent.log`
- Audio levels can be monitored via the frontend interface
- Voice pipeline status is available in the Hermes dashboard

## Best Practices

1. **Wake Word Selection**: Choose distinctive wake words to minimize false positives
2. **VAD Tuning**: Adjust silence thresholds based on environment and speaking style
3. **Echo Cancellation Testing**: Test in the actual usage environment to tune echo cancellation
4. **Language Consistency**: Ensure STT, TTS, and language models are configured for the same language
5. **Performance Monitoring**: Monitor CPU usage of voice components, especially on lower-end hardware

## Troubleshooting

### No Voice Response
1. Check if voice is enabled: `/voice status`
2. Verify microphone is working and not muted
3. Check audio output device and volume
4. Look for errors in agent.log related to voice initialization

### False Wake Word Triggers
1. Increase Porcupine sensitivity in voice config
2. Choose a more distinctive wake word
3. Check for ambient noise that might trigger false positives

### Missed Wake Words
1. Decrease Porcupine sensitivity
2. Check microphone placement and gain
3. Verify wake word model is properly loaded

### Echo Issues
1. Ensure echo cancellation is enabled in configuration
2. Test with `audio_transport` set to "renderer" for best echo cancellation
3. Adjust microphone and speaker placement to reduce coupling

### High CPU Usage
1. Consider using a smaller Vosk model
2. Reduce audio sample rate if supported
3. Check for audio driver issues causing excessive interrupts

## References

- Vosk Documentation: https://alphacephei.com/vosk/
- Porcupine Documentation: https://picovoice.ai/docs/porcupine/
- Gemini Live API: https://ai.google.dev/gemini-live
- WebRTC Echo Cancellation: https://webrtc.org/echo-cancellation/
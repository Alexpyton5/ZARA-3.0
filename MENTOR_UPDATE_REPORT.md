# ZARA CLEAN-003 — Gemini Live/Kore + AI Engine Selector

Base: CLEAN-002, already validated as opening correctly on Alex's machine.

## Added
- Persistent Gemini Live native-audio session (`gemini-3.1-flash-live-preview`).
- Kore prebuilt voice.
- 16 kHz PCM16 microphone input and 24 kHz PCM16 speaker output.
- 40 ms microphone chunks for low-latency streaming.
- Barge-in/interruption handling.
- Input/output transcription into ZARA Conversation Log and episodic memory.
- Context window compression and session resumption.
- Particle level driven by real microphone/output PCM amplitude.
- Key-aware AI ENGINE selector in the existing top bar.
- Engine preference persisted as `ai_engine` without exposing API keys.

## Text engines in registry (shown only when corresponding key exists)
- NVIDIA Nemotron 3 Ultra 550B (`nvidia/nemotron-3-ultra-550b-a55b`)
- Groq GPT-OSS 120B (`openai/gpt-oss-120b`)
- Groq Llama 3.3 70B (`llama-3.3-70b-versatile`)
- Gemini 2.5 Flash (`gemini-2.5-flash`)
- Gemini 3.1 Flash-Lite (`gemini-3.1-flash-lite`)
- Z.AI GLM-4.7 Flash (`glm-4.7-flash`)
- xAI Grok 4.5 (`grok-4.5`)
- AUTO • ZARA ROUTER

Gemini Live is deliberately a dedicated voice transport and does not appear as a text-chat engine. Hermes Gateway is deliberately controlled only by the Supercérebro switch.

## Removed from selectable registry
- Groq Mixtral 8x7B: provider model was retired.
- Old Groq Nemotron placeholder: replaced by current Groq GPT-OSS 120B.
- Old NVIDIA Nemotron placeholder API id: replaced by current NVIDIA id.
- Z.AI GLM-4.5 default: replaced by current free GLM-4.7 Flash.

## Dependencies
- `google-genai>=2.13.0`
- existing `sounddevice` and `numpy` are reused.

## Security
- No real API key is included in this package.
- Python sidecar reads existing provider keys from the existing ZARA config path.
- Renderer receives only engine metadata, never secret values.

## Validation performed by Mentor
- Python `compileall`: PASS.
- Python model registry / helper smoke test: PASS.
- TypeScript/TSX syntax transpilation with TypeScript 5.8.3: PASS.
- Real API/network call: intentionally not executed because Alex's keys are not copied into Mentor artifacts.
- Final Windows/PyInstaller/Electron build must be performed by Hermes on Alex's machine.

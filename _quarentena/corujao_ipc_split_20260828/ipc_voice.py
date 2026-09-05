# core/ipc_voice.py
"""
IPC Voice - Voice pipeline, Gemini Live, wake word, barge-in, AEC.
Extracted from IPCHandler (God Class decomposition).
"""
from __future__ import annotations

import asyncio
import time
import os
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from core.ipc_protocol import IPCMessage
from core.pc_voice_intent import RESPOSTA_NAO_SEI
from core.action_registry import ActionResult, execute_action


class IPCVoice:
    """Handles all voice-related IPC and pipeline management."""

    def __init__(self, send_callback: Callable[[IPCMessage], Awaitable[None]]):
        self.send = send_callback
        self._handler: "IPCHandler" = None

        # Voice pipeline state
        self.voice_pipeline: "VoicePipeline" = None
        self.tts_manager: "TTSManager" = None
        self._voice_level: float = 0.0
        self._voice_tone: float = 0.5
        self._voice_speaking: bool = False
        self._assistant_output_active: bool = False
        self._assistant_output_text: str = ""
        self._assistant_output_protect_until: float = 0.0
        self._recent_assistant_outputs: deque[tuple[str, float]] = deque(maxlen=3)
        self._voice_last_error: str | None = None
        self._voice_loop_task: asyncio.Task = None
        self._voice_start_lock = asyncio.Lock()
        self._tts_initialized: bool = False
        self.gemini_live_voice: "GeminiLiveVoice" = None
        self.voice_mode: str = "off"
        self._gemini_wake_armed_until: float = 0.0
        self._voice_turn_started: float = 0.0
        self._last_spoken_text: str = ""
        self._fala_interrompida: bool = False  # ZARA-VOZ-UNICA-002

    def bind_handler(self, handler: "IPCHandler") -> None:
        self._handler = handler

    # ----- Gemini Live Configuration -----
    def _build_gemini_live_config(self, gemini_key: str):
        """Build Gemini Live voice config."""
        from google.generativeai.types import GenerationConfig, SafetySettingDict, HarmCategory, HarmBlockThreshold
        from core.gemini_live_voice import GeminiLiveVoiceConfig

        return GeminiLiveVoiceConfig(
            api_key=gemini_key or os.environ.get("GEMINI_API_KEY", ""),
            model="models/gemini-1.5-pro-latest",
            voice_name="Kore",
            generation_config=GenerationConfig(
                temperature=0.7,
                top_p=0.95,
                top_k=40,
                max_output_tokens=2048,
            ),
            safety_settings=[
                SafetySettingDict(
                    category=HarmCategory.HARM_CATEGORY_HARASSMENT,
                    threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                ),
                SafetySettingDict(
                    category=HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                    threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                ),
                SafetySettingDict(
                    category=HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                    threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                ),
                SafetySettingDict(
                    category=HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                    threshold=HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
                ),
            ],
        )

    # ----- Gemini Live Callbacks -----
    async def _on_gemini_live_output_audio(self, audio: bytes) -> None:
        """Handle audio output from Gemini Live."""
        if self.tts_manager and self.voice_mode == "gemini_live":
            await self.tts_manager.play_audio(audio)
        # Forward to frontend for local playback/visualization
        await self.send_event('voice-output-audio', {'audio': audio.hex()})

    async def handle_voice_mic_chunk(self, msg: IPCMessage) -> None:
        """Handle microphone chunk from frontend."""
        audio_data = bytes.fromhex(msg.payload.get('audio', '')) if msg.payload else b''
        if self.gemini_live_voice and self.voice_active:
            await self.gemini_live_voice.process_audio(audio_data)

    async def _on_gemini_live_state(self, state: str) -> None:
        """Gemini Live state change."""
        await self.send_event('voice-state-change', {'state': state})

    async def _on_gemini_live_level(self, level: float, speaking: bool) -> None:
        """Audio level from Gemini Live."""
        self._voice_level = level
        self._voice_speaking = speaking
        await self.send_event('voice-level', {
            'level': level,
            'tone': self._voice_tone,
            'speaking': speaking,
            'state': 'SPEAKING' if speaking else 'LISTENING'
        })

    def _voice_turn_needs_executor(self, command: str) -> bool:
        """Check if voice command needs action executor."""
        # Delegated to intent detection - for now, conservatively true for PC intents
        from core.pc_voice_intent import _looks_like_unhandled_local_action
        return bool(_looks_like_unhandled_local_action(command))

    def _voice_turn_is_echo_suspect(self) -> bool:
        """Check if current turn might be echo."""
        # Simple heuristic: if we just spoke and heard similar text quickly
        return (
            self._assistant_output_active and
            time.monotonic() - self._assistant_output_protect_until < 1.0
        )

    def _voice_can_answer_directly(self, user_text: str) -> bool:
        """Check if can answer directly without action."""
        # Non-action queries: greetings, status, knowledge, etc.
        direct_patterns = [
            r'^(oi|olá|hey|ei|bom\s+dia|boa\s+tarde|boa\s+noite)[\s,;:!.-]*$',
            r'^(como\s+vai|tudo\s+bem|tudo\s+ok|beleza|joia)[\s,;:!.-]*$',
            r'^(que\s+horas\s+são|que\s+dia\s+é\s+hoje|qual\s+é\s+a\s+data)[\s,;:!?.-]*$',
            r'^(o\s+que\s+você\s+aprendeu|meu\s+nome\s+é|qual\s+é\s+o\s+meu\s+nome)[\s,;:!?.-]*$',
            r'^(você\s+está\s+ouvindo|consegue\s+me\s+ouvir|sistema\s+online)[\s,;:!?.-]*$',
        ]
        import re
        return any(re.match(pattern, user_text.strip(), re.I) for pattern in direct_patterns)

    def _anotar_turno_descartado(self, texto: str, motivo: str) -> None:
        """Log discarded turn."""
        if self._handler and hasattr(self._handler, 'conversation_history'):
            # This would normally go to conversation history logging
            pass  # Implemented in handler if needed

    async def _begin_assistant_output(self, text: str) -> None:
        """Mark assistant output start."""
        self._assistant_output_active = True
        self._assistant_output_text = text
        self._assistant_output_protect_until = time.monotonic() + 2.0
        self._recent_assistant_outputs.append((text, time.monotonic()))
        # Notify frontend of assistant speaking start
        await self.send_event('assistant-output-start', {'text': text})

    def _finish_assistant_output(self) -> None:
        self._assistant_output_active = False
        self._assistant_output_text = ""
        self._assistant_output_protect_until = 0.0
        # Notify frontend of assistant output end
        # (handled by voice-level event with speaking=False)

    def _voice_elapsed_ms(self) -> float:
        return (time.monotonic() - self._voice_turn_started) * 1000

    async def _on_gemini_live_turn(self, turn_data: dict) -> None:
        """Handle Gemini Live turn completion."""
        # Forward turn info to handler for memory/storage
        if self._handler and hasattr(self._handler, '_anotar_experiencia'):
            user_text = turn_data.get('user_text', '')
            model_text = turn_data.get('model_text', '')
            # Would normally call handler's memory methods here
            pass

    async def _on_gemini_live_interrupt(self) -> None:
        """Handle barge-in interrupt."""
        self._fala_interrompida = True  # ZARA-VOZ-UNICA-002
        self._finish_assistant_output()
        await self.send_event('voice-interrupt', {})
        # Resume listening after interrupt
        if self.voice_active and self.voice_pipeline:
            self.voice_pipeline.resume_listening(require_wake_word=True)

    async def _on_gemini_live_error(self, error: str) -> None:
        """Handle Gemini Live error."""
        self._voice_last_error = error
        await self.send_event('voice-error', {'error': error})

    async def _on_wake_word(self) -> None:
        """Wake word detected."""
        self._voice_turn_started = time.monotonic()
        self._last_spoken_text = ""
        await self.send_event('wake-word-detected', {})
        # Start listening session
        if self.voice_pipeline:
            self.voice_pipeline.start_listening()

    async def _on_voice_level(self, level: float) -> None:
        """Voice level update."""
        self._voice_level = level
        # Only send if changed significantly to reduce noise
        if abs(level - getattr(self, '_last_sent_level', -1)) > 0.1:
            await self.send_event('voice-level', {
                'level': level,
                'tone': self._voice_tone,
                'speaking': self._voice_speaking,
                'state': 'SPEAKING' if self._voice_speaking else 'LISTENING'
            })
            self._last_sent_level = level

    async def _on_partial_speech(self, partial: str) -> None:
        """Partial speech recognition."""
        await self.send_event('voice-partial', {'text': partial})

    async def _on_speech_recognized(self, text: str) -> None:
        """Full speech recognized."""
        self._last_spoken_text = text
        await self.send_event('voice-speech-recognized', {'text': text})

    # ----- Voice Response -----
    async def _speak_response(self, text: str) -> None:
        """Speak response via TTS or Gemini Live."""
        if not text:
            return
        # Mark as assistant output for echo protection
        await self._begin_assistant_output(text)
        # Try TTS first if available and configured
        if self.tts_manager and self.voice_mode != "gemini_live":
            try:
                await self.tts_manager.speak(text)
                await self._finish_assistant_output()
                return
            except Exception as e:
                print(f"[Voice] TTS error: {e}")
                # Fall through to Gemini Live
        # Use Gemini Live for speech
        if self.gemini_live_voice and self.voice_active:
            await self.gemini_live_voice.speak(text)
            # Audio output will come via _on_gemini_live_output_audio
            # We'll wait for a reasonable time then finish output
            await asyncio.sleep(len(text) * 0.1)  # Rough estimate
            await self._finish_assistant_output()
        else:
            # Fallback: just mark as done
            await self._finish_assistant_output()

    def _marcar_valor_no_cronometro(self, nome: str, ms: float) -> None:
        """Latency marking."""
        if self._handler and hasattr(self._handler, 'cronometro'):
            # Delegate to handler's cronometro if available
            try:
                self._handler.cronometro._marcar_valor(nome, ms)
            except AttributeError:
                pass  # Handler may not have cronometro yet
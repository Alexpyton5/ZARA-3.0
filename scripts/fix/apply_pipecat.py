# Apply Pipecat integration to ipc_handlers.py
with open('C:/Users/alexp/Downloads/ZARA 3.0 CLEAN 002/core/ipc_handlers.py', 'rb') as f:
    content = f.read()

# 1. Add _start_pipecat_pipeline method after _build_gemini_live_config
old1 = b'''        return GeminiLiveVoiceConfig(
            api_key=gemini_key,
            voice_name="Kore",
            wake_word_enabled=gate_local,
            audio_transport=transporte,
            vad_silencio_ms=silencio_ms,
        )

    async def _on_gemini_live_output_audio(self, audio: bytes) -> None:'''

new1 = b'''        return GeminiLiveVoiceConfig(
            api_key=gemini_key,
            voice_name="Kore",
            wake_word_enabled=gate_local,
            audio_transport=transporte,
            vad_silencio_ms=silencio_ms,
        )

    async def _start_pipecat_pipeline(self, msg: IPCMessage) -> bool:
        """Start the Pipecat STT\u2192LLM\u2192TTS pipeline with Ollama qwen3:4b and Kokoro."""
        try:
            from core.pipecat_voice_pipeline import ZaraPipecatConfig, ZaraPipecatPipeline
        except ImportError as e:
            print(f"[IPC] Pipecat pipeline not available: {e}")
            return False

        # Get Deepgram API key
        deepgram_key = os.environ.get('DEEPGRAM_API_KEY', '').strip()
        if not deepgram_key:
            print("[IPC] Pipecat pipeline requires DEEPGRAM_API_KEY")
            return False

        config = ZaraPipecatConfig(
            deepgram_api_key=deepgram_key,
            ollama_base_url="http://localhost:11434/v1",
            ollama_model="qwen3:4b",
            kokoro_voice="pf_dora",
            vad_stop_secs=0.2,
            vad_min_volume=0.6,
            transport_type="eval",  # Use eval transport for local testing
        )

        try:
            self.pipecat_pipeline = ZaraPipecatPipeline(config)
            await self.pipecat_pipeline.build()

            # Create transport for Pipecat
            from pipecat.evals.transport import EvalTransportParams
            from pipecat.runner.types import RunnerArguments
            from pipecat.runner.utils import create_transport

            transport = await create_transport(RunnerArguments(), {
                "eval": lambda: EvalTransportParams(audio_in_enabled=True, audio_out_enabled=True)
            })

            # Start pipeline in background
            self._pipecat_task = asyncio.create_task(self.pipecat_pipeline.run(transport))
            self.voice_active = True
            self.voice_mode = 'pipecat'

            print("[IPC] Pipecat voice pipeline started (Deepgram \u2192 Ollama qwen3:4b \u2192 Kokoro)")
            await self.send_response(msg.request_id, {
                'success': True, 'state': 'LISTENING', 'mode': 'pipecat',
                'voice': 'Pipecat STT\u2192LLM\u2192TTS'
            })
            await self.send_event('state-change', 'LISTENING')
            return True

        except Exception as e:
            print(f"[IPC] Pipecat pipeline start error: {e}")
            traceback.print_exc()
            await self.send_error(msg, str(e))
            return False

    async def _on_gemini_live_output_audio(self, audio: bytes) -> None:'''

content = content.replace(old1, new1)

# 2. Replace _handle_voice_start_locked to support Pipecat mode
old2 = b'''    async def _handle_voice_start_locked(self, msg: IPCMessage):
        """Serialize microphone starts without blocking unrelated IPC requests."""
        if self.voice_active:
            if self.gemini_live_voice and self.gemini_live_voice.active:
                await self.send_response(msg.request_id, {
                    'success': True, 'state': 'LISTENING', **self.gemini_live_voice.status()
                })
                return

        gemini_key = os.environ.get('GEMINI_API_KEY', '').strip()
        if gemini_key and GEMINI_LIVE_MODULE_AVAILABLE and GeminiLiveVoice and GeminiLiveVoiceConfig:
            try:
                if not self.gemini_live_voice:
                    self.gemini_live_voice = GeminiLiveVoice(
                        self._build_gemini_live_config(gemini_key),
                        on_state=self._on_gemini_live_state,
                        on_level=self._on_gemini_live_level,
                        on_turn=self._on_gemini_live_turn,
                        # ZARA-VOICE-FLUIDEZ-001: politica CONVERSA/ACAO.
                        can_answer_directly=self._voice_can_answer_directly,
                        on_interrupt=self._on_gemini_live_interrupt,
                        on_error=self._on_gemini_live_error,
                        on_output_audio=self._on_gemini_live_output_audio,
                    )
                status = await self.gemini_live_voice.start(timeout=12.0)
                self.voice_active = True
                self.voice_mode = 'gemini_live'
                print("[IPC] Gemini Live voice started (Kore, wake-gate)")
                await self._ligar_vigia_das_respostas()
                await self.send_response(msg.request_id, {
                    'success': True,
                    'state': status.get('session_state', 'LISTENING'),
                    'wake_mode': bool(status.get('wake_detector_ready')),
                    **status
                })
                return
            except Exception as exc:
                self.voice_active = False
                self.voice_mode = 'off'
                print(f"[IPC] Gemini Live start error: {exc}")
                traceback.print_exc()
                # Fall through to local Vosk. A Gemini Live failure must not
                # turn the microphone button into a dead end.

        # Backward-compatible local path for machines without a Gemini key.
        if not VOICE_AVAILABLE or not self.voice_pipeline:
            await self.send_error(msg, "Gemini API key missing and local voice pipeline unavailable")
            return

        try:
            if not self.voice_pipeline.vosk or not self.voice_pipeline.audio:
                await asyncio.to_thread(self.voice_pipeline.initialize)
            self.voice_pipeline._event_loop = asyncio.get_running_loop()
            await asyncio.to_thread(self.voice_pipeline.start)
            self.voice_active = True
            self.voice_mode = 'local'
            self._voice_last_error = None
            print("[IPC] Local voice pipeline started")
            await self.send_response(msg.request_id, {
                'success': True, 'state': 'LISTENING', 'mode': 'local',
                'voice': 'Kokoro/Vosk fallback'
            })
            await self.send_event('state-change', 'LISTENING')
        except Exception as e:
            self._voice_last_error = str(e).split(':', 1)[0][:120]
            print(f"[IPC] Voice start error: {e}")
            traceback.print_exc()
            await self.send_error(msg, str(e))'''

new2 = b'''    async def _handle_voice_start_locked(self, msg: IPCMessage):
        """Serialize microphone starts without blocking unrelated IPC requests."""
        if self.voice_active:
            if self.gemini_live_voice and self.gemini_live_voice.active:
                await self.send_response(msg.request_id, {
                    'success': True, 'state': 'LISTENING', **self.gemini_live_voice.status()
                })
                return
            # Also check if Pipecat pipeline is active
            if hasattr(self, 'pipecat_pipeline') and self.pipecat_pipeline and self.pipecat_pipeline.is_active():
                await self.send_response(msg.request_id, {
                    'success': True, 'state': 'LISTENING', 'mode': 'pipecat',
                    'voice': 'Pipecat STT\u2192LLM\u2192TTS'
                })
                return

        await self._ensure_voice_prepared()

        # Check requested voice mode from payload
        requested_mode = msg.payload.get('mode', 'auto') if msg.payload else 'auto'

        # Try Pipecat pipeline first if requested or if no Gemini key
        gemini_key = os.environ.get('GEMINI_API_KEY', '').strip()

        if requested_mode == 'pipecat' or not gemini_key:
            # Try Pipecat pipeline
            if await self._start_pipecat_pipeline(msg):
                return

        # Try Gemini Live if key available
        if gemini_key and GEMINI_LIVE_MODULE_AVAILABLE and GeminiLiveVoice and GeminiLiveVoiceConfig:
            try:
                if not self.gemini_live_voice:
                    self.gemini_live_voice = GeminiLiveVoice(
                        self._build_gemini_live_config(gemini_key),
                        on_state=self._on_gemini_live_state,
                        on_level=self._on_gemini_live_level,
                        on_turn=self._on_gemini_live_turn,
                        # ZARA-VOICE-FLUIDEZ-001: politica CONVERSA/ACAO.
                        can_answer_directly=self._voice_can_answer_directly,
                        on_interrupt=self._on_gemini_live_interrupt,
                        on_error=self._on_gemini_live_error,
                        on_output_audio=self._on_gemini_live_output_audio,
                    )
                status = await self.gemini_live_voice.start(timeout=12.0)
                self.voice_active = True
                self.voice_mode = 'gemini_live'
                print("[IPC] Gemini Live voice started (Kore, wake-gate)")
                await self._ligar_vigia_das_respostas()
                await self.send_response(msg.request_id, {
                    'success': True,
                    'state': status.get('session_state', 'LISTENING'),
                    'wake_mode': bool(status.get('wake_detector_ready')),
                    **status
                })
                return
            except Exception as exc:
                self.voice_active = False
                self.voice_mode = 'off'
                print(f"[IPC] Gemini Live start error: {exc}")
                traceback.print_exc()
                # Fall through to local Vosk. A Gemini Live failure must not
                # turn the microphone button into a dead end.

        # Backward-compatible local path for machines without a Gemini key.
        if not VOICE_AVAILABLE or not self.voice_pipeline:
            await self.send_error(msg, "Gemini API key missing and local voice pipeline unavailable")
            return

        try:
            if not self.voice_pipeline.vosk or not self.voice_pipeline.audio:
                await asyncio.to_thread(self.voice_pipeline.initialize)
            self.voice_pipeline._event_loop = asyncio.get_running_loop()
            await asyncio.to_thread(self.voice_pipeline.start)
            self.voice_active = True
            self.voice_mode = 'local'
            self._voice_last_error = None
            print("[IPC] Local voice pipeline started")
            await self.send_response(msg.request_id, {
                'success': True, 'state': 'LISTENING', 'mode': 'local',
                'voice': 'Kokoro/Vosk fallback'
            })
            await self.send_event('state-change', 'LISTENING')
        except Exception as e:
            self._voice_last_error = str(e).split(':', 1)[0][:120]
            print(f"[IPC] Voice start error: {e}")
            traceback.print_exc()
            await self.send_error(msg, str(e))'''

content = content.replace(old2, new2)

# 3. Update handle_voice_stop to stop Pipecat pipeline
old3 = b'''    async def handle_voice_stop(self, msg: IPCMessage):
        """Stop whichever voice transport is currently active."""
        vigia = getattr(self, "_vigia", None)
        if vigia is not None:
            await vigia.parar()
            self._vigia = None
        if self.gemini_live_voice and self.gemini_live_voice.active:
            await self.gemini_live_voice.stop()
        if self.voice_pipeline:
            await asyncio.to_thread(self.voice_pipeline.stop)
        self.voice_active = False
        self.voice_mode = 'off'
        self._voice_speaking = False
        self._finish_assistant_output()
        print("[IPC] Voice stopped")
        await self.send_response(msg.request_id, {'success': True, 'state': 'STANDBY'})
        await self.send_event('state-change', 'STANDBY')
        await self.send_event('voice-level', {
            'level': 0.0,
            'tone': 0.5,
            'speaking': False,
            'state': 'STANDBY'
        })'''

new3 = b'''    async def handle_voice_stop(self, msg: IPCMessage):
        """Stop whichever voice transport is currently active."""
        vigia = getattr(self, "_vigia", None)
        if vigia is not None:
            await vigia.parar()
            self._vigia = None
        if self.gemini_live_voice and self.gemini_live_voice.active:
            await self.gemini_live_voice.stop()
        if self.voice_pipeline:
            await asyncio.to_thread(self.voice_pipeline.stop)
        if hasattr(self, 'pipecat_pipeline') and self.pipecat_pipeline:
            self.pipecat_pipeline.stop()
            if hasattr(self, '_pipecat_task') and self._pipecat_task:
                self._pipecat_task.cancel()
                try:
                    await self._pipecat_task
                except asyncio.CancelledError:
                    pass
        self.voice_active = False
        self.voice_mode = 'off'
        self._voice_speaking = False
        self._finish_assistant_output()
        print("[IPC] Voice stopped")
        await self.send_response(msg.request_id, {'success': True, 'state': 'STANDBY'})
        await self.send_event('state-change', 'STANDBY')
        await self.send_event('voice-level', {
            'level': 0.0,
            'tone': 0.5,
            'speaking': False,
            'state': 'STANDBY'
        })'''

content = content.replace(old3, new3)

with open('C:/Users/alexp/Downloads/ZARA 3.0 CLEAN 002/core/ipc_handlers.py', 'wb') as f:
    f.write(content)

print("Applied all changes!")

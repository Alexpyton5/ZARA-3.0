return GeminiLiveVoiceConfig(
                    api_key=gemini_key,
                    voice_name="Kore",
                    wake_word_enabled=gate_local,
                    audio_transport=transporte,
                    vad_silencio_ms=silencio_ms,
                )

        async def _start_pipecat_pipeline(self, msg: IPCMessage) -> bool:
                """Start the Pipecat STT→LLM→TTS pipeline with Ollama qwen3:4b and Kokoro."""
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

                    print("[IPC] Pipecat voice pipeline started (Deepgram → Ollama qwen3:4b → Kokoro)")
                    await self.send_response(msg.request_id, {
                        'success': True, 'state': 'LISTENING', 'mode': 'pipecat',
                        'voice': 'Pipecat STT→LLM→TTS'
                    })
                    await self.send_event('state-change', 'LISTENING')
                    return True

                except Exception as e:
                    print(f"[IPC] Pipecat pipeline start error: {e}")
                    traceback.print_exc()
                    await self.send_error(msg, str(e))
                    return False

        async def _on_gemini_live_output_audio(self, audio: bytes) -> None:
        """Entrega a fala da Kore ao Electron para tocar. ZARA-AEC-RENDERER-001.

        Bytes vazios significam "corta agora" (barge-in), nao "silencio".
        """
        if not audio:
            await self.send_event('voice-output-audio', {'stop': True})
            return
        await self.send_event('voice-output-audio', {
            'pcm': base64.b64encode(audio).decode('ascii'),
            'sampleRate': 24000,
        })
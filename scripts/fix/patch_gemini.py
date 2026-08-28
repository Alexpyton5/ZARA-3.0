# Read the file
with open('core/gemini_live_voice.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add _mic_permanent_failure after _audio_frames_received
old1 = """self._audio_frames_received = 0
        # --- Wake-gate state (ZARA-VOICE-WAKE-GATE-001) ---"""

new1 = """self._audio_frames_received = 0
        # Microphone permanent failure flag (permission denied, device missing)
        # If set, _run will not retry opening the microphone
        self._mic_permanent_failure = False
        # --- Wake-gate state (ZARA-VOICE-WAKE-GATE-001) ---"""

content = content.replace(old1, new1)

# 2. Fix start() to reset the flag and check for permanent failure
old2 = """    async def start(self, timeout: float = 20.0) -> dict[str, Any]:
        if self.active:
            return self.status()
        if not self.config.api_key:
            raise RuntimeError("GEMINI_API_KEY não configurada")

        self._loop = asyncio.get_running_loop()
        self._audio_queue = asyncio.Queue(maxsize=64)
        self._speech_queue = asyncio.Queue(maxsize=8)
        self._speech_done = asyncio.Event()
        self._stop = asyncio.Event()
        self._ready = asyncio.Event()
        self._ready_error = None
        self._stream_generation += 1
        generation = self._stream_generation
        self._audio_frames_received = 0
        self._task = asyncio.create_task(self._run(generation), name="zara-gemini-live")

        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout)
        except TimeoutError as exc:
            self._stream_generation += 1
            self._stop.set()
            task = self._task
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            self._task = None
            self._connected = False
            print("[VOICE_TRACE] stage=MIC_OPEN_RESULT result=TIMEOUT", flush=True)
            raise RuntimeError("VOICE_START_TIMEOUT") from exc
        if self._ready_error:
            await self.stop()
            raise RuntimeError(str(self._ready_error)) from self._ready_error
        return self.status()"""

new2 = """    async def start(self, timeout: float = 20.0) -> dict[str, Any]:
        if self.active:
            return self.status()
        if not self.config.api_key:
            raise RuntimeError("GEMINI_API_KEY não configurada")

        self._loop = asyncio.get_running_loop()
        self._audio_queue = asyncio.Queue(maxsize=64)
        self._speech_queue = asyncio.Queue(maxsize=8)
        self._speech_done = asyncio.Event()
        self._stop = asyncio.Event()
        self._ready = asyncio.Event()
        self._ready_error = None
        self._stream_generation += 1
        generation = self._stream_generation
        self._audio_frames_received = 0
        # Reset microphone permanent failure flag on new start attempt
        self._mic_permanent_failure = False
        self._task = asyncio.create_task(self._run(generation), name="zara-gemini-live")

        try:
            await asyncio.wait_for(self._ready.wait(), timeout=timeout)
        except TimeoutError as exc:
            self._stream_generation += 1
            self._stop.set()
            task = self._task
            if task and not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            self._task = None
            self._connected = False
            print("[VOICE_TRACE] stage=MIC_OPEN_RESULT result=TIMEOUT", flush=True)
            raise RuntimeError("VOICE_START_TIMEOUT") from exc
        if self._ready_error:
            await self.stop()
            raise RuntimeError(str(self._ready_error)) from self._ready_error
        # Check for permanent microphone failure after start
        if self._mic_permanent_failure:
            await self.stop()
            raise RuntimeError("VOICE_MIC_PERMANENT_FAILURE: Microfone ausente ou acesso negado")
        return self.status()"""

content = content.replace(old2, new2)

# 3. Fix _open_streams to handle PortAudioError gracefully
old3 = """        devices = sd.query_devices()
        default_devices = getattr(getattr(sd, "default", None), "device", (None, None))
        print(
            "[VOICE_TRACE] stage=SELECTED_INPUT_DEVICE "
            f"configured={self.config.input_device is not None} "
            f"default_index={default_devices[0] if default_devices else None} "
            f"device_count={len(devices)}",
            flush=True,
        )
        input_stream = None
        output_stream = None
        try:
            input_stream = sd.RawInputStream(
                samplerate=self.config.input_sample_rate,
                blocksize=blocksize,
                channels=1,
                dtype="int16",
                device=self.config.input_device,
                callback=mic_callback,
            )
            input_stream.start()
            if generation != self._stream_generation or self._stop.is_set():
                self._close_stream_pair(input_stream, output_stream)
                return False
            self._input_stream = input_stream
            self._output_stream = output_stream
            return True
        except Exception:
            self._close_stream_pair(input_stream, output_stream)
            raise"""

new3 = """        devices = sd.query_devices()
        default_devices = getattr(getattr(sd, "default", None), "device", (None, None))
        print(
            "[VOICE_TRACE] stage=SELECTED_INPUT_DEVICE "
            f"configured={self.config.input_device is not None} "
            f"default_index={default_devices[0] if default_devices else None} "
            f"device_count={len(devices)}",
            flush=True,
        )
        input_stream = None
        output_stream = None
        try:
            input_stream = sd.RawInputStream(
                samplerate=self.config.input_sample_rate,
                blocksize=blocksize,
                channels=1,
                dtype="int16",
                device=self.config.input_device,
                callback=mic_callback,
            )
            input_stream.start()
            if generation != self._stream_generation or self._stop.is_set():
                self._close_stream_pair(input_stream, output_stream)
                return False
            self._input_stream = input_stream
            self._output_stream = output_stream
            print("[VOICE_TRACE] stage=MIC_OPEN_RESULT result=PASS", flush=True)
            return True
        except sd.PortAudioError as exc:
            # Microphone missing, access denied, or device unavailable.
            # Log with error code for diagnostics, but don't crash ZARA.
            error_code = exc.args[1] if len(exc.args) > 1 else "unknown"
            # Error codes that indicate permanent failure (no retry):
            # -9985: paDeviceUnavailable
            # -9986: paInsufficientMemory (could be temporary)
            # -9990: paBadIODeviceCombination
            # -9999: paInvalidDevice
            # Also check error message for permission denied
            is_permanent = False
            if isinstance(error_code, int):
                is_permanent = error_code in (-9985, -9990, -9999)
            if not is_permanent:
                # Check message for permission denied or access denied
                msg_lower = str(exc).lower()
                is_permanent = any(keyword in msg_lower for keyword in [
                    "permission denied", "access denied", "unauthorized",
                    "device not found", "no such device", "input device not found"
                ])
            
            print(
                f"[VOICE_TRACE] stage=MIC_OPEN_RESULT result=FAIL "
                f"error={type(exc).__name__} code={error_code} msg={exc} "
                f"permanent={is_permanent}",
                flush=True,
            )
            # Store permanent failure flag for start() to use
            self._mic_permanent_failure = is_permanent
            return False
        except Exception as exc:
            # Any other unexpected error - log and fail gracefully.
            print(
                f"[VOICE_TRACE] stage=MIC_OPEN_RESULT result=FAIL "
                f"error={type(exc).__name__} msg={exc}",
                flush=True,
            )
            return False"""

content = content.replace(old3, new3)

# 4. Fix _run to set _ready_error when microphone fails permanently
old4 = """            print("[VOICE_TRACE] stage=LIVE_IMPORT result=PASS", flush=True)

            print("[VOICE_TRACE] stage=MIC_DEVICE_ENUMERATION result=START", flush=True)
            opened = await asyncio.to_thread(self._open_streams, sd, generation)
            if not opened:
                return
            print("[VOICE_TRACE] stage=MIC_OPEN_RESULT result=PASS", flush=True)"""

new4 = """            print("[VOICE_TRACE] stage=LIVE_IMPORT result=PASS", flush=True)

            print("[VOICE_TRACE] stage=MIC_DEVICE_ENUMERATION result=START", flush=True)
            opened = await asyncio.to_thread(self._open_streams, sd, generation)
            if not opened:
                # Microphone failed to open - check if it's a permanent failure
                if self._mic_permanent_failure:
                    self._ready_error = RuntimeError("VOICE_MIC_PERMANENT_FAILURE: Microfone ausente ou acesso negado")
                else:
                    self._ready_error = RuntimeError("VOICE_AUDIO_OPEN_FAILED: Failed to open microphone")
                self._ready.set()
                return
            print("[VOICE_TRACE] stage=MIC_OPEN_RESULT result=PASS", flush=True)"""

content = content.replace(old4, new4)

# Write back
with open('core/gemini_live_voice.py', 'w', encoding='utf-8') as f:
    f.write(content)

print("Done patching gemini_live_voice.py")
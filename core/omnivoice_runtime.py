"""Isolated client for the optional per-user OmniVoice worker runtime."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import uuid
from pathlib import Path


class OmniVoiceWorkerTTS:
    READY_MARKER = Path("models") / "omnivoice" / "ready.json"
    TIMEOUT_SECONDS = 180

    def __init__(self, runtime_root: Path | None = None, data_root: Path | None = None,
                 worker_path: Path | None = None):
        local = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local")
        root = Path(os.environ.get("ZARA3_HOME") or local / "ZARA3")
        self.runtime_root = Path(runtime_root) if runtime_root else root / "runtimes" / "omnivoice"
        self.data_root = Path(data_root) if data_root else root
        if worker_path:
            self.worker_path = Path(worker_path)
        elif getattr(sys, "frozen", False):
            self.worker_path = Path(getattr(sys, "_MEIPASS", "")) / "core" / "omnivoice_worker.py"
        else:
            self.worker_path = Path(__file__).with_name("omnivoice_worker.py")
        self._process: subprocess.Popen[str] | None = None
        self._responses: queue.Queue[str | None] = queue.Queue()
        self._lock = threading.RLock()

    @property
    def available(self) -> bool:
        python = self.runtime_root / "venv" / "Scripts" / "python.exe"
        marker = self.data_root / self.READY_MARKER
        try:
            state = json.loads(marker.read_text(encoding="utf-8"))
            return bool(python.is_file() and self.worker_path.is_file()
                        and state.get("ready") is True
                        and state.get("model") == "k2-fsa/OmniVoice")
        except (OSError, ValueError, TypeError):
            return False

    @staticmethod
    def _worker_environment(source: dict[str, str], data_root: Path) -> dict[str, str]:
        allowed = {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "USERPROFILE",
                   "APPDATA", "LOCALAPPDATA"}
        result = {key: value for key, value in source.items() if key in allowed}
        result.update({"PYTHONIOENCODING": "utf-8", "HF_HOME": str(data_root / "models" / "omnivoice" / "hub"),
                       "HF_HUB_DISABLE_TELEMETRY": "1", "TOKENIZERS_PARALLELISM": "false"})
        return result

    def _start(self) -> subprocess.Popen[str]:
        if not self.available:
            raise RuntimeError("Runtime local OmniVoice não instalado")
        if self._process is None or self._process.poll() is not None:
            self._responses = queue.Queue()
            python = self.runtime_root / "venv" / "Scripts" / "python.exe"
            self._process = subprocess.Popen(
                [str(python), str(self.worker_path)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                encoding="utf-8", bufsize=1,
                env=self._worker_environment(dict(os.environ), self.data_root),
            )
            threading.Thread(target=self._read_responses, args=(self._process,), daemon=True).start()
        return self._process

    def _read_responses(self, process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            self._responses.put(line)
        self._responses.put(None)

    def play(self, text: str, voice: str | None = None, speed: float = 1.0,
             blocking: bool = True) -> None:
        if not blocking:
            thread = threading.Thread(target=self.play, args=(text, voice, speed, True), daemon=True)
            thread.start()
            return
        request_id = uuid.uuid4().hex
        output = Path(tempfile.gettempdir()) / f"zara-omnivoice-{request_id}.wav"
        try:
            with self._lock:
                process = self._start()
                assert process.stdin is not None
                process.stdin.write(json.dumps({"id": request_id, "text": str(text),
                                                "speed": float(speed), "output": str(output)}) + "\n")
                process.stdin.flush()
                line = self._responses.get(timeout=self.TIMEOUT_SECONDS)
                if line is None:
                    self._stop_worker()
                    raise RuntimeError("Worker OmniVoice encerrou inesperadamente")
                response = json.loads(line)
                if response.get("id") != request_id or response.get("ok") is not True:
                    self._stop_worker()
                    raise RuntimeError("Falha de síntese no worker OmniVoice")
            import sounddevice as sd
            import soundfile as sf

            audio, sample_rate = sf.read(str(output), dtype="float32")
            sd.play(audio, sample_rate)
            sd.wait()
        except queue.Empty as exc:
            with self._lock:
                self._stop_worker()
            raise TimeoutError("Worker OmniVoice excedeu o limite de resposta") from exc
        finally:
            output.unlink(missing_ok=True)

    def _stop_worker(self) -> None:
        process, self._process = self._process, None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)

    def stop(self) -> None:
        try:
            import sounddevice as sd
            sd.stop()
        except Exception:
            pass
        with self._lock:
            self._stop_worker()

    def cleanup(self) -> None:
        self.stop()

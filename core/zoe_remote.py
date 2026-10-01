"""Authenticated Zoe/SSH bridge payloads, with persistent at-most-once dispatch.

Zoe receives WhatsApp messages in Muse. This adapter is the Windows execution
end; it does not claim to be a WhatsApp account or create an Internet listener.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
import wave
from pathlib import Path


def audio_file(spool: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError("Caminho de áudio inválido.")
    path = (spool / relative).resolve()
    path.relative_to(spool.resolve())
    if path.suffix.lower() not in {".wav", ".ogg", ".opus", ".m4a", ".mp3"}:
        raise ValueError("Formato de áudio não suportado.")
    if not path.is_file() or not 0 < path.stat().st_size <= 8 * 1024 * 1024:
        raise ValueError("Áudio ausente ou maior que 8 MB.")
    return path


def transcribe_audio(path: Path) -> str:
    from core.voice_stt import VoiceConfig, VoskSTT
    # Convert WhatsApp codecs with the installed local ffmpeg. Never download
    # weights or fall back to a paid provider behind the user's back.
    with tempfile.TemporaryDirectory(prefix="tropa-audio-") as temporary:
        wav = path
        if path.suffix.lower() != ".wav":
            binary = shutil.which("ffmpeg")
            probe = shutil.which("ffprobe")
            if not binary or not probe:
                raise ValueError("FFmpeg não disponível para converter áudio do WhatsApp.")
            metadata = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration",
                                       "-of", "json", str(path)], check=True, timeout=10,
                                      capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            duration = float(json.loads(metadata.stdout).get("format", {}).get("duration", 0))
            if not 0 < duration <= 120:
                raise ValueError("Áudio deve durar até 120 segundos; não executei uma ordem cortada.")
            wav = Path(temporary) / "input.wav"
            subprocess.run([binary, "-nostdin", "-loglevel", "error", "-i", str(path),
                            "-t", "120", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(wav)],
                           check=True, timeout=25, capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        with wave.open(str(wav), "rb") as stream:
            if (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) != (1, 2, 16000):
                raise ValueError("Use áudio PCM mono 16 kHz, 16 bits.")
            if not 0 < stream.getnframes() / 16000 <= 120:
                raise ValueError("Áudio deve durar até 120 segundos.")
            pcm = stream.readframes(stream.getnframes())
        stt = VoskSTT(VoiceConfig())
        stt.recognizer.AcceptWaveform(pcm)
        return str(json.loads(stt.recognizer.FinalResult()).get("text", "")).strip()


class ZoeRemote:
    def __init__(self, directory: Path, executor, transcriber=transcribe_audio):
        self.directory = directory
        self.spool = directory / "inbox"
        self.spool.mkdir(parents=True, exist_ok=True)
        self.db = directory / "remote_receipts.sqlite3"
        self.executor = executor
        self.transcriber = transcriber
        self.lock = asyncio.Lock()
        with self._connect() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS receipts (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, result TEXT)")

    def _connect(self):
        return sqlite3.connect(self.db, timeout=10)

    def _transcribe_snapshot(self, content: bytes, suffix: str) -> str:
        with tempfile.TemporaryDirectory(prefix='tropa-received-') as temporary:
            frozen = Path(temporary) / ('received' + suffix)
            frozen.write_bytes(content)
            return self.transcriber(frozen)

    async def receive(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            return {"success": False, "error": "Pedido remoto inválido."}
        message_id = payload.get("message_id")
        channel = payload.get("channel", "whatsapp")
        text = payload.get("text")
        audio = payload.get("audio_path")
        if (not isinstance(message_id, str) or not re.fullmatch(r"[\w:.-]{1,160}", message_id)
                or not isinstance(channel, str) or channel not in {"whatsapp", "muse"}
                or bool(text) == bool(audio)
                or (text and (not isinstance(text, str) or not text.strip() or len(text) > 4000))):
            return {"success": False, "error": "Pedido remoto inválido."}
        try:
            path = audio_file(self.spool, audio) if audio else None
            content = path.read_bytes() if path else None
            if content is not None and not 0 < len(content) <= 8 * 1024 * 1024:
                raise ValueError('Áudio fora do limite.')
        except (ValueError, OSError):
            return {"success": False, "error": "Áudio fora da caixa de entrada ou inválido."}
        fingerprint = hashlib.sha256(json.dumps({"channel": channel, "text": text,
                                                "audio": hashlib.sha256(content).hexdigest() if content is not None else None},
                                               sort_keys=True).encode()).hexdigest()
        async with self.lock:
            # Persist before performing any action. A crash leaves 'pending',
            # never permission to rerun an uncertain side effect on restart.
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute("SELECT fingerprint,result FROM receipts WHERE id=?", (message_id,)).fetchone()
                if existing:
                    if existing[0] != fingerprint:
                        return {"success": False, "error": "Identificador já usado por outro pedido."}
                    return {**(json.loads(existing[1]) if existing[1] else
                               {"success": False, "error": "Execução anterior não confirmada; confira o PC antes de reenviar."}), "replayed": True}
                conn.execute("INSERT INTO receipts VALUES (?,?,NULL)", (message_id, fingerprint))
            try:
                if path:
                    text = await asyncio.to_thread(self._transcribe_snapshot, content, path.suffix)
                if not isinstance(text, str) or not text.strip() or len(text) > 4000:
                    result = {"success": False, "error": "Nenhuma fala válida reconhecida; não executei a ordem."}
                else:
                    result = await self.executor(text.strip(), channel)
                    result = {**result, "transcript": text.strip() if path else None}
            except Exception as exc:
                result = {"success": False, "error": f"Pedido não concluído ({type(exc).__name__}); resultado não confirmado."}
            with self._connect() as conn:
                conn.execute("UPDATE receipts SET result=? WHERE id=?", (json.dumps(result, ensure_ascii=False), message_id))
            return result

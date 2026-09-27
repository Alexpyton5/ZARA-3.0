"""Persistent JSON-lines worker for local OmniVoice inference."""

from __future__ import annotations

import contextlib
import json
import os
import sys
import wave
from pathlib import Path
from typing import Any


def _load_model() -> tuple[Any, str]:
    import torch
    from omnivoice import OmniVoice

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device.startswith("cuda") else torch.float32
    model = OmniVoice.from_pretrained(
        "k2-fsa/OmniVoice", device_map=device, dtype=dtype
    )
    model.eval()
    return model, device


def _write_wave(path: Path, audio: Any) -> None:
    import numpy as np

    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    if not samples.size:
        raise ValueError("OmniVoice output was empty")
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(pcm.tobytes())


def main() -> int:
    model = None
    for line in sys.stdin:
        request_id = ""
        try:
            request = json.loads(line)
            request_id = str(request.get("id") or "")
            text = str(request.get("text") or "").strip()
            output_path = Path(str(request.get("output") or ""))
            if not request_id or not text or not output_path.is_absolute():
                raise ValueError("Invalid request")
            with contextlib.redirect_stdout(sys.stderr), contextlib.redirect_stderr(sys.stderr):
                if model is None:
                    model, _device = _load_model()
                audio = model.generate(
                    text=text,
                    language_id="pt",
                    speed=float(request.get("speed") or 1.0),
                    num_step=16,
                )
            waveform = audio[0] if isinstance(audio, (list, tuple)) else audio
            _write_wave(output_path, waveform)
            response = {"id": request_id, "ok": True}
        except Exception as exc:
            # Exception text can contain local paths or model details; keep the
            # protocol response generic and leave only the type for diagnosis.
            response = {
                "id": request_id,
                "ok": False,
                "error_type": type(exc).__name__,
            }
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

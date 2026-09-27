"""Credential-free, per-user preferences for speech output selection."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from core.paths import user_data_dir
from core.voice_engine_policy import normalize_voice_engine


def voice_preferences_path() -> Path:
    return user_data_dir() / "config" / "voice_preferences.json"


def load_voice_output_engine(path: Path | None = None) -> str:
    target = Path(path) if path else voice_preferences_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return normalize_voice_engine(data.get("output_engine"))
    except (OSError, ValueError, TypeError):
        return "kore"


def save_voice_output_engine(engine: object, path: Path | None = None) -> str:
    selected = normalize_voice_engine(engine)
    target = Path(path) if path else voice_preferences_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix="voice-preferences-", suffix=".tmp", dir=target.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"output_engine": selected}, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return selected

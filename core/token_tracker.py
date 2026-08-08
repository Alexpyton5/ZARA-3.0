"""TokenTracker — tracks daily token usage per model."""
from __future__ import annotations

import json
import threading
from datetime import date, datetime
from typing import Any

from core.storage import atomic_write_json, safe_user_path


class TokenTracker:
    """Thread-safe daily token usage tracker."""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._data_file = safe_user_path("token_usage.json")
        self._data: dict[str, Any] = {"daily": {}, "total": {}}
        self._load()

    def _load(self):
        try:
            if self._data_file.exists():
                with open(self._data_file, encoding="utf-8") as f:
                    self._data = json.load(f)
        except Exception:
            self._data = {"daily": {}, "total": {}}

    def _save(self):
        atomic_write_json(self._data_file, self._data)

    def _today_key(self) -> str:
        return date.today().isoformat()

    def record_usage(self, model: str, prompt_tokens: int = 0, completion_tokens: int = 0):
        """Record token usage for a model."""
        today = self._today_key()
        total = prompt_tokens + completion_tokens

        # Daily
        if today not in self._data["daily"]:
            self._data["daily"][today] = {}
        if model not in self._data["daily"][today]:
            self._data["daily"][today][model] = {"prompt": 0, "completion": 0, "total": 0}

        self._data["daily"][today][model]["prompt"] += prompt_tokens
        self._data["daily"][today][model]["completion"] += completion_tokens
        self._data["daily"][today][model]["total"] += total

        # Total
        if model not in self._data["total"]:
            self._data["total"][model] = {"prompt": 0, "completion": 0, "total": 0, "last_used": None}

        self._data["total"][model]["prompt"] += prompt_tokens
        self._data["total"][model]["completion"] += completion_tokens
        self._data["total"][model]["total"] += total
        self._data["total"][model]["last_used"] = datetime.now().isoformat()

        self._save()

    def get_daily_usage(self, day: str | None = None) -> dict[str, Any]:
        day = day or self._today_key()
        return self._data["daily"].get(day, {})

    def get_total_usage(self) -> dict[str, Any]:
        return self._data.get("total", {})

    def get_model_usage(self, model: str, day: str | None = None) -> dict[str, int]:
        day = day or self._today_key()
        return self._data["daily"].get(day, {}).get(model, {"prompt": 0, "completion": 0, "total": 0})


# Global instance
tracker = TokenTracker()

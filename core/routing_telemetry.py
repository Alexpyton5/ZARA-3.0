"""Routing Telemetry — review-only logging for model routing decisions.

Contract (see docs/technical/routing_telemetry.md):
- record() stores one routing outcome (task type, executor, model, duration,
  success, fallback usage) and persists it to disk immediately.
- Persistence is atomic (write to a .tmp file, then replace) so a crash never
  leaves a truncated/corrupt telemetry.json on disk.
- A corrupt telemetry.json on disk must never prevent ZARA from starting:
  it is treated as "no history yet" and the failure is exposed via
  last_persistence_error, not raised.
- get_aggregates() rolls up success/fallback rate and average duration per
  task_type, per executor and per model, independently.
- routing_candidates() looks at concrete routes (task_type, executor, model)
  and flags ones with enough samples, a low success rate and a high fallback
  rate as ROUTING_CANDIDATE. These are review_required / auto_apply=False by
  construction: this module has no method that could apply a candidate to
  the router, by design (safety first).
- History is capped at MAX_EVENTS (rolling window); oldest events are
  dropped first.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any


class RoutingTelemetry:
    """Thread-safe, file-backed, review-only telemetry for routing decisions."""

    MAX_EVENTS = 1000

    # A route is flagged as a candidate for human review when it has at
    # least this many samples and looks weak on both axes below.
    DEFAULT_MINIMUM_SAMPLES = 5
    DEFAULT_MAX_SUCCESS_RATE = 0.6
    DEFAULT_MIN_FALLBACK_RATE = 0.4

    def __init__(self, data_dir: Path | None = None):
        if data_dir is None:
            from core.paths import data_dir as default_data_dir

            data_dir = default_data_dir()
        self.data_dir = Path(data_dir)
        self.telemetry_dir = self.data_dir / "routing"
        self.telemetry_dir.mkdir(parents=True, exist_ok=True)
        self.telemetry_file = self.telemetry_dir / "telemetry.json"

        self._lock = threading.RLock()
        self.last_persistence_error: str | None = None
        self._events: list[dict[str, Any]] = self._load()

    # ------------------------------------------------------------------
    # Loading / persistence
    # ------------------------------------------------------------------

    def _load(self) -> list[dict[str, Any]]:
        if not self.telemetry_file.exists():
            return []
        try:
            raw = self.telemetry_file.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, list):
                raise ValueError("telemetry.json did not contain a list")
            return data
        except Exception as exc:  # noqa: BLE001 - corruption must never crash startup
            self.last_persistence_error = f"{type(exc).__name__}: {exc}"
            return []

    def _persist_locked(self) -> bool:
        """Atomically write self._events to disk. Caller must hold self._lock."""
        tmp_file = Path(str(self.telemetry_file) + ".tmp")
        try:
            tmp_file.write_text(
                json.dumps(self._events, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp_file.replace(self.telemetry_file)
            self.last_persistence_error = None
            return True
        except Exception as exc:  # noqa: BLE001 - persistence failure is observable, not fatal
            self.last_persistence_error = f"{type(exc).__name__}: {exc}"
            try:
                if tmp_file.exists():
                    tmp_file.unlink()
            except Exception:
                pass
            return False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record(
        self,
        task_type: Any,
        executor: str,
        duration: float,
        success: bool,
        *,
        model: str | None = None,
        fallback: bool = False,
        error: str | None = None,
    ) -> bool:
        """Store one routing result. Returns True if it was persisted to disk."""
        task_type_value = str(task_type) if task_type is not None else ""
        if not task_type_value:
            raise ValueError("task_type is required")

        executor_value = str(executor) if executor is not None else ""
        if not executor_value:
            raise ValueError("executor is required")

        try:
            duration_value = float(duration)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid duration: {duration!r}") from exc
        if duration_value < 0:
            raise ValueError("duration must be >= 0")

        event = {
            "timestamp": time.time(),
            "task_type": task_type_value,
            "executor": executor_value,
            "model": str(model) if model is not None else None,
            "duration": duration_value,
            "success": bool(success),
            "fallback": bool(fallback),
            # Truncated defensively: telemetry is not a place to dump full
            # stack traces or arbitrary user content.
            "error": str(error)[:500] if error else None,
        }

        with self._lock:
            self._events.append(event)
            if len(self._events) > self.MAX_EVENTS:
                self._events = self._events[-self.MAX_EVENTS :]
            return self._persist_locked()

    def get_events(
        self, limit: int = 100, task_type: Any | None = None
    ) -> list[dict[str, Any]]:
        """Most-recent-first list of events, optionally filtered by task type."""
        if limit < 0:
            raise ValueError("limit must be >= 0")

        with self._lock:
            events = list(self._events)

        if task_type is not None:
            task_type_value = str(task_type)
            events = [e for e in events if e["task_type"] == task_type_value]

        events.reverse()
        return events[:limit]

    def get_aggregates(self) -> dict[str, Any]:
        """Aggregate success/fallback rate and avg duration per task/executor/model."""
        with self._lock:
            events = list(self._events)

        axis_keys = {
            "task_type": lambda e: e["task_type"],
            "executor": lambda e: e["executor"],
            "model": lambda e: e.get("model"),
        }

        groups: dict[str, dict[Any, dict[str, Any]]] = {}
        for axis, keyfn in axis_keys.items():
            buckets: dict[Any, list[dict[str, Any]]] = {}
            for event in events:
                key = keyfn(event)
                if key is None:
                    continue
                buckets.setdefault(key, []).append(event)

            axis_groups: dict[Any, dict[str, Any]] = {}
            for key, bucket_events in buckets.items():
                count = len(bucket_events)
                successes = sum(1 for e in bucket_events if e["success"])
                fallbacks = sum(1 for e in bucket_events if e.get("fallback"))
                total_duration = sum(e["duration"] for e in bucket_events)
                axis_groups[key] = {
                    "count": count,
                    "success_rate": successes / count,
                    "fallback_rate": fallbacks / count,
                    "avg_duration": total_duration / count,
                }
            groups[axis] = axis_groups

        return {"groups": groups}

    def routing_candidates(
        self,
        minimum_samples: int = DEFAULT_MINIMUM_SAMPLES,
        max_success_rate: float = DEFAULT_MAX_SUCCESS_RATE,
        min_fallback_rate: float = DEFAULT_MIN_FALLBACK_RATE,
    ) -> list[dict[str, Any]]:
        """Review-only suggestions for weak routes. Never applies anything itself.

        A "route" is a concrete (task_type, executor, model) combination —
        candidates are evaluated per route, not per aggregation axis, so one
        weak route produces exactly one suggestion instead of one per axis.
        """
        with self._lock:
            events = list(self._events)

        routes: dict[tuple[str, str, str | None], list[dict[str, Any]]] = {}
        for event in events:
            key = (event["task_type"], event["executor"], event.get("model"))
            routes.setdefault(key, []).append(event)

        candidates: list[dict[str, Any]] = []
        for (task_type, executor, model), route_events in routes.items():
            count = len(route_events)
            if count < minimum_samples:
                continue

            successes = sum(1 for e in route_events if e["success"])
            fallbacks = sum(1 for e in route_events if e.get("fallback"))
            success_rate = successes / count
            fallback_rate = fallbacks / count

            if success_rate <= max_success_rate and fallback_rate >= min_fallback_rate:
                candidates.append(
                    {
                        "kind": "ROUTING_CANDIDATE",
                        "task_type": task_type,
                        "executor": executor,
                        "model": model,
                        "count": count,
                        "success_rate": success_rate,
                        "fallback_rate": fallback_rate,
                        "review_required": True,
                        "auto_apply": False,
                    }
                )

        return candidates

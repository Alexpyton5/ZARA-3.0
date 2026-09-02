"""Local watchdogs for battery, disk, CPU and completed downloads."""
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import psutil


@dataclass(frozen=True)
class MonitorEvent:
    kind: str
    severity: str
    message: str
    data: dict[str, Any]
    observed_at: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProactiveMonitor:
    def __init__(
        self,
        *,
        downloads_dir: str | Path | None = None,
        battery_low_percent: float = 20.0,
        disk_low_percent: float = 10.0,
        cpu_high_percent: float = 90.0,
        cpu_consecutive_samples: int = 3,
        cooldown_seconds: float = 300.0,
        callback: Callable[[MonitorEvent], None] | None = None,
    ):
        self.downloads_dir = Path(downloads_dir).expanduser() if downloads_dir else Path.home() / "Downloads"
        self.battery_low_percent = float(battery_low_percent)
        self.disk_low_percent = float(disk_low_percent)
        self.cpu_high_percent = float(cpu_high_percent)
        self.cpu_consecutive_samples = max(1, int(cpu_consecutive_samples))
        self.cooldown_seconds = max(0.0, float(cooldown_seconds))
        self.callback = callback
        self._last_emitted: dict[str, float] = {}
        self._high_cpu_samples = 0
        self._download_snapshot = self._snapshot_downloads()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _snapshot_downloads(self) -> dict[str, tuple[int, float]]:
        if not self.downloads_dir.is_dir():
            return {}
        snapshot = {}
        try:
            for path in self.downloads_dir.iterdir():
                if path.is_file():
                    stat = path.stat()
                    snapshot[str(path.resolve())] = (stat.st_size, stat.st_mtime)
        except OSError:
            return snapshot
        return snapshot

    def _emit(self, event: MonitorEvent, output: list[MonitorEvent]) -> None:
        key = f"{event.kind}:{event.data.get('path', '')}"
        now = event.observed_at
        if now - self._last_emitted.get(key, 0.0) < self.cooldown_seconds:
            return
        self._last_emitted[key] = now
        output.append(event)
        if self.callback is not None:
            try:
                self.callback(event)
            except Exception:
                pass

    def check_once(self) -> list[MonitorEvent]:
        now = time.time()
        events: list[MonitorEvent] = []
        battery = psutil.sensors_battery()
        if battery is not None and not battery.power_plugged and battery.percent <= self.battery_low_percent:
            self._emit(MonitorEvent("battery_low", "warning", f"Bateria em {battery.percent:.0f}%.",
                                    {"percent": float(battery.percent), "plugged": False}, now), events)

        disk_root = self.downloads_dir.anchor or str(Path.cwd().anchor)
        try:
            disk = psutil.disk_usage(disk_root)
            free_percent = 100.0 - float(disk.percent)
            if free_percent <= self.disk_low_percent:
                self._emit(MonitorEvent("disk_low", "warning", f"Disco com {free_percent:.1f}% livre.",
                                        {"free_percent": free_percent, "free_bytes": int(disk.free), "root": disk_root}, now), events)
        except (OSError, ValueError):
            pass

        cpu = float(psutil.cpu_percent(interval=None))
        self._high_cpu_samples = self._high_cpu_samples + 1 if cpu >= self.cpu_high_percent else 0
        if self._high_cpu_samples >= self.cpu_consecutive_samples:
            self._emit(MonitorEvent("cpu_high", "warning", f"CPU em {cpu:.0f}% por varias leituras.",
                                    {"percent": cpu, "samples": self._high_cpu_samples}, now), events)

        current = self._snapshot_downloads()
        incomplete_suffixes = {".crdownload", ".part", ".tmp"}
        previous_incomplete_stems = {
            str(Path(path).with_suffix("")) for path in self._download_snapshot
            if Path(path).suffix.casefold() in incomplete_suffixes
        }
        for path, details in current.items():
            item = Path(path)
            if path in self._download_snapshot or item.suffix.casefold() in incomplete_suffixes:
                continue
            likely_completed = str(item.with_suffix("")) in previous_incomplete_stems or details[1] >= now - 10.0
            if likely_completed:
                self._emit(MonitorEvent("download_completed", "info", f"Download concluido: {item.name}",
                                        {"path": path, "size_bytes": details[0]}, now), events)
        self._download_snapshot = current
        return events

    def start(self, interval_seconds: float = 15.0) -> bool:
        if self._thread is not None and self._thread.is_alive():
            return False
        interval = max(1.0, float(interval_seconds))
        self._stop.clear()

        def loop() -> None:
            while not self._stop.wait(interval):
                self.check_once()

        self._thread = threading.Thread(target=loop, name="zara-proactive-monitor", daemon=True)
        self._thread.start()
        return True

    def stop(self, timeout: float = 5.0) -> bool:
        self._stop.set()
        thread = self._thread
        if thread is None:
            return True
        thread.join(max(0.0, timeout))
        return not thread.is_alive()

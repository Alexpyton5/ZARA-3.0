"""
Scheduler Action — Routines, cron jobs, and scheduled tasks.
"""
from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from core.action_registry import ActionResult, action, get_registry
from core.paths import user_data_dir
from core.storage import atomic_write_json


@dataclass
class ScheduledTask:
    """A scheduled task."""
    id: str
    name: str
    action: str
    action_params: dict
    schedule: str  # cron expression or "interval:N" or "once:ISO_TIME"
    enabled: bool = True
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    last_run: str | None = None
    next_run: str | None = None
    run_count: int = 0


class TaskScheduler:
    """Background task scheduler."""

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

        self.tasks: dict[str, ScheduledTask] = {}
        self._thread: threading.Thread | None = None
        self._running = False
        self._action_runner: Callable | None = None
        self._load_tasks()

    def set_action_runner(self, runner: Callable[[str, dict], ActionResult]):
        """Set the function to execute actions."""
        self._action_runner = runner

    def _load_tasks(self):
        """Load tasks from disk."""
        tasks_file = user_data_dir() / "scheduled_tasks.json"
        if tasks_file.exists():
            try:
                import json
                data = json.loads(tasks_file.read_text(encoding="utf-8"))
                for task_data in data.get("tasks", []):
                    task = ScheduledTask(**task_data)
                    self.tasks[task.id] = task
                print(f"[Scheduler] Loaded {len(self.tasks)} tasks")
            except Exception as e:
                print(f"[Scheduler] Failed to load tasks: {e}")

    def _save_tasks(self):
        """Save tasks to disk."""
        tasks_file = user_data_dir() / "scheduled_tasks.json"
        try:
            data = {"tasks": [self._task_to_dict(t) for t in self.tasks.values()]}
            atomic_write_json(tasks_file, data)
        except Exception as e:
            print(f"[Scheduler] Failed to save tasks: {e}")

    def _task_to_dict(self, task: ScheduledTask) -> dict:
        return {
            "id": task.id,
            "name": task.name,
            "action": task.action,
            "action_params": task.action_params,
            "schedule": task.schedule,
            "enabled": task.enabled,
            "created": task.created,
            "last_run": task.last_run,
            "next_run": task.next_run,
            "run_count": task.run_count,
        }

    def add_task(
        self,
        name: str,
        action: str,
        action_params: dict,
        schedule: str,
        task_id: str = None,
    ) -> str:
        """Add a scheduled task."""
        import uuid
        task_id = task_id or str(uuid.uuid4())[:8]

        task = ScheduledTask(
            id=task_id,
            name=name,
            action=action,
            action_params=action_params,
            schedule=schedule,
        )
        task.next_run = self._calculate_next_run(task)

        self.tasks[task_id] = task
        self._save_tasks()
        return task_id

    def remove_task(self, task_id: str) -> bool:
        """Remove a task."""
        if task_id in self.tasks:
            del self.tasks[task_id]
            self._save_tasks()
            return True
        return False

    def enable_task(self, task_id: str, enabled: bool = True) -> bool:
        """Enable/disable a task."""
        if task_id in self.tasks:
            self.tasks[task_id].enabled = enabled
            if enabled:
                self.tasks[task_id].next_run = self._calculate_next_run(self.tasks[task_id])
            self._save_tasks()
            return True
        return False

    def _calculate_next_run(self, task: ScheduledTask) -> str | None:
        """Calculate next run time from schedule."""
        now = datetime.now()

        if task.schedule.startswith("interval:"):
            # interval:N (seconds)
            try:
                seconds = int(task.schedule.split(":")[1])
                return (now + timedelta(seconds=seconds)).isoformat()
            except Exception:
                return None

        elif task.schedule.startswith("once:"):
            # once:ISO_TIME
            try:
                run_time = datetime.fromisoformat(task.schedule.split(":", 1)[1])
                if run_time > now:
                    return run_time.isoformat()
            except Exception:
                return None

        else:
            # Cron expression - simplified (would need croniter for full support)
            # For now, just run every minute for testing
            return (now + timedelta(minutes=1)).isoformat()

    def start(self):
        """Start the scheduler thread."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="TaskScheduler")
        self._thread.start()
        print("[Scheduler] Started")

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        print("[Scheduler] Stopped")

    def _run_loop(self):
        """Main scheduler loop."""
        while self._running:
            try:
                now = datetime.now()

                for task in list(self.tasks.values()):
                    if not task.enabled or not task.next_run:
                        continue

                    next_run = datetime.fromisoformat(task.next_run)
                    if now >= next_run:
                        # Execute task
                        self._execute_task(task)

                        # Calculate next run
                        task.last_run = now.isoformat()
                        task.run_count += 1
                        task.next_run = self._calculate_next_run(task)

                        # If one-time task, disable
                        if task.schedule.startswith("once:"):
                            task.enabled = False

                self._save_tasks()

            except Exception as e:
                print(f"[Scheduler] Loop error: {e}")

            time.sleep(10)  # Check every 10 seconds

    def _execute_task(self, task: ScheduledTask):
        """Execute a scheduled task."""
        print(f"[Scheduler] Running task: {task.name} ({task.action})")

        if self._action_runner:
            try:
                result = self._action_runner(task.action, task.action_params)
                print(f"[Scheduler] Task {task.name} result: {result.success}")
            except Exception as e:
                print(f"[Scheduler] Task {task.name} error: {e}")
        else:
            print("[Scheduler] No action runner configured")

    def list_tasks(self) -> list[dict]:
        """List all tasks."""
        return [self._task_to_dict(t) for t in self.tasks.values()]


# Global scheduler instance
scheduler = TaskScheduler()


@action(
    name="schedule_add",
    category="scheduler",
    description="Add a scheduled task",
    risk="MEDIUM",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Task name"},
            "action": {"type": "string", "description": "Action to execute"},
            "params": {"type": "object", "description": "Action parameters", "default": {}},
            "schedule": {"type": "string", "description": "Schedule: 'interval:N' (seconds), 'once:ISO_TIME', or cron expression"},
            "task_id": {"type": "string", "description": "Optional custom task ID"},
        },
        "required": ["name", "action", "schedule"],
    },
    capability="PC_CONTROL",
)
def schedule_add_action(name: str, action: str, schedule: str, params: dict = None, task_id: str = "") -> ActionResult:
    """Add a scheduled task."""
    try:
        params = params or {}
        tid = scheduler.add_task(name, action, params, schedule, task_id or None)
        task = scheduler.tasks[tid]
        return ActionResult(
            success=True,
            output=f"Scheduled task '{name}' (ID: {tid}) - Next run: {task.next_run}",
            data={"task_id": tid, "next_run": task.next_run}
        )
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="schedule_remove",
    category="scheduler",
    description="Remove a scheduled task",
    risk="MEDIUM",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "Task ID to remove"},
        },
        "required": ["task_id"],
    },
    capability="PC_CONTROL",
)
def schedule_remove_action(task_id: str) -> ActionResult:
    """Remove a scheduled task."""
    try:
        if scheduler.remove_task(task_id):
            return ActionResult(success=True, output=f"Removed task {task_id}")
        return ActionResult(success=False, error=f"Task {task_id} not found")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="schedule_list",
    category="scheduler",
    description="List all scheduled tasks",
    parameters={},
)
def schedule_list_action() -> ActionResult:
    """List all scheduled tasks."""
    try:
        tasks = scheduler.list_tasks()
        return ActionResult(
            success=True,
            output=json.dumps(tasks, indent=2),
            data={"tasks": tasks, "count": len(tasks)}
        )
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="schedule_enable",
    category="scheduler",
    description="Enable or disable a scheduled task",
    risk="MEDIUM",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "Task ID"},
            "enabled": {"type": "boolean", "description": "Enable (true) or disable (false)", "default": True},
        },
        "required": ["task_id"],
    },
    capability="PC_CONTROL",
)
def schedule_enable_action(task_id: str, enabled: bool = True) -> ActionResult:
    """Enable/disable a scheduled task."""
    try:
        if scheduler.enable_task(task_id, enabled):
            return ActionResult(success=True, output=f"Task {task_id} {'enabled' if enabled else 'disabled'}")
        return ActionResult(success=False, error=f"Task {task_id} not found")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


@action(
    name="schedule_run_now",
    category="scheduler",
    description="Run a scheduled task immediately",
    risk="MEDIUM",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {"type": "string", "description": "Task ID to run"},
        },
        "required": ["task_id"],
    },
    capability="PC_CONTROL",
)
def schedule_run_now_action(task_id: str) -> ActionResult:
    """Run a scheduled task immediately."""
    try:
        task = scheduler.tasks.get(task_id)
        if not task:
            return ActionResult(success=False, error=f"Task {task_id} not found")

        if scheduler._action_runner:
            result = scheduler._action_runner(task.action, task.action_params)
            task.last_run = datetime.now().isoformat()
            task.run_count += 1
            scheduler._save_tasks()
            return ActionResult(
                success=result.success,
                output=f"Task {task.name} executed: {result.output or result.error}",
                data={"result": str(result)}
            )
        return ActionResult(success=False, error="No action runner configured")
    except Exception as e:
        return ActionResult(success=False, error=str(e))


def init_scheduler(action_runner: Callable[[str, dict], ActionResult]):
    """Initialize scheduler with action runner."""
    scheduler.set_action_runner(action_runner)
    scheduler.start()


get_registry()

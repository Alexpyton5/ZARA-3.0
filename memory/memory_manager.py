import asyncio
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path
from threading import Lock


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()

# Persistent memory must be user-writable in packaged Electron installs.
try:
    from core.paths import memory_dir as _user_memory_dir
    _MEMORY_DIR = _user_memory_dir()
except Exception:
    _MEMORY_DIR = BASE_DIR / "memory"

MEMORY_PATH = _MEMORY_DIR / "long_term.json"
MEMORY_EXPORT_DIR = _MEMORY_DIR / "exports"
LEGACY_MEMORY_PATH = BASE_DIR / "memory" / "long_term.json"
_lock            = Lock()
MAX_VALUE_LENGTH = 380
MEMORY_MAX_CHARS = 2200
_SENSITIVE_MEMORY_KEY_MARKERS = (
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "password",
    "senha",
    "secret",
    "segredo",
    "access_token",
    "refresh_token",
    "token",
)
_SENSITIVE_MEMORY_PATTERNS = (
    re.compile(r"(?i)\b(?:api[_ -]?key|chave[_ -]?de[_ -]?api|authorization|credential|password|senha|secret|segredo|access[_ -]?token|refresh[_ -]?token)\s*[:=]"),
    re.compile(r"(?i)\bbearer\s+[a-z0-9._-]{8,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)

def _empty_memory() -> dict:
    return {
        "identity":      {},
        "preferences":   {},
        "projects":      {},
        "relationships": {},
        "wishes":        {},
        "notes":         {},
    }

def load_memory() -> dict:
    if not MEMORY_PATH.exists():
        return _empty_memory()
    with _lock:
        try:
            data = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                base = _empty_memory()
                for key in base:
                    if key not in data:
                        data[key] = {}
                return data
            return _empty_memory()
        except Exception as e:
            print(f"[Memory] ⚠️ Load error: {e}")
            return _empty_memory()

def _all_entries(memory: dict) -> list[tuple]:
    entries = []
    for cat, items in memory.items():
        if not isinstance(items, dict):
            continue
        for key, entry in items.items():
            if isinstance(entry, dict) and "value" in entry:
                entries.append((cat, key, entry))
    return entries


def _trim_to_limit(memory: dict) -> dict:
    if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
        return memory
    entries = _all_entries(memory)
    entries.sort(key=lambda t: t[2].get("updated", "0000-00-00"))
    for cat, key, _ in entries:
        if len(json.dumps(memory, ensure_ascii=False)) <= MEMORY_MAX_CHARS:
            break
        del memory[cat][key]
        print(f"[Memory] 🗑️  Trimmed {cat}/{key}")
    return memory

def save_memory(memory: dict) -> None:
    if not isinstance(memory, dict):
        return
    memory = _trim_to_limit(memory)
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        MEMORY_PATH.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _truncate_value(val: str) -> str:
    if isinstance(val, str) and len(val) > MAX_VALUE_LENGTH:
        return val[:MAX_VALUE_LENGTH].rstrip() + "…"
    return val


def _recursive_update(target: dict, updates: dict) -> bool:
    changed = False
    for key, value in updates.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, dict) and "value" not in value:
            if key not in target or not isinstance(target[key], dict):
                target[key] = {}
                changed = True
            if _recursive_update(target[key], value):
                changed = True
        else:
            new_val  = _truncate_value(str(value["value"] if isinstance(value, dict) else value))
            entry    = {"value": new_val, "updated": datetime.now().strftime("%Y-%m-%d")}
            existing = target.get(key, {})
            if not isinstance(existing, dict) or existing.get("value") != new_val:
                target[key] = entry
                changed = True
    return changed


def update_memory(memory_update: dict) -> dict:
    if not isinstance(memory_update, dict) or not memory_update:
        return load_memory()
    memory_update = _filter_sensitive_update(memory_update)
    if not memory_update:
        return load_memory()
    memory = load_memory()
    if _recursive_update(memory, memory_update):
        save_memory(memory)
        print(f"[Memory] 💾 Saved: {list(memory_update.keys())}")
    return memory


def is_sensitive_memory(key: str, value: str) -> bool:
    normalized_key = re.sub(r"[^a-z0-9]+", "_", str(key or "").lower()).strip("_")
    if any(
        normalized_key == marker
        or normalized_key.endswith(f"_{marker}")
        or f"_{marker}_" in normalized_key
        for marker in _SENSITIVE_MEMORY_KEY_MARKERS
    ):
        return True
    text = str(value or "")
    return any(pattern.search(text) for pattern in _SENSITIVE_MEMORY_PATTERNS)


def _filter_sensitive_update(updates: dict, path: str = "") -> dict:
    filtered = {}
    for key, value in updates.items():
        key_path = f"{path}.{key}" if path else str(key)
        if isinstance(value, dict) and "value" not in value:
            nested = _filter_sensitive_update(value, key_path)
            if nested:
                filtered[key] = nested
            continue
        candidate = value.get("value") if isinstance(value, dict) else value
        if is_sensitive_memory(key_path, str(candidate or "")):
            print(f"[Memory] Sensitive value skipped: {key_path}")
            continue
        filtered[key] = value
    return filtered


def memory_statistics(memory: dict | None = None) -> dict[str, int]:
    snapshot = memory if isinstance(memory, dict) else load_memory()
    category_count = 0
    entry_count = 0
    for _category, values in snapshot.items():
        if isinstance(values, dict):
            category_count += 1
            entry_count += sum(1 for entry in values.values() if isinstance(entry, dict) and "value" in entry)
    sessions = snapshot.get("sessions", [])
    return {
        "categories": category_count,
        "entries": entry_count,
        "sessions": len(sessions) if isinstance(sessions, list) else 0,
    }


def _redact_memory_for_export(value, path: str = ""):
    if isinstance(value, dict):
        if "value" in value and is_sensitive_memory(path, str(value.get("value") or "")):
            redacted = dict(value)
            redacted["value"] = "[redigido por privacidade]"
            return redacted
        return {
            key: _redact_memory_for_export(item, f"{path}.{key}" if path else str(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_memory_for_export(item, path) for item in value]
    if isinstance(value, str) and is_sensitive_memory(path, value):
        return "[redigido por privacidade]"
    return value


def export_memory(destination: Path | None = None) -> Path:
    memory = _redact_memory_for_export(load_memory())
    export_path = destination or (
        MEMORY_EXPORT_DIR / f"zara-memory-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    )
    export_path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        export_path.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")
    return export_path


def clear_all_memory() -> dict[str, int | str]:
    memory = load_memory()
    statistics = memory_statistics(memory)
    save_memory(_empty_memory())
    try:
        from memory.episodic_memory import clear_episodic_memory

        episodes = clear_episodic_memory(strict=True)
        episodic_error = ""
    except Exception:
        episodes = 0
        episodic_error = "Não foi possível apagar a memória episódica."
    return {
        "entries": statistics["entries"],
        "sessions": statistics["sessions"],
        "episodes": episodes,
        "episodic_error": episodic_error,
    }

def format_memory_for_prompt(memory: dict | None) -> str:
    if not memory:
        return ""

    lines = []

    identity  = memory.get("identity", {})
    id_fields = ["name", "age", "birthday", "city", "job", "language", "school", "nationality"]
    for field in id_fields:
        entry = identity.get(field)
        if entry:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"{field.title()}: {val}")
    for key, entry in identity.items():
        if key in id_fields:
            continue
        val = entry.get("value") if isinstance(entry, dict) else entry
        if val:
            lines.append(f"{key.replace('_', ' ').title()}: {val}")

    prefs = memory.get("preferences", {})
    if prefs:
        lines.append("")
        lines.append("Preferences:")
        for key, entry in list(prefs.items())[:15]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    projects = memory.get("projects", {})
    if projects:
        lines.append("")
        lines.append("Active Projects / Goals:")
        for key, entry in list(projects.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    rels = memory.get("relationships", {})
    if rels:
        lines.append("")
        lines.append("People in their life:")
        for key, entry in list(rels.items())[:10]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    wishes = memory.get("wishes", {})
    if wishes:
        lines.append("")
        lines.append("Wishes / Plans / Wants:")
        for key, entry in list(wishes.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key.replace('_', ' ').title()}: {val}")

    notes = memory.get("notes", {})
    if notes:
        lines.append("")
        lines.append("Other notes:")
        for key, entry in list(notes.items())[:8]:
            val = entry.get("value") if isinstance(entry, dict) else entry
            if val:
                lines.append(f"  - {key}: {val}")

    if not lines:
        return ""

    header = "[WHAT YOU KNOW ABOUT THIS PERSON — use naturally, never recite like a list]\n"
    result = header + "\n".join(lines)
    if len(result) > 2000:
        result = result[:1997] + "…"

    return result + "\n"

def remember(key: str, value: str, category: str = "notes") -> str:
    valid = {"identity", "preferences", "projects", "relationships", "wishes", "notes"}
    if category not in valid:
        category = "notes"
    if is_sensitive_memory(key, value):
        return "Not remembered: sensitive values stay out of long-term memory."
    update_memory({category: {key: {"value": value}}})
    return f"Remembered: {category}/{key} = {value}"


def forget(key: str, category: str = "notes") -> str:
    memory = load_memory()
    cat    = memory.get(category, {})
    if key in cat:
        del cat[key]
        memory[category] = cat
        save_memory(memory)
        return f"Forgotten: {category}/{key}"
    return f"Not found: {category}/{key}"


forget_memory = forget


# ── Session memory ─────────────────────────────────────────────────────────────

_SESSION_MAX = 3   # safety cap — in practice 0-1 entries after pop


def save_session_summary(summary: str, language: str = "") -> None:
    """Append a 1-2 sentence session summary to long_term.json['sessions']."""
    summary = (summary or "").strip()
    if not summary:
        return
    if is_sensitive_memory("session_summary", summary):
        print("[Memory] Sensitive session summary skipped")
        return
    memory   = load_memory()
    sessions = memory.get("sessions", [])
    if not isinstance(sessions, list):
        sessions = []
    entry: dict = {
        "date":    datetime.now().strftime("%Y-%m-%d"),
        "summary": summary[:280],
    }
    if language:
        entry["language"] = language
    sessions.append(entry)
    memory["sessions"] = sessions[-_SESSION_MAX:]
    with _lock:
        MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        MEMORY_PATH.write_text(
            json.dumps(memory, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    try:
        from memory.episodic_memory import record_episode

        record_episode(
            summary,
            metadata={"date": entry["date"], "language": language or "unknown"},
        )
    except Exception as exc:
        print(f"[Memory] Episodic memory skipped: {exc}")
    print(f"[Memory] 📝 Session saved ({entry['date']}): {summary[:60]}…")


def pop_last_session() -> dict | None:
    """
    Return AND remove the most recent session entry.
    Calling this consumes the entry so it is never repeated in future briefings.
    """
    with _lock:
        if not MEMORY_PATH.exists():
            return None
        try:
            memory   = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
            sessions = memory.get("sessions", [])
            if not isinstance(sessions, list) or not sessions:
                return None
            entry = sessions.pop()          # remove the last entry
            memory["sessions"] = sessions
            MEMORY_PATH.write_text(
                json.dumps(memory, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return entry
        except Exception as e:
            print(f"[Memory] ⚠️ pop_last_session error: {e}")
            return None


class MemoryManager:
    """Async-compatible facade used by the Electron IPC layer.

    Long-term semantic facts stay in ``long_term.json`` while raw conversation
    turns are stored as compact episodic records. This keeps the prompt memory
    small and avoids polluting the fact store with chat transcripts.
    """

    def __init__(self) -> None:
        self.initialized = False

    async def initialize(self) -> None:
        def _init() -> None:
            MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
            # One-time migration from the old project/executable-adjacent path.
            if (
                LEGACY_MEMORY_PATH != MEMORY_PATH
                and LEGACY_MEMORY_PATH.is_file()
                and not MEMORY_PATH.exists()
            ):
                try:
                    shutil.copy2(LEGACY_MEMORY_PATH, MEMORY_PATH)
                except OSError as exc:
                    print(f"[Memory] Legacy migration skipped: {exc}")
            if not MEMORY_PATH.exists():
                save_memory(_empty_memory())
            # Touch the episodic store so schema/path problems surface at startup.
            try:
                from memory.episodic_memory import EpisodicMemory
                EpisodicMemory()._connect().close()
            except Exception as exc:
                print(f"[Memory] Episodic store warning: {exc}")

        await asyncio.to_thread(_init)
        self.initialized = True
        print(f"[Memory] Manager ready: {MEMORY_PATH}")

    async def add_conversation(self, user_text: str, assistant_text: str, engine: str = "") -> str | None:
        """Persist a compact conversation episode without changing fact memory."""
        user_text = " ".join(str(user_text or "").split())
        assistant_text = " ".join(str(assistant_text or "").split())
        if not user_text and not assistant_text:
            return None
        combined = f"Usuário: {user_text}\nZARA: {assistant_text}".strip()
        if is_sensitive_memory("conversation", combined):
            print("[Memory] Sensitive conversation episode skipped")
            return None

        def _record() -> str | None:
            from memory.episodic_memory import record_episode
            return record_episode(
                combined,
                kind="conversation",
                metadata={"engine": str(engine or "")[:80]},
            )

        return await asyncio.to_thread(_record)

    def load(self) -> dict:
        return load_memory()

    def save(self, memory: dict) -> None:
        save_memory(memory)

    def update(self, updates: dict) -> dict:
        return update_memory(updates)

    def format_for_prompt(self, memory: dict | None = None) -> str:
        return format_memory_for_prompt(memory or self.load())

    def remember(self, key: str, value: str, category: str = "notes") -> str:
        return remember(key, value, category)

    def forget(self, key: str, category: str = "notes") -> str:
        return forget(key, category)

    def get_stats(self, memory: dict | None = None) -> dict[str, int]:
        return memory_statistics(memory)

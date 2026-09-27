"""Read-only inventory adapter for Codex agent manifests.

The adapter deliberately treats ``.codex/agents`` as data.  It parses TOML
files, normalizes the small inventory contract used by the Lab, and returns
plain JSON-compatible values.  It never imports providers, starts agents, or
writes the workforce policy.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Mapping

try:  # Python 3.11+ (the Windows target uses the stdlib TOML parser).
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - compatibility for older hosts.
    tomllib = None  # type: ignore[assignment]


_AGENT_FILE_SUFFIX = ".toml"
_CAPABILITY_KEYS = (
    "capabilities",
    "capability",
    "skills",
    "skill",
    "specialties",
    "speciality",
    "specialties",
    "tools",
)
_PERMISSION_KEYS = (
    "permissions",
    "permission",
    "allowed_permissions",
    "access",
)
_NESTED_KEYS = ("agent", "metadata", "identity", "profile")

# These are intentionally conservative.  A sentence mentioning a provider is
# not proof that the agent may invoke it, so provider/network permissions are
# never inferred from prose.
_READ_ONLY_MARKERS = (
    "read-only",
    "read only",
    "somente leitura",
    "só lê",
    "nao escreve",
    "não escreve",
    "never edit",
    "never writes",
)
_WRITE_MARKERS = (
    "can write",
    "may write",
    "allowed to write",
    "pode escrever",
    "pode editar",
)
_ROLE_RE = re.compile(r"(?:\*\*)?role(?:\*\*)?\s*[:=]\s*([^\r\n]+)", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.+?)\s*$")


class AgentInventoryError(ValueError):
    """Base error for invalid or unsafe inventory input."""


class DuplicateAgentError(AgentInventoryError):
    """Raised before returning when normalized agent identities collide."""

    def __init__(self, duplicates: Mapping[str, Iterable[str]]) -> None:
        self.duplicates = {
            str(identity): tuple(sorted(str(source) for source in sources))
            for identity, sources in duplicates.items()
        }
        rendered = "; ".join(
            f"{identity}: {', '.join(sources)}"
            for identity, sources in sorted(self.duplicates.items())
        )
        super().__init__(f"duplicate normalized agent identity: {rendered}")


def _text(value: Any) -> str | None:
    if isinstance(value, str):
        value = unicodedata.normalize("NFKC", value)
        value = " ".join(value.strip().split())
        return value or None
    return None


def _slug(value: Any) -> str | None:
    value = _text(value)
    if not value:
        return None
    value = value.casefold()
    value = re.sub(r"[^\w]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"[-_]+", "-", value).strip("-")
    return value or None


def _label(value: Any) -> str | None:
    """Normalize a human label without making it an executable identifier."""
    value = _text(value)
    if not value:
        return None
    return re.sub(r"\s+", " ", value).strip(" .:;,-") or None


def _iter_values(value: Any) -> Iterable[Any]:
    if isinstance(value, (list, tuple, set, frozenset)):
        for item in value:
            yield from _iter_values(item)
    elif isinstance(value, Mapping):
        # Mapping keys are useful as capability/permission labels; values are
        # deliberately ignored because arbitrary TOML values are not a safe
        # permission claim by themselves.
        for key in value:
            yield key
    else:
        yield value


def _normalized_labels(values: Iterable[Any]) -> list[str]:
    labels = {_label(value) for value in values}
    return sorted((value for value in labels if value), key=lambda item: item.casefold())


def _nested_value(document: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in document:
            return document[key]
        for nested_key in _NESTED_KEYS:
            nested = document.get(nested_key)
            if isinstance(nested, Mapping) and key in nested:
                return nested[key]
    return None


def _readable_document(path: Path) -> Mapping[str, Any]:
    if tomllib is None:  # pragma: no cover - only reachable on Python < 3.11.
        raise AgentInventoryError("Python 3.11+ is required to parse agent TOML")
    try:
        with path.open("rb") as stream:
            document = tomllib.load(stream)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise AgentInventoryError(f"cannot parse agent manifest {path}: {exc}") from exc
    if not isinstance(document, dict):
        raise AgentInventoryError(f"agent manifest is not a TOML table: {path}")
    return document


def _extract_role(document: Mapping[str, Any], text: str) -> str | None:
    explicit = _nested_value(document, ("role", "job", "title"))
    role = _label(explicit)
    if role:
        return role
    match = _ROLE_RE.search(text)
    return _label(match.group(1)) if match else None


def _description_capabilities(description: str | None) -> list[str]:
    """Extract only short, declared specialty phrases from a description."""
    if not description:
        return []
    lower = description.casefold()
    markers = (
        "specializes in",
        "specialises in",
        "especialista em",
        "especializado em",
        "expert in",
        "expert em",
    )
    tail: str | None = None
    for marker in markers:
        index = lower.find(marker)
        if index >= 0:
            tail = description[index + len(marker):]
            break
    if tail is None:
        return []
    tail = re.split(r"[.!?]", tail, maxsplit=1)[0]
    parts = re.split(r"\s*(?:,|;|\band\b|\be\b|\bor\b|\bou\b)\s*", tail, flags=re.IGNORECASE)
    return _normalized_labels(part for part in parts if 1 < len(part.split()) <= 12)


def _extract_capabilities(document: Mapping[str, Any], description: str | None, text: str) -> list[str]:
    raw: list[Any] = []
    for key in _CAPABILITY_KEYS:
        value = _nested_value(document, (key,))
        if value is not None:
            raw.extend(_iter_values(value))
    capabilities = _normalized_labels(raw)
    if capabilities:
        return capabilities
    # A structured bullet under a capability heading is a declaration, unlike
    # arbitrary prose.  Keep this bounded so one large instruction block cannot
    # become an unreviewable inventory payload.
    in_capability_section = False
    extracted: list[str] = []
    for line in text.splitlines():
        heading = re.sub(r"^\s*#+\s*", "", line).strip().casefold()
        if line.lstrip().startswith("#"):
            in_capability_section = any(
                word in heading for word in ("capabil", "specializ", "core mission", "what i do")
            )
            continue
        if in_capability_section:
            match = _BULLET_RE.match(line)
            if match:
                value = _label(match.group(1))
                if value and len(value.split()) <= 16:
                    extracted.append(value)
                    if len(extracted) >= 24:
                        break
    return _normalized_labels(extracted) or _description_capabilities(description)


def _extract_permissions(document: Mapping[str, Any], text: str) -> list[str]:
    raw: list[Any] = []
    for key in _PERMISSION_KEYS:
        value = _nested_value(document, (key,))
        if value is not None:
            raw.extend(_iter_values(value))
    permissions = _normalized_labels(raw)

    for key in ("read_only", "readonly"):
        value = _nested_value(document, (key,))
        if value is True:
            permissions.append("read_only")
    for key in ("can_write", "write"):
        value = _nested_value(document, (key,))
        if value is True:
            permissions.append("write")

    lower = text.casefold()
    if any(marker in lower for marker in _READ_ONLY_MARKERS):
        permissions.append("read_only")
    if any(marker in lower for marker in _WRITE_MARKERS):
        permissions.append("write")

    allowed_paths = _nested_value(document, ("allowed_paths", "write_paths", "read_paths"))
    for path in _iter_values(allowed_paths) if allowed_paths is not None else ():
        label = _label(path)
        if label:
            permissions.append(f"path:{label}")
    return sorted(set(permissions), key=lambda item: item.casefold())


def _record(path: Path, document: Mapping[str, Any]) -> dict[str, Any]:
    explicit_name = _nested_value(document, ("name", "display_name"))
    name = _label(explicit_name) or _label(path.stem) or path.stem
    explicit_id = _nested_value(document, ("id", "agent_id"))
    identity = _slug(explicit_id) or _slug(name) or _slug(path.stem)
    if not identity:
        raise AgentInventoryError(f"agent manifest has no usable identity: {path}")

    description = _text(_nested_value(document, ("description", "summary")))
    instruction = _text(_nested_value(document, ("developer_instructions", "instructions"))) or ""
    text = "\n".join(part for part in (description or "", instruction) if part)
    return {
        "id": identity,
        "name": name,
        "role": _extract_role(document, text),
        "capabilities": _extract_capabilities(document, description, text),
        "permissions": _extract_permissions(document, text),
        "source": path.name,
    }


def discover_agent_files(agents_dir: str | Path) -> list[Path]:
    """Return sorted TOML manifests without importing or activating agents."""
    directory = Path(agents_dir)
    if not directory.is_dir():
        raise AgentInventoryError(f"agent directory does not exist: {directory}")
    try:
        files = [
            entry for entry in directory.iterdir()
            if entry.is_file() and entry.suffix.casefold() == _AGENT_FILE_SUFFIX
        ]
    except OSError as exc:
        raise AgentInventoryError(f"cannot enumerate agent directory {directory}: {exc}") from exc
    return sorted(files, key=lambda path: path.name.casefold())


def load_agent_inventory(agents_dir: str | Path) -> list[dict[str, Any]]:
    """Read, normalize, validate, and return a JSON-safe agent inventory.

    Duplicate normalized IDs are rejected before any list is returned.  The
    source filename is retained for auditability; no manifest is modified.
    """
    records = [_record(path, _readable_document(path)) for path in discover_agent_files(agents_dir)]
    by_identity: dict[str, list[str]] = {}
    for record in records:
        by_identity.setdefault(record["id"], []).append(record["source"])
    duplicates = {identity: sources for identity, sources in by_identity.items() if len(sources) > 1}
    if duplicates:
        raise DuplicateAgentError(duplicates)
    records.sort(key=lambda record: (record["id"].casefold(), record["source"].casefold()))
    # Round-trip validation makes the public contract explicit: callers get
    # only JSON primitives, not Path, Enum, dataclass, or TOML objects.
    json.dumps(records, ensure_ascii=False, sort_keys=True)
    return records


def inventory_json(agents_dir: str | Path) -> str:
    """Return the inventory as deterministic UTF-8 JSON for reporting tools."""
    return json.dumps(
        load_agent_inventory(agents_dir),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


__all__ = [
    "AgentInventoryError",
    "DuplicateAgentError",
    "discover_agent_files",
    "inventory_json",
    "load_agent_inventory",
]

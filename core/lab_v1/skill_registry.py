"""Independent, metadata-only registry for versioned Lab skills.

The registry is deliberately local and dependency-free.  It validates a skill
manifest and keeps a defensive copy of that metadata in memory; it never
imports, loads, starts, or otherwise executes a skill.  A caller that needs
persistence can serialize the returned JSON-safe records in its own boundary,
but this module does not open an application database or contact providers.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from enum import Enum
import json
import re
from threading import RLock
from typing import Any, Final


class SkillRegistryError(ValueError):
    """Base exception for invalid registry input or registry operations."""


class InvalidSkillManifest(SkillRegistryError):
    """Raised when a manifest is missing fields or contains invalid fields."""


class InvalidSkillStatus(SkillRegistryError):
    """Raised when a status is not part of the skill lifecycle."""


class InvalidSkillPermission(SkillRegistryError):
    """Raised when a permission list is malformed or contains duplicates."""


class InvalidSkillChecksum(SkillRegistryError):
    """Raised when a checksum is not a SHA-256 digest."""


class InvalidSkillVersion(SkillRegistryError):
    """Raised when a skill version is not a supported semantic version."""


class DuplicateSkill(SkillRegistryError):
    """Raised when the same skill/version is registered with new metadata."""


class SkillNotFound(SkillRegistryError):
    """Raised by strict lookup/update operations for an unknown skill."""


class InvalidSkillTransition(SkillRegistryError):
    """Raised when a skill status would move backwards in its lifecycle."""


class SkillStatus(str, Enum):
    """Supported lifecycle states for a registered skill manifest."""

    DRAFT = "DRAFT"
    TESTING = "TESTING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


SKILL_STATUSES: Final[tuple[str, ...]] = tuple(status.value for status in SkillStatus)
VALID_STATUSES: Final[frozenset[str]] = frozenset(SKILL_STATUSES)

# These are aliases rather than additional lifecycle states.  They make the
# wire format forgiving about common manifest spellings while keeping records
# canonical and unambiguous.
_STATUS_ALIASES: Final[dict[str, str]] = {
    "DRAFT": SkillStatus.DRAFT.value,
    "TESTING": SkillStatus.TESTING.value,
    "READY": SkillStatus.READY.value,
    "ACTIVE": SkillStatus.ACTIVE.value,
    "RETIRED": SkillStatus.RETIRED.value,
}

# Manifest fields are intentionally closed.  An unknown top-level field is a
# typo in a security-sensitive manifest, not silently ignored metadata.
_MANIFEST_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "skill_id",
        "version",
        "status",
        "permissions",
        "checksum",
        "name",
        "description",
        "entrypoint",
        "author",
        "license",
        "homepage",
        "manifest_version",
        "created_at",
        "updated_at",
        "metadata",
    }
)
_FIELD_ALIASES: Final[dict[str, str]] = {
    "id": "skill_id",
    "skill_name": "name",
    "capabilities": "permissions",
    "sha256": "checksum",
    "state": "status",
}
_REQUIRED_FIELDS: Final[frozenset[str]] = frozenset(
    {"skill_id", "version", "permissions", "checksum"}
)

# IDs are stable registry keys.  Versions follow SemVer 2.0.0, including
# optional prerelease/build metadata.  Leading zeroes in numeric components
# are rejected so that one version cannot have multiple spellings.
_SKILL_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,127}$")
_VERSION_RE = re.compile(
    r"^(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)\."
    r"(0|[1-9][0-9]*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)
_PERMISSION_RE = re.compile(r"^[a-z][a-z0-9]*(?:[._:/-][a-z0-9]+)*$")
_CHECKSUM_RE = re.compile(r"^(?:sha256:)?([0-9a-fA-F]{64})$", re.IGNORECASE)


def _json_safe(value: Any, *, field: str) -> Any:
    """Return a JSON-safe defensive copy or reject an unsafe value."""

    if value is None or isinstance(value, (str, int, float, bool)):
        if isinstance(value, float):
            # json.dumps(..., allow_nan=False) gives the clearest finite-value
            # check, while this branch keeps the recursive error field useful.
            try:
                json.dumps(value, allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise InvalidSkillManifest(
                    f"{field} must contain only JSON-safe finite values"
                ) from exc
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise InvalidSkillManifest(
                    f"{field} mapping keys must be non-empty strings"
                )
            result[key] = _json_safe(item, field=f"{field}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, field=field) for item in value]
    raise InvalidSkillManifest(f"{field} must contain only JSON-safe values")


def _text(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise InvalidSkillManifest(f"{field} must be a string")
    normalized = value.strip()
    if not normalized and not allow_empty:
        raise InvalidSkillManifest(f"{field} must not be empty")
    return normalized


def _coerce_status(status: str | SkillStatus) -> str:
    if isinstance(status, SkillStatus):
        return status.value
    if not isinstance(status, str):
        raise InvalidSkillStatus(
            f"status must be one of: {', '.join(SKILL_STATUSES)}"
        )
    normalized = status.strip().upper().replace("-", "_").replace(" ", "_")
    try:
        return _STATUS_ALIASES[normalized]
    except KeyError as exc:
        raise InvalidSkillStatus(
            f"unknown skill status {status!r}; expected one of: "
            f"{', '.join(SKILL_STATUSES)}"
        ) from exc


def _validate_skill_id(value: Any) -> str:
    normalized = _text(value, "skill_id")
    if not _SKILL_ID_RE.fullmatch(normalized):
        raise InvalidSkillManifest(
            "skill_id must start with a letter and contain only letters, "
            "numbers, '.', '_' or '-'; maximum length is 128"
        )
    return normalized


def _validate_version(value: Any) -> str:
    normalized = _text(value, "version")
    if not _VERSION_RE.fullmatch(normalized):
        raise InvalidSkillVersion(
            "version must be a semantic version such as '1.0.0'"
        )
    return normalized


def _normalize_permissions(value: Any) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise InvalidSkillPermission("permissions must be a list or tuple of strings")

    permissions: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise InvalidSkillPermission("each permission must be a string")
        permission = item.strip().lower()
        if not permission:
            raise InvalidSkillPermission("permissions cannot contain empty strings")
        if not _PERMISSION_RE.fullmatch(permission):
            raise InvalidSkillPermission(
                f"invalid permission {item!r}; use names such as 'filesystem.read'"
            )
        if permission in seen:
            raise InvalidSkillPermission(f"duplicate permission {item!r}")
        seen.add(permission)
        permissions.append(permission)
    return permissions


def _normalize_checksum(value: Any) -> str:
    if not isinstance(value, str):
        raise InvalidSkillChecksum("checksum must be a SHA-256 hexadecimal string")
    candidate = value.strip()
    match = _CHECKSUM_RE.fullmatch(candidate)
    if match is None:
        raise InvalidSkillChecksum(
            "checksum must contain exactly 64 hexadecimal characters, optionally "
            "prefixed with 'sha256:'"
        )
    return f"sha256:{match.group(1).lower()}"


def _canonical_aliases(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Copy aliases into canonical keys and reject conflicting spellings."""

    canonical: dict[str, Any] = {}
    for key, value in manifest.items():
        if not isinstance(key, str):
            raise InvalidSkillManifest("manifest field names must be strings")
        target = _FIELD_ALIASES.get(key, key)
        if target in canonical and canonical[target] != value:
            raise InvalidSkillManifest(
                f"manifest contains conflicting values for {target!r}"
            )
        canonical[target] = value
    return canonical


def validate_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and canonicalize a JSON-like skill manifest.

    The returned dictionary is safe to store and serialize.  It contains no
    executable object and no live reference to the caller's input.  ``status``
    defaults to ``DRAFT``; all other required fields must be explicit.
    """

    if not isinstance(manifest, Mapping):
        raise InvalidSkillManifest("manifest must be a mapping")
    canonical = _canonical_aliases(manifest)
    unknown = sorted(set(canonical) - _MANIFEST_FIELDS)
    if unknown:
        raise InvalidSkillManifest(
            f"unknown manifest field(s): {', '.join(unknown)}"
        )
    missing = sorted(_REQUIRED_FIELDS - set(canonical))
    if missing:
        raise InvalidSkillManifest(
            f"manifest is missing required field(s): {', '.join(missing)}"
        )

    result: dict[str, Any] = {
        "skill_id": _validate_skill_id(canonical["skill_id"]),
        "version": _validate_version(canonical["version"]),
        "status": _coerce_status(canonical.get("status", SkillStatus.DRAFT)),
        "permissions": _normalize_permissions(canonical["permissions"]),
        "checksum": _normalize_checksum(canonical["checksum"]),
    }

    for field in (
        "name",
        "description",
        "entrypoint",
        "author",
        "license",
        "homepage",
        "created_at",
        "updated_at",
    ):
        if field in canonical:
            result[field] = _text(canonical[field], field, allow_empty=field == "description")

    if "manifest_version" in canonical:
        manifest_version = canonical["manifest_version"]
        if (
            isinstance(manifest_version, bool)
            or not isinstance(manifest_version, int)
            or manifest_version <= 0
        ):
            raise InvalidSkillManifest("manifest_version must be a positive integer")
        result["manifest_version"] = manifest_version

    if "metadata" in canonical:
        metadata = canonical["metadata"]
        if not isinstance(metadata, Mapping):
            raise InvalidSkillManifest("metadata must be a mapping")
        result["metadata"] = _json_safe(metadata, field="metadata")

    # A final strict serialization guard prevents future optional fields from
    # accidentally widening the public contract to arbitrary Python objects.
    try:
        json.dumps(result, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:  # pragma: no cover - defensive guard
        raise InvalidSkillManifest("manifest must be JSON serializable") from exc
    return result


def _version_key(version: str) -> tuple[Any, ...]:
    """Build a sortable key for the already validated semantic version."""

    match = _VERSION_RE.fullmatch(version)
    if match is None:  # only callable with validated versions
        return (0, 0, 0, 0, version)
    major, minor, patch, prerelease, build = match.groups()
    # Stable releases sort after prereleases.  Build metadata does not affect
    # SemVer precedence, but is included as a deterministic tie-breaker.
    pre_key: tuple[Any, ...] = (1,) if prerelease is None else (0, prerelease)
    return (int(major), int(minor), int(patch), pre_key, build or "")


def _skill_key(skill_id: Any, version: Any) -> tuple[str, str]:
    return _validate_skill_id(skill_id), _validate_version(version)


class SkillRegistry:
    """An in-memory registry for validated, versioned skill metadata.

    Registration is idempotent only when the complete canonical manifest is
    identical.  Attempting to overwrite a ``(skill_id, version)`` record with
    different metadata raises :class:`DuplicateSkill`, preventing a checksum
    or permission change from being hidden by a repeated registration.
    """

    def __init__(self) -> None:
        self._skills: dict[tuple[str, str], dict[str, Any]] = {}
        self._lock = RLock()

    @staticmethod
    def validate(manifest: Mapping[str, Any]) -> dict[str, Any]:
        """Validate a manifest without adding it to a registry."""

        return validate_manifest(manifest)

    def register_skill(
        self,
        manifest: Mapping[str, Any] | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        """Validate and register one manifest, returning a defensive copy.

        A mapping is the canonical form.  Keyword fields are accepted as a
        convenience for metadata-only callers, but never interpreted as code.
        """

        if manifest is None:
            manifest = fields
        elif fields:
            raise TypeError("pass either manifest or keyword fields, not both")
        if not isinstance(manifest, Mapping):
            raise InvalidSkillManifest("manifest must be a mapping")
        normalized = validate_manifest(manifest)
        key = (normalized["skill_id"], normalized["version"])
        with self._lock:
            existing = self._skills.get(key)
            if existing is not None:
                if existing != normalized:
                    raise DuplicateSkill(
                        f"skill {key[0]!r} version {key[1]!r} already has "
                        "different metadata"
                    )
                return deepcopy(existing)
            self._skills[key] = deepcopy(normalized)
            return deepcopy(normalized)

    # Short aliases preserve a small, discoverable API for Lab callers.
    register = register_skill
    add = register_skill
    register_manifest = register_skill

    def update_skill(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        """Replace an existing version only through an explicit state change."""
        if not isinstance(manifest, Mapping):
            raise InvalidSkillManifest("manifest must be a mapping")
        normalized = validate_manifest(manifest)
        key = (normalized["skill_id"], normalized["version"])
        with self._lock:
            if key not in self._skills:
                raise SkillNotFound(f"skill {key[0]!r} version {key[1]!r} is not registered")
            self._skills[key] = deepcopy(normalized)
            return deepcopy(normalized)

    def get_skill(
        self, skill_id: str, version: str | None = None
    ) -> dict[str, Any] | None:
        """Return one version, or the highest version when omitted."""

        normalized_id = _validate_skill_id(skill_id)
        with self._lock:
            if version is not None:
                normalized_version = _validate_version(version)
                record = self._skills.get((normalized_id, normalized_version))
                return None if record is None else deepcopy(record)
            candidates = [
                record
                for (candidate_id, _), record in self._skills.items()
                if candidate_id == normalized_id
            ]
            if not candidates:
                return None
            record = max(candidates, key=lambda item: _version_key(item["version"]))
            return deepcopy(record)

    get = get_skill

    def require_skill(self, skill_id: str, version: str | None = None) -> dict[str, Any]:
        """Return a skill or raise :class:`SkillNotFound`."""

        record = self.get_skill(skill_id, version)
        if record is None:
            suffix = "" if version is None else f" version {version!r}"
            raise SkillNotFound(f"skill {skill_id!r}{suffix} is not registered")
        return record

    def list_skills(
        self,
        status: str | SkillStatus | None = None,
        *,
        skill_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List records in deterministic skill/version order."""

        normalized_status = None if status is None else _coerce_status(status)
        normalized_id = None if skill_id is None else _validate_skill_id(skill_id)
        with self._lock:
            records = [
                record
                for record in self._skills.values()
                if (normalized_status is None or record["status"] == normalized_status)
                and (normalized_id is None or record["skill_id"] == normalized_id)
            ]
            records.sort(key=lambda item: (item["skill_id"], _version_key(item["version"])))
            return deepcopy(records)

    list = list_skills
    list_all = list_skills

    def update_status(
        self,
        skill_id: str,
        version: str,
        status: str | SkillStatus,
    ) -> dict[str, Any] | None:
        """Advance a registered skill without creating or executing anything.

        Lifecycle updates may move forward over intermediate states (for
        example ``DRAFT`` to ``READY``), but never backwards.  ``RETIRED`` is
        terminal except for an idempotent update to ``RETIRED`` itself.
        """

        key = _skill_key(skill_id, version)
        normalized_status = _coerce_status(status)
        with self._lock:
            existing = self._skills.get(key)
            if existing is None:
                return None
            old_rank = SKILL_STATUSES.index(existing["status"])
            new_rank = SKILL_STATUSES.index(normalized_status)
            if new_rank < old_rank:
                raise InvalidSkillTransition(
                    f"cannot move skill {key[0]!r} version {key[1]!r} from "
                    f"{existing['status']} back to {normalized_status}"
                )
            if existing["status"] != normalized_status:
                existing = deepcopy(existing)
                existing["status"] = normalized_status
                self._skills[key] = existing
            return deepcopy(existing)

    set_status = update_status
    transition = update_status

    def count(self, status: str | SkillStatus | None = None) -> int:
        """Return the number of registered records, optionally by status."""

        normalized_status = None if status is None else _coerce_status(status)
        with self._lock:
            return sum(
                1
                for record in self._skills.values()
                if normalized_status is None or record["status"] == normalized_status
            )

    def __len__(self) -> int:
        return self.count()

    def clear(self) -> None:
        """Remove only this registry's in-memory metadata records."""

        with self._lock:
            self._skills.clear()


# Friendly aliases for callers that prefer the storage detail to be explicit.
SkillRegistryStore = SkillRegistry
Registry = SkillRegistry
SkillManifestError = InvalidSkillManifest


__all__ = [
    "DuplicateSkill",
    "InvalidSkillChecksum",
    "InvalidSkillManifest",
    "InvalidSkillPermission",
    "InvalidSkillStatus",
    "InvalidSkillTransition",
    "InvalidSkillVersion",
    "Registry",
    "SKILL_STATUSES",
    "SkillManifestError",
    "SkillNotFound",
    "SkillRegistry",
    "SkillRegistryError",
    "SkillRegistryStore",
    "SkillStatus",
    "VALID_STATUSES",
    "validate_manifest",
]

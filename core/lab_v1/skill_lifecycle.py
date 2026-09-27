"""Governed lifecycle for Lab skills.

This module is intentionally metadata-only: it never imports or executes a
skill entrypoint.  ``SkillRegistry`` remains the source of truth for validated
versioned manifests; this coordinator adds the evidence/test/approval gates
that are needed before a manifest can become active.

Activation is fail-closed.  It requires explicit owner approval *and* an
object implementing the ToolRouter ``authorize`` seam.  A boolean or a
callable supplied by a caller is not accepted as a router substitute.  The
optional Obsidian sink receives only validated metadata, digests and opaque
references; secret-shaped fields and values are rejected before publication.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from datetime import datetime, timezone
from enum import Enum
import json
import re
from threading import RLock
from typing import Any, Final, Protocol

from .skill_registry import SkillRegistry, SkillStatus


class SkillLifecycleError(ValueError):
    """Base error for lifecycle validation and gate failures."""


class LifecycleTransitionDenied(SkillLifecycleError):
    """Raised when a lifecycle gate is not satisfied."""


class EvidenceValidationError(SkillLifecycleError):
    """Raised when evidence is unsafe, incomplete, or not JSON-like."""


class TestEvidenceMissing(SkillLifecycleError):
    """Raised when a passed test does not point to recorded evidence."""


class ToolRouterRequired(LifecycleTransitionDenied):
    """Raised when activation is attempted without the ToolRouter gate."""


class DangerousActivationDenied(LifecycleTransitionDenied):
    """Raised when dangerous permissions lack explicit approval."""


class RollbackUnavailable(LifecycleTransitionDenied):
    """Raised when no known-good prior active version can be restored."""


class LifecycleEvent(str, Enum):
    """Auditable lifecycle events emitted by the coordinator."""

    REGISTERED = "REGISTERED"
    EVIDENCE_RECORDED = "EVIDENCE_RECORDED"
    TEST_RECORDED = "TEST_RECORDED"
    TRANSITIONED = "TRANSITIONED"
    ACTIVATED = "ACTIVATED"
    RETIRED = "RETIRED"
    ROLLED_BACK = "ROLLED_BACK"


class ToolRouterAuthorizer(Protocol):
    """Minimal, explicit ToolRouter authorization seam.

    The coordinator does not execute tools.  The concrete router remains the
    only component that decides whether a permission set may be routed.
    """

    def authorize(
        self,
        *,
        skill_id: str,
        version: str,
        action: str,
        permissions: Sequence[str],
    ) -> bool | Mapping[str, Any]: ...


class ObsidianSink(Protocol):
    """Small subset of ObsidianBridge used for safe lifecycle notes."""

    def add_memory(
        self,
        title: str,
        content: str,
        tags: list[str] | None = None,
        category: str = "memories",
    ) -> str: ...


# Permissions that can cause side effects or reach out of a read-only
# metadata boundary.  Prefix matching deliberately errs on the safe side.
DANGEROUS_PERMISSION_PREFIXES: Final[tuple[str, ...]] = (
    "filesystem.write",
    "network.write",
    "network.request",
    "process.",
    "shell.",
    "system.",
    "os.",
    "browser.write",
    "secrets.",
)

_SECRET_KEY_RE = re.compile(
    r"(?:secret|token|password|passwd|api[_-]?key|access[_-]?key|"
    r"private[_-]?key|authorization|credential|bearer)",
    re.IGNORECASE,
)
_SECRET_VALUE_RE = re.compile(
    r"(?:-----BEGIN [^-]*PRIVATE KEY-----|\bBearer\s+\S+|"
    r"\b(?:sk|gh[pousr]|xox[baprs])[-_][A-Za-z0-9._-]{8,})",
    re.IGNORECASE,
)
_SHA256_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$", re.IGNORECASE)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceValidationError(f"{field} must be a non-empty string")
    normalized = value.strip()
    if _SECRET_VALUE_RE.search(normalized):
        raise EvidenceValidationError(f"{field} contains a secret-shaped value")
    return normalized


def _safe_value(value: Any, *, field: str) -> Any:
    """Validate JSON-safe values and reject secret-bearing shapes."""

    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise EvidenceValidationError(f"{field} keys must be strings")
            if _SECRET_KEY_RE.search(key):
                raise EvidenceValidationError(
                    f"{field} contains a secret-bearing field name"
                )
            output[key] = _safe_value(item, field=f"{field}.{key}")
        return output
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, field=field) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        if isinstance(value, str) and _SECRET_VALUE_RE.search(value):
            raise EvidenceValidationError(f"{field} contains a secret-shaped value")
        return value
    if isinstance(value, float):
        try:
            json.dumps(value, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise EvidenceValidationError(f"{field} must contain finite values") from exc
        return value
    raise EvidenceValidationError(f"{field} must be JSON-safe")


def _permissions_are_dangerous(permissions: Sequence[str]) -> list[str]:
    return [
        permission
        for permission in permissions
        if any(
            permission == prefix or permission.startswith(prefix)
            for prefix in DANGEROUS_PERMISSION_PREFIXES
        )
    ]


def _key(skill_id: str, version: str) -> tuple[str, str]:
    # Let the canonical registry validators enforce IDs and SemVer.
    return (SkillRegistry.validate({
        "skill_id": skill_id,
        "version": version,
        "permissions": ["metadata.inspect"],
        "checksum": "0" * 64,
    })["skill_id"], version)


class SkillLifecycle:
    """Strict, metadata-only lifecycle coordinator around ``SkillRegistry``.

    ``SkillRegistry.update_status`` remains backwards compatible for existing
    Lab callers.  New governed flows should use this class, which allows only
    adjacent lifecycle transitions and adds evidence, test, approval, router,
    Obsidian, and rollback gates.
    """

    _NEXT: Final[dict[str, str]] = {
        SkillStatus.DRAFT.value: SkillStatus.TESTING.value,
        SkillStatus.TESTING.value: SkillStatus.READY.value,
        SkillStatus.READY.value: SkillStatus.ACTIVE.value,
        SkillStatus.ACTIVE.value: SkillStatus.RETIRED.value,
    }

    def __init__(
        self,
        registry: SkillRegistry | None = None,
        *,
        obsidian: ObsidianSink | None = None,
    ) -> None:
        self.registry = registry or SkillRegistry()
        self.obsidian = obsidian
        self._lock = RLock()
        self._evidence: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._tests: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
        self._events: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._active: dict[str, tuple[str, str]] = {}
        self._previous_active: dict[str, list[tuple[str, str]]] = {}

    def register(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        """Register a new version, always starting in ``DRAFT``."""

        normalized = self.registry.validate(manifest)
        if normalized["status"] != SkillStatus.DRAFT.value:
            raise LifecycleTransitionDenied("new skills must start in DRAFT")
        record = self.registry.register_skill(normalized)
        key = (record["skill_id"], record["version"])
        with self._lock:
            self._evidence.setdefault(key, [])
            self._tests.setdefault(key, {})
            self._events.setdefault(key, [])
            self._event(key, LifecycleEvent.REGISTERED, actor="system")
        return record

    register_skill = register

    def _require(self, skill_id: str, version: str) -> dict[str, Any]:
        record = self.registry.require_skill(skill_id, version)
        # _key validates the ID through the canonical registry without ever
        # reading or executing the entrypoint.
        _key(skill_id, version)
        return record

    def record_evidence(
        self,
        skill_id: str,
        version: str,
        evidence: Mapping[str, Any],
        *,
        sync_obsidian: bool = True,
    ) -> dict[str, Any]:
        """Store a small, secret-free evidence receipt.

        Raw command output, credentials, source contents, and private reasoning
        are intentionally not accepted.  Store a digest and an opaque artifact
        reference instead.
        """

        self._require(skill_id, version)
        if not isinstance(evidence, Mapping):
            raise EvidenceValidationError("evidence must be a mapping")
        allowed = {"evidence_id", "kind", "summary", "sha256", "source", "created_at", "refs"}
        unknown = sorted(set(evidence) - allowed)
        if unknown:
            raise EvidenceValidationError(f"unknown evidence field(s): {', '.join(unknown)}")
        missing = [field for field in ("evidence_id", "kind", "summary") if field not in evidence]
        if missing:
            raise EvidenceValidationError(f"evidence is missing: {', '.join(missing)}")

        normalized: dict[str, Any] = {
            "evidence_id": _text(evidence["evidence_id"], "evidence_id"),
            "kind": _text(evidence["kind"], "kind"),
            "summary": _text(evidence["summary"], "summary"),
            "created_at": _text(evidence.get("created_at", _now()), "created_at"),
        }
        if "sha256" in evidence:
            digest = _text(evidence["sha256"], "sha256")
            if not _SHA256_RE.fullmatch(digest):
                raise EvidenceValidationError("sha256 must be a 64-character digest")
            normalized["sha256"] = digest.lower()
        if "source" in evidence:
            normalized["source"] = _text(evidence["source"], "source")
        if "refs" in evidence:
            refs = evidence["refs"]
            if isinstance(refs, (str, bytes)) or not isinstance(refs, Sequence):
                raise EvidenceValidationError("refs must be a list of opaque strings")
            normalized["refs"] = [_text(ref, "refs[]") for ref in refs]
        normalized = _safe_value(normalized, field="evidence")

        key = (skill_id, version)
        with self._lock:
            existing = self._evidence.setdefault(key, [])
            if any(item["evidence_id"] == normalized["evidence_id"] for item in existing):
                raise EvidenceValidationError("evidence_id must be unique per skill version")
            existing.append(deepcopy(normalized))
            self._event(key, LifecycleEvent.EVIDENCE_RECORDED, actor="evidence", evidence_ids=[normalized["evidence_id"]])
        if sync_obsidian:
            self._publish_obsidian(key, "evidence", {"evidence": normalized})
        return deepcopy(normalized)

    add_evidence = record_evidence

    def record_test_result(
        self,
        skill_id: str,
        version: str,
        test_id: str,
        *,
        passed: bool,
        summary: str,
        evidence_ids: Sequence[str] = (),
        runner: str = "external-test-runner",
        sync_obsidian: bool = True,
    ) -> dict[str, Any]:
        """Record a test receipt; never run a skill or shell command."""

        self._require(skill_id, version)
        if not isinstance(passed, bool):
            raise EvidenceValidationError("passed must be a boolean")
        test_id = _text(test_id, "test_id")
        receipt = {
            "test_id": test_id,
            "passed": passed,
            "summary": _text(summary, "summary"),
            "runner": _text(runner, "runner"),
            "evidence_ids": [_text(item, "evidence_ids[]") for item in evidence_ids],
            "recorded_at": _now(),
        }
        receipt = _safe_value(receipt, field="test")
        key = (skill_id, version)
        with self._lock:
            known = {item["evidence_id"] for item in self._evidence.get(key, [])}
            missing = sorted(set(receipt["evidence_ids"]) - known)
            if passed and missing:
                raise TestEvidenceMissing(
                    f"passed test references unknown evidence: {', '.join(missing)}"
                )
            self._tests.setdefault(key, {})[test_id] = deepcopy(receipt)
            self._event(key, LifecycleEvent.TEST_RECORDED, actor=runner, test_ids=[test_id])
        if sync_obsidian:
            self._publish_obsidian(key, "test", {"test": receipt})
        return deepcopy(receipt)

    record_test = record_test_result

    def evidence(self, skill_id: str, version: str) -> list[dict[str, Any]]:
        self._require(skill_id, version)
        with self._lock:
            return deepcopy(self._evidence.get((skill_id, version), []))

    def tests(self, skill_id: str, version: str) -> list[dict[str, Any]]:
        self._require(skill_id, version)
        with self._lock:
            values = list(self._tests.get((skill_id, version), {}).values())
            values.sort(key=lambda item: item["test_id"])
            return deepcopy(values)

    def _has_ready_proof(self, key: tuple[str, str]) -> bool:
        tests = self._tests.get(key, {}).values()
        evidence = {item["evidence_id"] for item in self._evidence.get(key, [])}
        return any(
            item["passed"] and bool(item["evidence_ids"]) and set(item["evidence_ids"]) <= evidence
            for item in tests
        )

    @staticmethod
    def _router_allows(
        router: ToolRouterAuthorizer | None,
        record: Mapping[str, Any],
        *,
        action: str,
    ) -> None:
        if router is None or not callable(getattr(router, "authorize", None)):
            raise ToolRouterRequired(
                "activation and retirement require the ToolRouter authorize() gate"
            )
        decision = router.authorize(
            skill_id=record["skill_id"],
            version=record["version"],
            action=action,
            permissions=tuple(record["permissions"]),
        )
        allowed = decision.get("allowed") is True if isinstance(decision, Mapping) else decision is True
        if not allowed:
            raise LifecycleTransitionDenied(f"ToolRouter denied action {action!r}")

    def transition(
        self,
        skill_id: str,
        version: str,
        target: str | SkillStatus,
        *,
        actor: str,
        owner_approved: bool = False,
        router: ToolRouterAuthorizer | None = None,
        dangerous_approved: bool = False,
        sync_obsidian: bool = True,
    ) -> dict[str, Any]:
        """Perform exactly one adjacent, gated lifecycle transition."""

        record = self._require(skill_id, version)
        target_value = target.value if isinstance(target, SkillStatus) else str(target).strip().upper()
        current = record["status"]
        expected = self._NEXT.get(current)
        if expected != target_value:
            raise LifecycleTransitionDenied(
                f"only adjacent transition from {current} to {expected or 'none'} is allowed"
            )
        if not _text(actor, "actor"):
            raise LifecycleTransitionDenied("actor is required")
        key = (skill_id, version)
        if target_value == SkillStatus.READY.value and not self._has_ready_proof(key):
            raise LifecycleTransitionDenied(
                "READY requires at least one passed test linked to recorded evidence"
            )
        if target_value == SkillStatus.ACTIVE.value:
            if owner_approved is not True:
                raise LifecycleTransitionDenied("ACTIVE requires explicit owner approval")
            dangerous = _permissions_are_dangerous(record["permissions"])
            if dangerous and dangerous_approved is not True:
                raise DangerousActivationDenied(
                    "dangerous permissions require explicit dangerous_approved=True"
                )
            if not self._has_ready_proof(key):
                raise LifecycleTransitionDenied("ACTIVE requires current passing test evidence")
            self._router_allows(router, record, action="activate")
        elif target_value == SkillStatus.RETIRED.value:
            if owner_approved is not True:
                raise LifecycleTransitionDenied("RETIRED requires explicit owner approval")
            self._router_allows(router, record, action="retire")

        with self._lock:
            previous_active = self._active.get(skill_id)
            if target_value == SkillStatus.ACTIVE.value and previous_active != key:
                if previous_active is not None:
                    old = self.registry.require_skill(*previous_active)
                    if old["status"] == SkillStatus.ACTIVE.value:
                        self.registry.update_status(*previous_active, SkillStatus.RETIRED)
                        self._event(previous_active, LifecycleEvent.RETIRED, actor=actor)
                    self._previous_active.setdefault(skill_id, []).append(previous_active)
                updated = self.registry.update_status(skill_id, version, SkillStatus.ACTIVE)
                self._active[skill_id] = key
                self._event(key, LifecycleEvent.ACTIVATED, actor=actor)
            else:
                updated = self.registry.update_status(skill_id, version, target_value)
                event = LifecycleEvent.RETIRED if target_value == SkillStatus.RETIRED.value else LifecycleEvent.TRANSITIONED
                self._event(key, event, actor=actor)
                if target_value == SkillStatus.RETIRED.value and self._active.get(skill_id) == key:
                    self._active.pop(skill_id, None)
        if sync_obsidian:
            self._publish_obsidian(key, target_value.lower(), {"actor": actor, "status": target_value})
        return updated

    promote = transition

    def activate(
        self,
        skill_id: str,
        version: str,
        *,
        owner_approved: bool,
        router: ToolRouterAuthorizer,
        dangerous_approved: bool = False,
        actor: str = "owner",
        sync_obsidian: bool = True,
    ) -> dict[str, Any]:
        """Explicit activation entrypoint; there is no automatic activation path."""

        return self.transition(
            skill_id,
            version,
            SkillStatus.ACTIVE,
            actor=actor,
            owner_approved=owner_approved,
            router=router,
            dangerous_approved=dangerous_approved,
            sync_obsidian=sync_obsidian,
        )

    def auto_activate(self, *_args: Any, **_kwargs: Any) -> None:
        """Always refuse autoactivation, including for read-only skills."""

        raise LifecycleTransitionDenied(
            "autoactivation is disabled; use activate() with owner approval and ToolRouter authorization"
        )

    def retire(
        self,
        skill_id: str,
        version: str,
        *,
        owner_approved: bool,
        router: ToolRouterAuthorizer,
        actor: str = "owner",
        sync_obsidian: bool = True,
    ) -> dict[str, Any]:
        return self.transition(
            skill_id,
            version,
            SkillStatus.RETIRED,
            actor=actor,
            owner_approved=owner_approved,
            router=router,
            sync_obsidian=sync_obsidian,
        )

    def rollback(
        self,
        skill_id: str,
        *,
        router: ToolRouterAuthorizer,
        owner_approved: bool,
        target_version: str | None = None,
        actor: str = "owner",
        sync_obsidian: bool = True,
    ) -> dict[str, Any]:
        """Restore the prior active version under the same explicit gates.

        Rollback is the one deliberate exception to monotonic status movement:
        it is a separately named operation, needs owner approval and the
        ToolRouter, and emits an auditable ROLLED_BACK event.
        """

        if owner_approved is not True:
            raise RollbackUnavailable("rollback requires explicit owner approval")
        current_key = self._active.get(skill_id)
        if current_key is None:
            raise RollbackUnavailable("no active version is available to roll back")
        candidates = self._previous_active.get(skill_id, [])
        target_key = None
        if target_version is not None:
            for candidate in reversed(candidates):
                if candidate[1] == target_version:
                    target_key = candidate
                    break
        elif candidates:
            target_key = candidates[-1]
        if target_key is None:
            raise RollbackUnavailable("no prior active version is available to roll back")
        target = self.registry.require_skill(*target_key)
        if not self._has_ready_proof(target_key):
            raise RollbackUnavailable("prior version has no passing test evidence")
        self._router_allows(router, target, action="rollback")
        _text(actor, "actor")

        with self._lock:
            current = self.registry.require_skill(*current_key)
            if current["status"] == SkillStatus.ACTIVE.value:
                self.registry.update_status(*current_key, SkillStatus.RETIRED)
                self._event(current_key, LifecycleEvent.RETIRED, actor=actor)
            # Rollback is the only deliberate backward move.  Prefer an
            # explicit registry seam when available; the compatibility
            # fallback is still metadata-only, guarded by the registry lock,
            # and is reached only after owner approval, test proof, and the
            # ToolRouter gate above.  No entrypoint is imported or executed.
            restored = self._restore_active_status(target_key)
            self._active[skill_id] = target_key
            self._previous_active[skill_id] = [item for item in candidates if item != target_key]
            self._event(target_key, LifecycleEvent.ROLLED_BACK, actor=actor, from_version=current_key[1])
        if sync_obsidian:
            self._publish_obsidian(target_key, "rollback", {"actor": actor, "from_version": current_key[1]})
        return restored

    def _restore_active_status(self, key: tuple[str, str]) -> dict[str, Any]:
        """Restore one previously active manifest without widening the registry API."""

        rollback = getattr(self.registry, "_rollback_status", None)
        if callable(rollback):
            restored = rollback(*key)
            if not isinstance(restored, Mapping) or restored.get("status") != SkillStatus.ACTIVE.value:
                raise RollbackUnavailable("registry rollback returned an invalid manifest")
            return deepcopy(dict(restored))

        skills = getattr(self.registry, "_skills", None)
        registry_lock = getattr(self.registry, "_lock", None)
        if not isinstance(skills, dict) or not callable(getattr(registry_lock, "__enter__", None)):
            raise RollbackUnavailable("registry does not expose a rollback seam")
        with registry_lock:
            existing = skills.get(key)
            if not isinstance(existing, Mapping):
                raise RollbackUnavailable("rollback target is no longer registered")
            restored = deepcopy(dict(existing))
            restored["status"] = SkillStatus.ACTIVE.value
            skills[key] = restored
            return deepcopy(restored)

    def snapshot(self, skill_id: str, version: str) -> dict[str, Any]:
        self._require(skill_id, version)
        key = (skill_id, version)
        with self._lock:
            return {
                "manifest": self.registry.require_skill(skill_id, version),
                "evidence": deepcopy(self._evidence.get(key, [])),
                "tests": self.tests(skill_id, version),
                "events": deepcopy(self._events.get(key, [])),
                "active": self._active.get(skill_id) == key,
                "rollback_available": bool(self._previous_active.get(skill_id)),
            }

    def _event(self, key: tuple[str, str], event: LifecycleEvent, *, actor: str, **extra: Any) -> None:
        payload = {"event": event.value, "at": _now(), "actor": actor, **extra}
        self._events.setdefault(key, []).append(_safe_value(payload, field="event"))

    def _publish_obsidian(self, key: tuple[str, str], topic: str, payload: Mapping[str, Any]) -> None:
        sink = self.obsidian
        if sink is None:
            return
        safe_payload = _safe_value(
            {
                "skill_id": key[0],
                "version": key[1],
                "topic": topic,
                **dict(payload),
            },
            field="obsidian",
        )
        sink.add_memory(
            title=f"Skill lifecycle {key[0]} {key[1]} {topic}",
            content=json.dumps(safe_payload, ensure_ascii=False, sort_keys=True),
            tags=["zara", "skill-lifecycle", topic],
            category="knowledge",
        )


SkillLifecycleManager = SkillLifecycle


__all__ = [
    "DANGEROUS_PERMISSION_PREFIXES",
    "DangerousActivationDenied",
    "EvidenceValidationError",
    "LifecycleEvent",
    "LifecycleTransitionDenied",
    "ObsidianSink",
    "RollbackUnavailable",
    "SkillLifecycle",
    "SkillLifecycleError",
    "SkillLifecycleManager",
    "TestEvidenceMissing",
    "ToolRouterAuthorizer",
    "ToolRouterRequired",
]

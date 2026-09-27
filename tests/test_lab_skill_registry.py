"""Tests for the independent, metadata-only Lab skill registry."""

from __future__ import annotations

import json

import pytest

from core.lab_v1.skill_registry import (
    DuplicateSkill,
    InvalidSkillChecksum,
    InvalidSkillManifest,
    InvalidSkillPermission,
    InvalidSkillStatus,
    InvalidSkillTransition,
    InvalidSkillVersion,
    SKILL_STATUSES,
    SkillNotFound,
    SkillRegistry,
    SkillStatus,
    validate_manifest,
)


CHECKSUM = "a" * 64


def manifest(**overrides):
    value = {
        "skill_id": "local-reader",
        "version": "1.0.0",
        "permissions": ["filesystem.read", "metadata.inspect"],
        "checksum": CHECKSUM,
        "name": "Local reader",
        "description": "Reads declared local metadata.",
        "entrypoint": "skills.local_reader",
        "metadata": {"owner": "lab", "safe": True},
    }
    value.update(overrides)
    return value


def test_manifest_defaults_to_draft_and_returns_json_safe_canonical_metadata():
    normalized = validate_manifest(manifest())

    assert normalized["status"] == SkillStatus.DRAFT.value
    assert normalized["skill_id"] == "local-reader"
    assert normalized["version"] == "1.0.0"
    assert normalized["permissions"] == ["filesystem.read", "metadata.inspect"]
    assert normalized["checksum"] == f"sha256:{CHECKSUM}"
    assert json.loads(json.dumps(normalized)) == normalized


def test_all_lifecycle_statuses_are_supported_and_canonicalized():
    assert SKILL_STATUSES == ("DRAFT", "TESTING", "READY", "ACTIVE", "RETIRED")

    for status in SKILL_STATUSES:
        normalized = validate_manifest(manifest(status=status.lower()))
        assert normalized["status"] == status


def test_manifest_aliases_are_accepted_but_output_uses_stable_field_names():
    normalized = validate_manifest(
        {
            "id": "alias-skill",
            "version": "2.1.0",
            "capabilities": ("filesystem.read",),
            "sha256": CHECKSUM.upper(),
            "state": "testing",
        }
    )

    assert normalized == {
        "skill_id": "alias-skill",
        "version": "2.1.0",
        "status": "TESTING",
        "permissions": ["filesystem.read"],
        "checksum": f"sha256:{CHECKSUM}",
    }


def test_required_and_unknown_fields_are_rejected():
    for field in ("skill_id", "version", "permissions", "checksum"):
        incomplete = manifest()
        del incomplete[field]
        with pytest.raises(InvalidSkillManifest):
            validate_manifest(incomplete)

    with pytest.raises(InvalidSkillManifest, match="unknown manifest field"):
        validate_manifest(manifest(unexpected=True))

    with pytest.raises(InvalidSkillManifest, match="conflicting"):
        validate_manifest(manifest(id="different-id"))


def test_skill_ids_and_semantic_versions_are_validated():
    for skill_id in ("", "1-starts-with-number", "has space", "bad/$id"):
        with pytest.raises(InvalidSkillManifest):
            validate_manifest(manifest(skill_id=skill_id))

    for version in ("1", "v1.0.0", "1.0", "01.0.0", "1.0.0.0"):
        with pytest.raises(InvalidSkillVersion):
            validate_manifest(manifest(version=version))

    assert validate_manifest(manifest(version="1.2.3-beta.1+build.7"))["version"] == (
        "1.2.3-beta.1+build.7"
    )


def test_status_and_permission_values_are_validated():
    with pytest.raises(InvalidSkillStatus):
        validate_manifest(manifest(status="PAUSED"))

    for permissions in ("filesystem.read", [""], ["filesystem.read", "filesystem.read"], [7]):
        with pytest.raises(InvalidSkillPermission):
            validate_manifest(manifest(permissions=permissions))

    assert validate_manifest(manifest(permissions=[" FILESYSTEM.READ "]))[
        "permissions"
    ] == ["filesystem.read"]


def test_checksum_must_be_a_sha256_hex_digest():
    assert validate_manifest(manifest(checksum=f"SHA256:{CHECKSUM.upper()}"))["checksum"] == (
        f"sha256:{CHECKSUM}"
    )

    for checksum in ("", "not-a-digest", "a" * 63, "g" * 64, 7):
        with pytest.raises(InvalidSkillChecksum):
            validate_manifest(manifest(checksum=checksum))


def test_optional_fields_and_metadata_are_json_safe_and_defensive():
    source_metadata = {"nested": {"enabled": True}, "tags": ["local"]}
    normalized = validate_manifest(
        manifest(
            manifest_version=1,
            created_at="2026-01-01T00:00:00+00:00",
            updated_at="2026-01-02T00:00:00+00:00",
            metadata=source_metadata,
        )
    )
    source_metadata["tags"].append("changed")

    assert normalized["metadata"] == {"nested": {"enabled": True}, "tags": ["local"]}
    assert normalized["manifest_version"] == 1
    json.dumps(normalized)

    with pytest.raises(InvalidSkillManifest):
        validate_manifest(manifest(metadata={"not-safe": object()}))
    with pytest.raises(InvalidSkillManifest):
        validate_manifest(manifest(manifest_version=0))


def test_registry_registers_versions_without_executing_or_persisting_skill_code():
    registry = SkillRegistry()
    v1 = registry.register_skill(manifest())
    v2 = registry.register_skill(manifest(version="2.0.0", permissions=["metadata.inspect"]))

    assert registry.count() == 2
    assert registry.get_skill("local-reader", "1.0.0") == v1
    assert registry.get_skill("local-reader") == v2
    assert registry.list_skills(skill_id="local-reader") == [v1, v2]
    assert registry.list_skills(SkillStatus.DRAFT) == [v1, v2]

    # Returned metadata and caller-owned nested input cannot mutate registry state.
    v1["permissions"].append("unexpected.permission")
    v2["metadata"] = {"changed": True}
    assert registry.get_skill("local-reader", "1.0.0")["permissions"] == [
        "filesystem.read",
        "metadata.inspect",
    ]
    assert registry.get_skill("local-reader", "2.0.0")["metadata"] == {
        "owner": "lab",
        "safe": True,
    }


def test_registration_is_idempotent_only_for_identical_metadata():
    registry = SkillRegistry()
    original = registry.register(manifest())
    assert registry.register(manifest()) == original
    assert registry.count() == 1

    with pytest.raises(DuplicateSkill):
        registry.register(manifest(permissions=["metadata.inspect"]))
    assert registry.get_skill("local-reader", "1.0.0") == original


def test_status_updates_only_advance_the_lifecycle_and_unknown_updates_are_safe():
    registry = SkillRegistry()
    registry.register(manifest())

    for status in SKILL_STATUSES[1:]:
        updated = registry.update_status("local-reader", "1.0.0", status)
        assert updated is not None
        assert updated["status"] == status

    with pytest.raises(InvalidSkillTransition):
        registry.update_status("local-reader", "1.0.0", SkillStatus.ACTIVE)
    assert registry.update_status("local-reader", "1.0.0", SkillStatus.RETIRED)[
        "status"
    ] == "RETIRED"
    assert registry.update_status("missing", "1.0.0", "ACTIVE") is None
    assert registry.list_skills("RETIRED")[0]["skill_id"] == "local-reader"


def test_strict_lookup_and_filters_have_stable_behavior():
    registry = SkillRegistry()
    registry.register(manifest())

    assert registry.get_skill("missing") is None
    with pytest.raises(SkillNotFound):
        registry.require_skill("missing")
    assert registry.require_skill("local-reader")["version"] == "1.0.0"
    assert registry.count("DRAFT") == 1
    assert registry.count("ACTIVE") == 0

    with pytest.raises(InvalidSkillStatus):
        registry.list_skills("UNKNOWN")

    registry.clear()
    assert len(registry) == 0

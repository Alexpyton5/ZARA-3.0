from core.lab_v1.agent_profiles import AgentProfileStore
from core.lab_v1.domain import AgentProfile
from core.lab_v1.source_mission import profile_permission_allows


def test_profile_versions_can_be_read_and_rolled_back(tmp_path):
    store = AgentProfileStore(tmp_path / "profiles")

    first = store.update(
        "artemis", soul="# Artemis\nPriorize clareza.", model="gpt-5.6-sol",
        permissions=["read_workspace"],
    )
    second = store.update(
        "artemis", soul="# Artemis\nPriorize velocidade.", model="gpt-6-astra",
        permissions=["read_workspace", "run_tests"],
    )

    assert first["version"] == 1
    assert second["version"] == 2
    assert [item["version"] for item in store.history("artemis")] == [2, 1]

    restored = store.rollback("artemis", 1)

    assert restored["version"] == 3
    assert restored["soul"] == "# Artemis\nPriorize clareza."
    assert restored["model"] == "gpt-5.6-sol"
    assert restored["permissions"] == ["read_workspace"]


def test_configured_permissions_are_enforced_for_source_work():
    legacy = AgentProfile("legacy", "Legacy", "test", "test", capabilities=["model.text"])
    configured = AgentProfile(
        "builder", "Builder", "test", "test",
        capabilities=["model.text", "profile.permissions.configured", "permission:read_workspace"],
    )

    assert profile_permission_allows(legacy, "run_tests") is True
    assert profile_permission_allows(configured, "read_workspace") is True
    assert profile_permission_allows(configured, "run_tests") is False

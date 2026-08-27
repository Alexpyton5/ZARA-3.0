"""Security regressions for environment and directory-listing actions."""

import os

from core.action_registry import get_registry
from core.actions.files import files_list_action
from core.actions.system import system_env_action
import core.actions  # noqa: F401 -- garante que as actions estao registradas
from core.action_registry import get_registry


def load_capability(name):
    return get_registry().get_spec(name) is not None


def test_system_env_is_gated_as_medium_code_execution():
    assert load_capability("system_env") is True
    spec = get_registry().get_spec("system_env")

    assert (spec.risk, spec.capability) == ("MEDIUM", "CODE_EXECUTION")


def test_system_env_requires_capability_and_medium_risk_gates(monkeypatch):
    secret = "must-never-appear-in-an-action-result"
    assert load_capability("system_env") is True
    registry = get_registry()
    monkeypatch.delenv("ZARA_TEST_GATED_ENV", raising=False)
    monkeypatch.setattr(registry, "pc_control_allowed", False)
    monkeypatch.setattr(registry, "medium_risk_open", False)

    capability_blocked = registry.execute("system_env", var_name="ZARA_TEST_GATED_ENV", value=secret)

    assert capability_blocked.success is False
    assert "Superc" in capability_blocked.error
    assert secret not in capability_blocked.error
    assert "ZARA_TEST_GATED_ENV" not in os.environ

    monkeypatch.setattr(registry, "pc_control_allowed", True)
    medium_blocked = registry.execute("system_env", var_name="ZARA_TEST_GATED_ENV", value=secret)

    assert medium_blocked.success is False
    assert "MEDIUM risk" in medium_blocked.error
    assert secret not in medium_blocked.error
    assert "ZARA_TEST_GATED_ENV" not in os.environ

    authorized = registry.execute("system_env", var_name="ZARA_TEST_GATED_ENV", value=secret, confirm=True)

    assert authorized.success is True
    assert os.environ["ZARA_TEST_GATED_ENV"] == secret
    assert secret not in authorized.output


def test_system_env_refuses_arbitrary_environment_inspection(monkeypatch):
    secret = "must-never-appear-in-an-action-result"
    monkeypatch.setenv("ZARA_TEST_SECRET", secret)

    listed = system_env_action()
    named = system_env_action("ZARA_TEST_SECRET")

    for result in (listed, named):
        assert result.success is False
        assert result.error == "ENVIRONMENT_READ_BLOCKED"
        assert secret not in result.output
        assert secret not in result.error
        assert result.data is None


def test_system_env_never_echoes_the_value_being_set(monkeypatch):
    secret = "must-never-appear-in-an-action-result"
    monkeypatch.delenv("ZARA_TEST_PUBLIC_NAME", raising=False)

    result = system_env_action("ZARA_TEST_PUBLIC_NAME", secret)

    assert result.success is True
    assert secret not in result.output
    assert secret not in result.error
    assert result.data is None


def test_files_list_skips_sensitive_children_without_exposing_names(tmp_path):
    public = tmp_path / "public.txt"
    public.write_text("public", encoding="utf-8")
    secret = tmp_path / "credentials" / "token.json"
    secret.parent.mkdir()
    secret.write_text("must-never-appear-in-an-action-result", encoding="utf-8")

    result = files_list_action(str(tmp_path), recursive=True)

    assert result.success is True
    assert [item["path"] for item in result.data["files"]] == ["public.txt"]
    assert "credentials" not in result.output
    assert "token.json" not in result.output
    assert "must-never-appear-in-an-action-result" not in result.output


def test_files_list_rejects_sensitive_base_path(tmp_path):
    sensitive = tmp_path / ".ssh"
    sensitive.mkdir()

    result = files_list_action(str(sensitive))

    assert result.success is False
    assert result.error == "Acesso a caminho sensível (credenciais/chaves) bloqueado."
    assert result.data is None

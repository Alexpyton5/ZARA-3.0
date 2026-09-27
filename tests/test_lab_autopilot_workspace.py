"""A packaged Lab must observe a persistent source checkout, not _MEI."""

from __future__ import annotations

import threading
from types import SimpleNamespace

from core.lab_v1 import autopilot as autopilot_module
from core.lab_v1.evolution import EvolutionEngine
from core.lab_v1.service import ImprovementScheduler
from core.lab_v1.store import LabStore
from core.lab_v1.workforce_policy import WorkforcePolicy


def _source_checkout(root):
    for name in (
        ".git/HEAD", "tools/build_current.py",
        "core/lab_v1/autopilot.py", "core/lab_v1/evolution.py",
    ):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "zara-3.0"\n', encoding="utf-8"
    )
    return root


def test_mei_workspace_resolves_to_verified_persistent_checkout(tmp_path, monkeypatch):
    transient = tmp_path / "_MEI123456"
    transient.mkdir()
    checkout = _source_checkout(tmp_path / "persistent-source")
    monkeypatch.setattr(
        autopilot_module, "_persistent_checkout_candidates", lambda: (checkout,)
    )
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    policy = WorkforcePolicy({"workspace": str(transient)})

    engine = EvolutionEngine(SimpleNamespace(store=store), transient, policy=policy)

    assert engine.workspace == checkout.resolve()
    assert policy.document["workspace"] == str(checkout.resolve())
    assert [item["source_path"] for item in engine.observe_local()] == [
        "core/lab_v1/autopilot.py", "core/lab_v1/evolution.py"
    ]


def test_mei_without_verified_checkout_reports_configuration_error(tmp_path, monkeypatch):
    transient = tmp_path / "_MEI123456"
    transient.mkdir()
    monkeypatch.setattr(
        autopilot_module, "_persistent_checkout_candidates", lambda: ()
    )
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    runtime = SimpleNamespace(store=store)
    policy = {"workspace": str(transient), "max_new_evolution_missions_per_day": 1}
    supervisor = SimpleNamespace(policy=lambda: policy, lock=threading.Lock())
    scheduler = ImprovementScheduler(runtime, supervisor)

    result = scheduler.cycle(now=1)

    assert result["state"] == "WORKSPACE_NOT_CONFIGURED"
    assert result["dispatched"] is False
    assert scheduler.state()["state"] == "WORKSPACE_NOT_CONFIGURED"


def test_unverified_arbitrary_fallback_is_rejected(tmp_path, monkeypatch):
    transient = tmp_path / "_MEI123456"
    transient.mkdir()
    unrelated = _source_checkout(tmp_path / "unrelated")
    (unrelated / "pyproject.toml").write_text(
        '[project]\nname = "other-project"\n', encoding="utf-8"
    )
    monkeypatch.setattr(
        autopilot_module, "_persistent_checkout_candidates", lambda: (unrelated,)
    )

    assert autopilot_module.resolve_lab_source_checkout(transient) is None


def test_missing_explicit_workspace_reports_configuration_error(tmp_path):
    missing = tmp_path / "checkout-that-was-moved"
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    runtime = SimpleNamespace(store=store)
    policy = {"workspace": str(missing), "max_new_evolution_missions_per_day": 1}
    supervisor = SimpleNamespace(policy=lambda: policy, lock=threading.Lock())

    result = ImprovementScheduler(runtime, supervisor).cycle(now=1)

    assert result["state"] == "WORKSPACE_NOT_CONFIGURED"
    assert result["dispatched"] is False
    assert policy["workspace"] == str(missing)


def test_existing_explicit_worktree_and_empty_fixture_remain_valid(tmp_path):
    worktree = _source_checkout(tmp_path / "source-worktree")
    (worktree / ".git" / "HEAD").unlink()
    (worktree / ".git").rmdir()
    (worktree / ".git").write_text("gitdir: C:/repo/.git/worktrees/source\n", encoding="utf-8")
    empty_fixture = tmp_path / "empty-workspace"
    empty_fixture.mkdir()

    assert autopilot_module.resolve_lab_source_checkout(worktree) == worktree.resolve()
    assert autopilot_module.resolve_lab_source_checkout(empty_fixture) == empty_fixture.resolve()

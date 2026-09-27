"""Provider-free observation which dispatches one dynamic sandbox mission.

This module contains observations, never repairs. Production activation stays
outside this observer and always requires the owner's approval.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from core.lab_v1.autopilot import (Autopilot, WORKFLOW, WorkspaceNotConfigured,
                                   resolve_lab_source_checkout)


LEGACY_WORKFLOW = "reviewed-candidate-update-v1"
DEFAULT_SOURCE = "core/lab_v1/feedback_inbox.py"
COUNTEREXAMPLE = "A ZARA está sem erro e sem falha."


def _digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class EvolutionEngine:
    """Observe deterministic defects and dispatch the canonical workflow."""

    def __init__(self, runtime, workspace, *, policy=None, checker=None, autopilot=None):
        self.runtime, self.store = runtime, runtime.store
        source = resolve_lab_source_checkout(workspace)
        self.workspace = source
        self.policy = policy
        if source is not None and policy is not None:
            # This is an in-memory policy for this run; keep persisted user
            # configuration intact while source missions use the real checkout.
            policy.document['workspace'] = str(source)
        self.checker = checker or self._check_counterexample
        # Keep passive source observation provider-free.  The canonical
        # Autopilot is created only when a justified mission is dispatched.
        self.autopilot = autopilot
        with self.store._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS lab_evolution (
                    session_id TEXT PRIMARY KEY REFERENCES sessions(id),
                    repair_id TEXT NOT NULL UNIQUE, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS lab_evolution_proposals (
                    gap_id TEXT PRIMARY KEY, required TEXT NOT NULL,
                    state TEXT NOT NULL, document TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS lab_evolution_observer (
                    id INTEGER PRIMARY KEY CHECK(id=1), document TEXT NOT NULL);
            """)

    def snapshot(self, sid=None):
        with self.store._connect() as conn:
            row = conn.execute(
                "SELECT document FROM lab_evolution "
                + ("WHERE session_id=?" if sid else "ORDER BY rowid DESC LIMIT 1"),
                (sid,) if sid else (),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def proposals(self):
        with self.store._connect() as conn:
            return [json.loads(row[0]) for row in conn.execute(
                "SELECT document FROM lab_evolution_proposals ORDER BY rowid")]

    def observer_snapshot(self):
        with self.store._connect() as conn:
            row = conn.execute(
                "SELECT document FROM lab_evolution_observer WHERE id=1"
            ).fetchone()
        return json.loads(row[0]) if row else None

    def _record_unsupported_gaps(self):
        with self.store._connect() as conn:
            for gap in self.store.list_capability_gaps():
                if gap.required.startswith("runtime.action."):
                    continue
                proposal = {
                    "gap_id": gap.id,
                    "required": gap.required,
                    "state": "PROPOSAL_ONLY_UNSUPPORTED",
                    "reason": "No executable repair catalog is supported",
                    "created_at": time.time(),
                }
                conn.execute(
                    "INSERT OR IGNORE INTO lab_evolution_proposals VALUES(?,?,?,?)",
                    (gap.id, gap.required, proposal["state"], json.dumps(proposal)),
                )

    def _source_inventory(self):
        paths = []
        for name in ("core", "memory"):
            root = self.workspace / name
            if root.is_dir():
                paths.extend(root.rglob("*.py"))
        return [{"source_path": path.relative_to(self.workspace).as_posix(),
                 "source_sha256": _digest_bytes(path.read_bytes())}
                for path in sorted(paths)
                if path.is_file() and "hermes" not in path.as_posix().casefold()]

    def observe_local(self):
        """Hash real local source and persist a provider-free heartbeat."""
        if self.workspace is None:
            raise WorkspaceNotConfigured('WORKSPACE_NOT_CONFIGURED: persistent source checkout not found')
        inventory = self._source_inventory()
        previous = self.observer_snapshot() or {}
        old_hashes = {item["source_path"]: item["source_sha256"]
                      for item in previous.get("sources", [])}
        new_hashes = {item["source_path"]: item["source_sha256"] for item in inventory}
        changed = sorted(path for path in set(old_hashes) | set(new_hashes)
                         if old_hashes.get(path) != new_hashes.get(path))
        document = {
            "observed_at": time.time(),
            "inventory_count": len(inventory),
            "inventory_sha256": _digest_bytes(json.dumps(
                inventory, sort_keys=True, separators=(",", ":")).encode()),
            "changed_paths": changed,
            "sources": inventory,
            "provider_calls": 0,
        }
        with self.store._connect() as conn:
            conn.execute(
                "INSERT INTO lab_evolution_observer VALUES(1,?) "
                "ON CONFLICT(id) DO UPDATE SET document=excluded.document",
                (json.dumps(document),),
            )
        return inventory

    def _capability_gap_evidence(self):
        evidence = []
        for gap in self.store.list_capability_gaps():
            try:
                detail = json.loads(gap.detail)
            except (TypeError, ValueError):
                detail = gap.detail
            evidence.append({"id": gap.id, "required": gap.required,
                             "available": gap.available, "detail": detail,
                             "created_at": gap.created_at})
        return evidence

    @staticmethod
    def _runtime_gap_sources(inventory, gaps):
        by_path = {item["source_path"]: item for item in inventory}
        sources, relevant = [], []
        for gap in gaps:
            detail = gap.get("detail")
            path = detail.get("source_path") if isinstance(detail, dict) else None
            if gap["required"].startswith("runtime.action.") and path in by_path:
                relevant.append(gap)
                if by_path[path] not in sources:
                    sources.append(by_path[path])
        return sources[:3], relevant

    @staticmethod
    def _observation_id(kind, sources):
        payload = json.dumps({"kind": kind, "sources": sources}, sort_keys=True).encode()
        return kind.casefold() + ":" + _digest_bytes(payload)

    def _already_observed(self, observation_id):
        with self.store._connect() as conn:
            return conn.execute(
                "SELECT session_id FROM lab_evolution WHERE repair_id=?", (observation_id,)
            ).fetchone()

    def _inspection_batches(self, inventory):
        return [inventory[start:start + 3] for start in range(0, len(inventory), 3)]

    def _dispatch(self, *, observation_id, objective, evidence, sources, observation):
        if self.autopilot is None:
            self.autopilot = Autopilot(self.runtime, policy=self.policy)
        started = self.autopilot.start(
            objective, mission_kind="SELF_IMPROVEMENT", evidence=evidence
        )
        if not started.get("success"):
            return started
        document = {
            "session_id": started["session_id"], "repair_id": observation_id,
            "workflow": WORKFLOW, "mission_kind": "SELF_IMPROVEMENT",
            "source": str(self.workspace / sources[0]["source_path"]),
            "source_path": sources[0]["source_path"], "sources": sources,
            "observation": observation, "state": started.get("state", "QUEUED"),
            "build_state": "NOT_SCHEDULED",
            "production_activation": "OWNER_APPROVAL_REQUIRED", "created_at": time.time(),
        }
        with self.store._connect() as conn:
            conn.execute("INSERT INTO lab_evolution VALUES(?,?,?)",
                (started["session_id"], observation_id, json.dumps(document, ensure_ascii=False)))
        return {**started, "workflow": WORKFLOW}

    @staticmethod
    def _check_counterexample(source: Path):
        script = (
            "import json,runpy,sys; "
            "fn=runpy.run_path(sys.argv[1])['looks_like_product_criticism']; "
            "print(json.dumps(bool(fn(sys.argv[2]))))"
        )
        process = subprocess.run(
            [sys.executable, "-I", "-c", script, str(source), COUNTEREXAMPLE],
            capture_output=True, text=True, encoding="utf-8", timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        try:
            observed = json.loads(process.stdout)
        except (ValueError, TypeError):
            return {"conclusive": False, "exit_code": process.returncode}
        return {
            "conclusive": process.returncode == 0 and isinstance(observed, bool),
            "input": COUNTEREXAMPLE, "expected": False, "observed": observed,
            "exit_code": process.returncode,
        }

    def observe_and_plan(self, *, inventory=None):
        self._record_unsupported_gaps()
        inventory = inventory if inventory is not None else self.observe_local()
        relative = DEFAULT_SOURCE
        source = self.workspace / relative
        if source.is_file():
            source_fact = next((item for item in inventory if item["source_path"] == relative),
                               {"source_path": relative, "source_sha256": _digest_bytes(source.read_bytes())})
            behavior_id = self._observation_id("BEHAVIORAL_COUNTEREXAMPLE", [source_fact])
            observation = self.checker(source)
            if (observation.get("conclusive")
                    and observation.get("observed") != observation.get("expected")
                    and not self._already_observed(behavior_id)):
                evidence = {"observation_kind": "BEHAVIORAL_COUNTEREXAMPLE",
                    "source_path": relative, "source_sha256": source_fact["source_sha256"],
                    "behavioral_counterexample": observation,
                    "observer": "provider_free_deterministic", "source_inventory": inventory,
                    "capability_gaps": self._capability_gap_evidence()}
                objective = ("Melhore o código-fonte no sandbox para corrigir o contraexemplo observado em "
                    f"{relative}. Preserve comportamentos válidos, execute testes focados e faça revisão "
                    "independente. Não altere nem promova o source de produção.")
                return self._dispatch(observation_id=behavior_id, objective=objective,
                    evidence=evidence, sources=[source_fact], observation=observation)

        gaps = self._capability_gap_evidence()
        runtime_sources, runtime_gaps = self._runtime_gap_sources(inventory, gaps)
        if runtime_sources:
            runtime_id = self._observation_id(
                "RUNTIME_CAPABILITY_FAILURE", {"sources": runtime_sources, "gaps": runtime_gaps})
            if not self._already_observed(runtime_id):
                paths = [item["source_path"] for item in runtime_sources]
                evidence = {"observation_kind": "RUNTIME_CAPABILITY_FAILURE",
                    "sources": runtime_sources, "capability_gaps": runtime_gaps,
                    "observer": "factual_runtime_failure_inbox"}
                objective = ("Investigue como arquiteto estas falhas factuais do runtime no sandbox, "
                    "limitando a mudança aos executores observados: " + ", ".join(paths) + ". Preserve "
                    "comportamentos válidos, execute testes focados e revisão independente. Não presuma "
                    "que a capacidade foi implementada, e não altere nem promova produção.")
                return self._dispatch(observation_id=runtime_id, objective=objective,
                    evidence=evidence, sources=runtime_sources,
                    observation={"kind": "RUNTIME_CAPABILITY_FAILURE", "bug_asserted": True})

        inspection_gaps = [gap for gap in gaps
                           if not gap["required"].startswith("runtime.action.")]
        for sources in self._inspection_batches(inventory):
            inspection_id = self._observation_id(
                "SOURCE_INSPECTION", {"sources": sources, "capability_gaps": inspection_gaps})
            if self._already_observed(inspection_id):
                continue
            paths = [item["source_path"] for item in sources]
            evidence = {"observation_kind": "SOURCE_INSPECTION", "sources": sources,
                "source_inventory_count": len(inventory), "capability_gaps": inspection_gaps,
                "observer": "provider_free_inventory"}
            objective = ("Inspecione como arquiteto este lote factual de código no sandbox: "
                + ", ".join(paths) + ". Procure somente melhorias justificadas pelo source e pelas lacunas "
                "registradas. Se não houver mudança defensável, conclua sem alteração e registre o motivo. "
                "Não presuma defeito a partir de hashes e não altere nem promova produção.")
            return self._dispatch(observation_id=inspection_id, objective=objective,
                evidence=evidence, sources=sources,
                observation={"kind": "SOURCE_INSPECTION", "bug_asserted": False})
        return {"success": True, "state": "NO_CHANGED_SOURCE_BATCH", "workflow": WORKFLOW}

    def run(self, sid):
        """Continue only current dynamic missions; catalog missions are retired."""
        doc = self.snapshot(sid)
        if not doc:
            raise ValueError("Unknown evolution mission")
        if doc.get("workflow") != WORKFLOW or doc.get("mission_kind") != "SELF_IMPROVEMENT":
            return {"success": False, **doc, "state": "LEGACY_RETIRED",
                "build_state": "NOT_SCHEDULED",
                "production_activation": "OWNER_APPROVAL_REQUIRED"}
        if self.autopilot is None:
            self.autopilot = Autopilot(self.runtime, policy=self.policy)
        result = self.autopilot.run(sid)
        current = self.snapshot(sid) or doc
        current.update(state=result.get("state", "UNKNOWN"), updated_at=time.time())
        with self.store._connect() as conn:
            conn.execute("UPDATE lab_evolution SET document=? WHERE session_id=?",
                (json.dumps(current, ensure_ascii=False), sid))
        return {**result, "evolution": current}

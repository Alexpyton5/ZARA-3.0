import hashlib
import json
import sqlite3

import pytest

from core.lab_v1.domain import Artifact, Run, RunState
from core.lab_v1.store import LabStore
from core.lab_v1.review_evidence_packet import (
    ReviewEvidencePacketError,
    _bound_response_run,
    validate_persisted_review_evidence_packet,
)


class ArtifactStore:
    def __init__(self, artifact):
        self.artifact = artifact

    def list_artifacts(self, _session_id):
        return [self.artifact]


def packet_artifact(*, session_id="session", attempt_id="attempt"):
    packet = {"version": 1, "packet_id": "packet:1", "session_id": session_id,
              "review_attempt_id": attempt_id, "diff": {"content": "sentinel"}}
    canonical = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    envelope = json.dumps({"packet": packet, "packet_sha256": digest}, ensure_ascii=False,
                          sort_keys=True, separators=(",", ":"))
    return Artifact("packet:1", session_id, "session:review", "REVIEW_EVIDENCE_PACKET",
                    "packet", body=envelope), digest


def test_persisted_packet_rejects_tamper_other_session_and_stale_attempt():
    artifact, digest = packet_artifact()
    assert validate_persisted_review_evidence_packet(
        ArtifactStore(artifact), session_id="session", packet_id="packet:1",
        packet_sha256=digest, review_attempt_id="attempt")["diff"]["content"] == "sentinel"

    artifact.body = artifact.body.replace("sentinel", "tampered")
    with pytest.raises(ReviewEvidencePacketError, match="TAMPERED_OR_STALE"):
        validate_persisted_review_evidence_packet(
            ArtifactStore(artifact), session_id="session", packet_id="packet:1",
            packet_sha256=digest, review_attempt_id="attempt")

    artifact, digest = packet_artifact()
    with pytest.raises(ReviewEvidencePacketError, match="NOT_FOUND"):
        validate_persisted_review_evidence_packet(
            ArtifactStore(artifact), session_id="other", packet_id="packet:1",
            packet_sha256=digest, review_attempt_id="attempt")
    with pytest.raises(ReviewEvidencePacketError, match="TAMPERED_OR_STALE"):
        validate_persisted_review_evidence_packet(
            ArtifactStore(artifact), session_id="session", packet_id="packet:1",
            packet_sha256=digest, review_attempt_id="stale")


class BoundRunStore:
    def __init__(self, runs):
        self.runs = {run.id: run for run in runs}

    def get_run(self, run_id):
        return self.runs.get(run_id)

    def list_runs(self, _session_id):
        raise AssertionError("resolver must not infer the binding from the newest Run")


def response_binding(*, attempt_id="attempt", run_id="run:bound"):
    response = Artifact("response:" + attempt_id, "session", "task", "MODEL_TEXT",
                        "response", body="exact response")
    payload = {
        "version": 1,
        "session_id": "session",
        "task_id": "task",
        "attempt_id": attempt_id,
        "run_id": run_id,
        "artifact_id": response.id,
        "artifact_sha256": hashlib.sha256(response.body.encode("utf-8")).hexdigest(),
    }
    binding = Artifact("MODEL_RESPONSE_BINDING:" + attempt_id, "session", "task",
                       "MODEL_RESPONSE_BINDING", "binding",
                       body=json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return response, binding


def test_response_resolver_uses_exact_attempt_binding_despite_wrong_newer_run():
    response, binding = response_binding()
    bound = Run("run:bound", "session", "builder", "provider", "model",
                model_reported="model", state=RunState.COMPLETED, task_id="task", started_at=1)
    wrong_newer = Run("run:newer", "session", "builder", "other-provider", "other-model",
                      model_reported="other-model", state=RunState.COMPLETED,
                      task_id="task", started_at=2)
    resolved = _bound_response_run(
        BoundRunStore([bound, wrong_newer]), {response.id: response, binding.id: binding},
        session_id="session", task_id="task", attempt_id="attempt", response=response)
    assert resolved.id == "run:bound"


def test_response_resolver_rejects_stale_attempt_and_missing_legacy_binding():
    response, binding = response_binding()
    run = Run("run:bound", "session", "builder", "provider", "model",
              model_reported="model", state=RunState.COMPLETED, task_id="task")
    store = BoundRunStore([run])

    stale = json.loads(binding.body)
    stale["attempt_id"] = "older-attempt"
    binding.body = json.dumps(stale, sort_keys=True, separators=(",", ":"))
    with pytest.raises(ReviewEvidencePacketError, match="RESPONSE_RUN_BINDING_MISMATCH"):
        _bound_response_run(
            store, {response.id: response, binding.id: binding}, session_id="session",
            task_id="task", attempt_id="attempt", response=response)

    with pytest.raises(ReviewEvidencePacketError, match="RESPONSE_RUN_BINDING_MISSING"):
        _bound_response_run(
            store, {response.id: response}, session_id="session", task_id="task",
            attempt_id="attempt", response=response)


def test_bound_response_storage_rolls_back_both_rows_if_binding_insert_crashes(tmp_path):
    store = LabStore(tmp_path / "lab.db")
    store.initialize()
    legacy = Artifact("legacy", "session", "task", "MODEL_TEXT", "legacy", body="preserve")
    store.save_artifact(legacy)
    response, binding = response_binding()
    with store._connect() as conn:
        conn.execute("""
            CREATE TRIGGER abort_model_response_binding
            BEFORE INSERT ON artifacts
            WHEN NEW.kind = 'MODEL_RESPONSE_BINDING'
            BEGIN SELECT RAISE(ABORT, 'simulated binding crash'); END
        """)

    with pytest.raises(sqlite3.IntegrityError, match="simulated binding crash"):
        store.save_bound_model_response(response, binding)

    artifacts = store.list_artifacts("session")
    assert [(item.id, item.body) for item in artifacts] == [("legacy", "preserve")]

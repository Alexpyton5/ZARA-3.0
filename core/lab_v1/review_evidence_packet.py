"""Durable, fail-closed evidence handoff for an independent source reviewer."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from core.lab_v1.domain import Artifact


MAX_REVIEW_PACKET_CHARS = 44_000
LOG_EXCERPT_CHARS = 2_000


class ReviewEvidencePacketError(ValueError):
    pass


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _artifact_index(store: Any, session_id: str) -> dict[str, Artifact]:
    artifacts = store.list_artifacts(session_id)
    indexed = {item.id: item for item in artifacts}
    if len(indexed) != len(artifacts):
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_DUPLICATE_ARTIFACT")
    return indexed


def _resolved_artifact(indexed: Mapping[str, Artifact], artifact_id: str, *, session_id: str,
                       task_id: str, kind: str, expected_summary: str | None = None) -> dict[str, Any]:
    artifact = indexed.get(artifact_id)
    if (artifact is None or artifact.session_id != session_id or artifact.task_id != task_id
            or artifact.kind != kind):
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_ARTIFACT_BINDING_MISMATCH")
    if expected_summary is not None and artifact.body != expected_summary:
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_RECEIPT_TAMPERED")
    return {"id": artifact.id, "task_id": artifact.task_id, "kind": artifact.kind,
            "body_sha256": _sha(artifact.body), "body_chars": len(artifact.body)}


def _step(snapshot: Mapping[str, Any], step_id: str) -> Mapping[str, Any]:
    matches = [item for item in snapshot.get("steps", ()) if item.get("id") == step_id]
    if len(matches) != 1:
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_STEP_BINDING_MISMATCH")
    step = matches[0]
    if step.get("status") not in {"DONE", "COMPLETED"} or not isinstance(step.get("receipt"), Mapping):
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_STEP_NOT_VERIFIED")
    return step


def _receipt(indexed: Mapping[str, Artifact], snapshot: Mapping[str, Any], step_id: str,
             *, session_id: str, kind: str) -> tuple[Mapping[str, Any], dict[str, Any], Artifact]:
    step = _step(snapshot, step_id)
    raw = step["receipt"]
    artifact_id, summary = raw.get("artifact_ref"), raw.get("summary")
    if not isinstance(artifact_id, str) or not isinstance(summary, str):
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_RECEIPT_INVALID")
    ref = _resolved_artifact(indexed, artifact_id, session_id=session_id,
                             task_id=step["task_id"], kind=kind, expected_summary=summary)
    return step, ref, indexed[artifact_id]


def _bound_response_run(store: Any, indexed: Mapping[str, Artifact], *, session_id: str,
                        task_id: str, attempt_id: str, response: Artifact) -> Any:
    binding_id = "MODEL_RESPONSE_BINDING:" + attempt_id
    binding_artifact = indexed.get(binding_id)
    if binding_artifact is None:
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_RESPONSE_RUN_BINDING_MISSING")
    if (binding_artifact.session_id != session_id or binding_artifact.task_id != task_id
            or binding_artifact.kind != "MODEL_RESPONSE_BINDING"):
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_RESPONSE_RUN_BINDING_MISMATCH")
    try:
        binding = json.loads(binding_artifact.body)
    except (TypeError, ValueError) as exc:
        raise ReviewEvidencePacketError(
            "REVIEW_EVIDENCE_PACKET_RESPONSE_RUN_BINDING_INVALID") from exc
    expected = {
        "version": 1,
        "session_id": session_id,
        "task_id": task_id,
        "attempt_id": attempt_id,
        "artifact_id": response.id,
        "artifact_sha256": _sha(response.body),
    }
    if any(binding.get(key) != value for key, value in expected.items()):
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_RESPONSE_RUN_BINDING_MISMATCH")
    run_id = binding.get("run_id")
    if not isinstance(run_id, str) or not run_id:
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_RESPONSE_RUN_BINDING_INVALID")
    run = store.get_run(run_id)
    if (run is None or run.id != run_id or run.session_id != session_id
            or run.task_id != task_id or run.state.value != "COMPLETED"):
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_BUILDER_RUN_MISMATCH")
    return run


def _test_view(body: str, artifact_ref: Mapping[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(body)
        result: dict[str, Any] = {
            "artifact": dict(artifact_ref),
            "source_hashes": value["source_hashes"],
            "executed_test_paths": value["executed_test_paths"],
            "preservation": value["preservation"],
            "preservation_receipt_id": value["preservation_receipt_id"],
        }
        for label in ("baseline", "candidate"):
            run = value[label]
            result[label] = {key: run[key] for key in
                             ("exit_code", "timed_out", "baseline", "counts", "test_hashes")}
            for stream in ("stdout", "stderr"):
                text = str(run.get(stream, ""))
                result[label][stream + "_artifact"] = {
                    "artifact_id": artifact_ref["id"], "json_field": f"{label}.{stream}",
                    "sha256": _sha(text), "chars": len(text),
                    "excerpt": text[-LOG_EXCERPT_CHARS:], "excerpt_policy": "TAIL_EXPLICIT_LIMIT_2000",
                }
        return result
    except (KeyError, TypeError, ValueError) as exc:
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_TEST_RECEIPT_INVALID") from exc


def build_review_evidence_packet(*, store: Any, controller: Any, session_id: str,
                                 review_attempt_id: str, patch_step_id: str,
                                 test_step_id: str, review_task_id: str,
                                 change_evidence: Mapping[str, Any],
                                 review_preservation_id: str,
                                 source_identity: Mapping[str, str | None],
                                 candidate_identity: Mapping[str, str]) -> tuple[dict[str, Any], str]:
    """Resolve persisted Runs/receipts and return a bounded reviewer packet and hash."""
    snapshot = controller.snapshot(session_id)
    indexed = _artifact_index(store, session_id)
    session = store.get_session(session_id)
    plan_task = store.get_task(session_id + ":plan")
    review_task = store.get_task(review_task_id)
    if session is None or plan_task is None or review_task is None:
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_TASK_BINDING_MISMATCH")

    draft, draft_ref, draft_artifact = _receipt(
        indexed, snapshot, patch_step_id, session_id=session_id, kind="MODEL_TEXT")
    apply, diff_ref, diff_artifact = _receipt(
        indexed, snapshot, patch_step_id.replace(":draft", ":apply"),
        session_id=session_id, kind="SOURCE_DIFF")
    tests, tests_ref, tests_artifact = _receipt(
        indexed, snapshot, test_step_id, session_id=session_id, kind="REAL_TESTS")

    builder_run = _bound_response_run(
        store, indexed, session_id=session_id, task_id=draft["task_id"],
        attempt_id=draft["attempt_id"], response=draft_artifact)
    if builder_run.agent_id != store.get_task(draft["task_id"]).assigned_agent_id:
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_BUILDER_RUN_MISMATCH")
    if draft_artifact.id != "response:" + draft["attempt_id"]:
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_STALE_BUILDER_ATTEMPT")

    try:
        persisted_diff = json.loads(diff_artifact.body)
    except (TypeError, ValueError) as exc:
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_DIFF_INVALID") from exc
    if persisted_diff != dict(change_evidence) or not isinstance(persisted_diff.get("diff"), str):
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_DIFF_TAMPERED")

    test_payload = json.loads(tests_artifact.body)
    preservation_id = test_payload.get("preservation_receipt_id")
    preservation_ref = _resolved_artifact(indexed, preservation_id, session_id=session_id,
        task_id=tests["task_id"], kind="LOCAL_PRESERVATION")
    review_preservation_ref = _resolved_artifact(indexed, review_preservation_id,
        session_id=session_id, task_id=review_task_id, kind="LOCAL_PRESERVATION")

    changed_after = {path: hashes.get("after_sha256") for path, hashes in persisted_diff["hashes"].items()}
    if any(candidate_identity.get(path) != digest for path, digest in changed_after.items()):
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_CANDIDATE_IDENTITY_MISMATCH")
    packet_id = "REVIEW_EVIDENCE_PACKET:" + review_attempt_id
    packet = {
        "version": 1, "packet_id": packet_id, "session_id": session_id,
        "review_attempt_id": review_attempt_id,
        "objective": session.objective, "acceptance": review_task.acceptance,
        "plan_version": snapshot.get("plan_version"),
        "source_identity": dict(source_identity), "candidate_identity": dict(candidate_identity),
        "builder": {"run": builder_run.to_dict(), "response": draft_ref},
        "diff": {"artifact": diff_ref, "content": persisted_diff["diff"],
                 "hashes": persisted_diff["hashes"], "files_changed": persisted_diff["files_changed"],
                 "lines_added": persisted_diff["lines_added"], "lines_deleted": persisted_diff["lines_deleted"]},
        "tests": _test_view(tests_artifact.body, tests_ref),
        "receipts": {"builder_response": draft_ref, "source_diff": diff_ref,
                     "real_tests": tests_ref, "preservation_after_tests": preservation_ref,
                     "preservation_before_review": review_preservation_ref},
        "limitations": ["SOURCE_AND_TEST_EVIDENCE_ONLY", "NO_PACKAGED_OR_PHYSICAL_PROOF",
                        "TEST_LOGS_EXCERPTED_WITH_FULL_ARTIFACT_REFERENCE"],
    }
    serialized = _json(packet)
    if len(serialized) > MAX_REVIEW_PACKET_CHARS:
        raise ReviewEvidencePacketError(
            f"REVIEW_EVIDENCE_PACKET_TOO_LARGE:{len(serialized)}>{MAX_REVIEW_PACKET_CHARS}")
    return packet, _sha(serialized)


def persist_review_evidence_packet(store: Any, *, session_id: str, task_id: str,
                                   packet: Mapping[str, Any], packet_sha256: str) -> Artifact:
    envelope = {"packet": dict(packet), "packet_sha256": packet_sha256}
    artifact = Artifact(packet["packet_id"], session_id, task_id, "REVIEW_EVIDENCE_PACKET",
                        "Resolved reviewer evidence", body=_json(envelope))
    store.save_artifact(artifact)
    return artifact


def validate_persisted_review_evidence_packet(store: Any, *, session_id: str,
                                              packet_id: str, packet_sha256: str,
                                              review_attempt_id: str) -> dict[str, Any]:
    indexed = _artifact_index(store, session_id)
    artifact = indexed.get(packet_id)
    if artifact is None or artifact.session_id != session_id or artifact.kind != "REVIEW_EVIDENCE_PACKET":
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_NOT_FOUND")
    try:
        envelope = json.loads(artifact.body)
        packet = envelope["packet"]
    except (KeyError, TypeError, ValueError) as exc:
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_INVALID") from exc
    if (envelope.get("packet_sha256") != packet_sha256 or _sha(_json(packet)) != packet_sha256
            or packet.get("packet_id") != packet_id or packet.get("session_id") != session_id
            or packet.get("review_attempt_id") != review_attempt_id):
        raise ReviewEvidencePacketError("REVIEW_EVIDENCE_PACKET_TAMPERED_OR_STALE")
    return packet

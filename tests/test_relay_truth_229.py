"""227/228/229 — relay: ordem, dedupe, recovery e verdade de estado.

Tudo em diretorio isolado (tmp_path). Nenhuma mensagem real, nenhum acesso ao
data dir do Alex, nenhuma chamada de rede.
"""
from __future__ import annotations

import json
import time

import pytest

from core.mentor_relay import MentorRelay


def _write_reply(relay: MentorRelay, relay_id: str, content: str, **extra):
    payload = {
        "schema": 1,
        "relay_id": relay_id,
        "direction": "MENTOR_TO_ZARA",
        "content": content,
        "created_at": time.time(),
    }
    payload.update(extra)
    path = relay.inbox / f"{relay_id}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


@pytest.fixture()
def relay(tmp_path):
    return MentorRelay(root=tmp_path / "mentor-relay")


# ---------------------------------------------------------------- 227 order


def test_replies_are_drained_in_arrival_order(relay):
    for i in range(5):
        _write_reply(relay, f"MR-ORDER-{i}", f"msg{i}")
        time.sleep(0.01)
    drained = relay.drain_replies()
    assert [r["content"] for r in drained] == [f"msg{i}" for i in range(5)]


def test_duplicate_relay_id_is_delivered_once(relay):
    first_path = _write_reply(relay, "MR-DUP-1", "primeira")
    first = relay.drain_replies()
    assert [r["content"] for r in first] == ["primeira"]
    archived = relay.archive / "MR-DUP-1.reply.json"
    first_payload = json.loads(archived.read_text(encoding="utf-8"))

    # A duplicata chega depois com o MESMO id: nao pode reentregar.
    _write_reply(relay, "MR-DUP-1", "primeira")
    second = relay.drain_replies()
    assert second == []
    assert json.loads(archived.read_text(encoding="utf-8")) == first_payload
    assert list(relay.archive.glob("MR-DUP-1.reply.duplicate-*.json"))
    assert not first_path.exists()


def test_out_of_order_ids_do_not_break_delivery(relay):
    for rid in ("MR-9", "MR-1", "MR-5"):
        _write_reply(relay, rid, rid)
        time.sleep(0.01)
    drained = relay.drain_replies()
    assert len(drained) == 3
    assert {r["relay_id"] for r in drained} == {"MR-9", "MR-1", "MR-5"}


def test_invalid_payloads_are_quarantined_not_delivered(relay):
    _write_reply(relay, "MR-BAD-1", "")                                  # vazio
    _write_reply(relay, "MR-BAD-2", "x", direction="ZARA_TO_MENTOR")     # direcao errada
    (relay.inbox / "MR-BAD-3.json").write_text("{not json", encoding="utf-8")
    assert relay.drain_replies() == []
    assert list(relay.inbox.glob("MR-*.json")) == []
    assert len(list(relay.archive.glob("*.invalid-*.json"))) == 3


def test_agent_identity_is_preserved(relay):
    _write_reply(relay, "MR-AG-1", "oi", agent="codex")
    assert relay.drain_replies()[0]["agent"] == "codex"


# ------------------------------------------------------- 228 restart recovery


def test_worker_restart_does_not_reprocess_completed_order(relay, tmp_path):
    _write_reply(relay, "MR-RESTART-1", "ordem A")
    assert len(relay.drain_replies()) == 1

    # "Restart": nova instancia apontando para a mesma raiz.
    fresh = MentorRelay(root=relay.root)
    assert fresh.drain_replies() == []

    # Uma ordem NOVA depois do restart e processada normalmente.
    _write_reply(fresh, "MR-RESTART-2", "ordem B")
    assert [r["content"] for r in fresh.drain_replies()] == ["ordem B"]


def test_outbound_pending_survives_restart(relay):
    relay.enqueue("alex", "mensagem persistente")
    assert relay.pending_count() == 1
    fresh = MentorRelay(root=relay.root)
    assert fresh.pending_count() == 1


# ------------------------------------------------------ 229 state truthfulness


def test_enqueue_starts_pending_not_delivered(relay):
    payload = relay.enqueue("alex", "oi mentor")
    assert payload["status"] == "PENDING"
    assert payload["relay_id"].startswith("MR-")


def test_empty_message_is_rejected(relay):
    with pytest.raises(ValueError):
        relay.enqueue("alex", "   ")


def test_mark_delivered_records_real_delivery(relay):
    payload = relay.enqueue("alex", "entregar")
    relay.mark_outbound_delivered(payload["relay_id"], detail="issue-comment-123")
    assert relay.pending_count() == 0
    archived = json.loads(
        (relay.archive / f"{payload['relay_id']}.request.json").read_text(encoding="utf-8")
    )
    assert archived["status"] == "DELIVERED"
    assert archived["delivery_detail"] == "issue-comment-123"


def test_mark_failed_keeps_message_and_does_not_claim_delivery(relay):
    payload = relay.enqueue("alex", "vai falhar")
    relay.mark_outbound_failed(payload["relay_id"], reason="HTTP 500")
    # A mensagem NAO pode sumir como se tivesse sido entregue.
    assert relay.pending_count() == 1
    stored = json.loads((relay.outbox / f"{payload['relay_id']}.json").read_text(encoding="utf-8"))
    assert stored["status"] == "FAILED"
    assert stored["last_error"] == "HTTP 500"
    assert stored["attempts"] == 1


def test_failed_then_delivered_transitions_correctly(relay):
    payload = relay.enqueue("alex", "retry")
    rid = payload["relay_id"]
    relay.mark_outbound_failed(rid, reason="timeout")
    relay.mark_outbound_failed(rid, reason="timeout")
    stored = json.loads((relay.outbox / f"{rid}.json").read_text(encoding="utf-8"))
    assert stored["attempts"] == 2
    relay.mark_outbound_delivered(rid)
    assert relay.pending_count() == 0


def test_mark_delivered_on_unknown_id_is_not_a_silent_success(relay):
    assert relay.mark_outbound_delivered("MR-DOES-NOT-EXIST") is False


def test_legacy_mark_outbound_processed_still_archives(relay):
    payload = relay.enqueue("alex", "legado")
    relay.mark_outbound_processed(payload["relay_id"])
    assert relay.pending_count() == 0

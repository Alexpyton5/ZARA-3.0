"""MISSAO GIGANTE 3 — FRENTE E, passo E3: a chamada outbound em SIMULACAO.

Nenhum teste aqui disca de verdade: o transporte padrao e o
SimulationTransport, que so registra a tentativa. Ligacao real sem
authorized_by_user=True explicito levanta CallNotAuthorizedError e e
registrada como "blocked" no audit.
"""
from __future__ import annotations

import pytest

from core.outbound_call import (
    CALL_TRIGGERS,
    CallNotAuthorizedError,
    OutboundCallManager,
    SimulationTransport,
)


class _FakeTTS:
    def __init__(self):
        self.spoken: list[str] = []

    def __call__(self, text: str) -> None:
        self.spoken.append(text)


class _FakeAudit:
    def __init__(self):
        self.records: list[tuple] = []

    def record(self, action, risk, outcome, error=None):
        self.records.append((action, risk, outcome, error))


def _manager(**kw):
    tts = _FakeTTS()
    audit = _FakeAudit()
    transport = SimulationTransport()
    mgr = OutboundCallManager(tts_speak=tts, transport=transport, audit=audit, **kw)
    return mgr, tts, audit, transport


def test_e3_gatilhos_documentados():
    """E1: os gatilhos existem e cada um diz quando ela decide ligar."""
    assert set(CALL_TRIGGERS) == {
        "critical_failure", "security_alert", "scheduled_call", "missed_urgent",
    }
    for trigger, regra in CALL_TRIGGERS.items():
        assert isinstance(regra, str) and len(regra) > 20, trigger


def test_e3_gatilho_desconhecido_rejeitado():
    mgr, _, _, _ = _manager()
    with pytest.raises(ValueError):
        mgr.request_call("saudade", "so queria ouvir sua voz")


def test_e3_simulacao_roda_o_fluxo_inteiro():
    """E3: simular = discar (fake) + falar o roteiro com a voz dela + log."""
    mgr, tts, audit, transport = _manager()
    call = mgr.request_call("critical_failure", "O backup falhou duas vezes.")

    result = mgr.place_call(call)  # simulate=True e o padrao

    assert result["ok"] is True
    assert result["simulated"] is True
    assert result["status"] == "simulated"
    assert call.id in transport.dial_attempts
    # O roteiro: ela se apresenta e diz o motivo.
    assert len(tts.spoken) == 1
    roteiro = tts.spoken[0]
    assert "ZARA" in roteiro
    assert "backup falhou" in roteiro
    # Registro no log.
    assert ("outbound_call", "MEDIUM", "simulated", None) in audit.records


def test_e3_ligacao_real_sem_autorizacao_bloqueia():
    """Fail-closed: sem authorized_by_user=True, nao disca e registra."""
    mgr, tts, audit, transport = _manager()
    call = mgr.request_call("security_alert", "Atividade estranha detectada.")

    with pytest.raises(CallNotAuthorizedError):
        mgr.place_call(call, simulate=False)

    assert transport.dial_attempts == [], "discou sem autorizacao!"
    assert tts.spoken == [], "falou o roteiro sem discar!"
    assert call.status == "blocked"
    assert any(r[2] == "blocked" for r in audit.records)


def test_e3_ligacao_real_sem_transporte_real_bloqueia():
    """Mesmo autorizada, sem transporte real configurado nao sai ligacao."""
    mgr, tts, audit, transport = _manager()
    call = mgr.request_call("scheduled_call", "Ele pediu: me liga as 8h.")

    with pytest.raises(CallNotAuthorizedError):
        mgr.place_call(call, simulate=False, authorized_by_user=True)

    assert transport.dial_attempts == []
    assert tts.spoken == []
    assert call.status == "blocked"


def test_e3_falha_do_tts_registra_failed():
    """Se a voz falhar no meio da chamada, o log conta 'failed'."""
    mgr, tts, audit, transport = _manager()

    def tts_quebrado(texto):
        raise RuntimeError("sem voz agora")

    mgr._tts_speak = tts_quebrado
    call = mgr.request_call("missed_urgent", "Mensagem urgente nao lida.")

    with pytest.raises(RuntimeError):
        mgr.place_call(call)

    assert call.status == "failed"
    assert any(r[2] == "failed" for r in audit.records)

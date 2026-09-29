"""ZARA-OUTBOUND-CALL-001 (MISSAO GIGANTE 3, frente E): ela pode LIGAR pra ele.

E1. FLUXO DA CHAMADA OUTBOUND
-----------------------------
1. GATILHO -- algo decide que vale ligar. So gatilhos da allowlist
   CALL_TRIGGERS abaixo; qualquer outro motivo e rejeitado na hora.
2. ROTEIRO -- monta o texto que ela fala ao atender: pt-BR simples, ela se
   apresenta ("Oi, aqui e a ZARA."), diz o motivo em uma frase e encerra.
3. DISCAR -- via CallTransport. O padrao e SimulationTransport: NAO disca
   nada real, so registra a tentativa. Transporte real exige DUAS coisas
   juntas: `authorized_by_user=True` EXPLICITO + um transporte real
   configurado. Sem isso, fail-closed: levanta CallNotAuthorizedError e
   registra "blocked" no audit. Nenhuma ligacao real sai sem ele pedir.
4. FALAR -- o roteiro vai para a voz dela (TTSManager em cascata Kore ->
   OmniVoice -> Edge -> Kokoro; injetavel para testes).
5. REGISTRAR -- toda tentativa cai no audit_log: outbound_call / MEDIUM /
   outcome (simulated | completed | blocked | failed).

COMO DISCA (transporte real, desenho futuro -- NAO implementado aqui):
opcoes sao chamada de WhatsApp via zoeBridge (use computer: abrir a conversa
do Alex e clicar no botao de chamada, mantendo a trava fail-closed) ou uma
integracao de telefonia dedicada. E3 exige SIMULACAO, e discar de verdade no
meio da noite sem ele pedir e proibido pela propria missao; por isso o
transporte real fica como desenho, nao como codigo.

E2. GATILHO + CHAMADA + LOG: OutboundCallManager abaixo.
E3. SIMULACAO: tests/test_outbound_call.py roda o fluxo inteiro sem tocar
em telefonia de verdade.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Protocol

# E1. GATILHOS DOCUMENTADOS -- quando ela decide ligar.
# Cada chave e um motivo permitido; o texto explica a regra de decisao.
CALL_TRIGGERS: dict[str, str] = {
    "critical_failure": (
        "Algo critico quebrou e ele precisa saber AGORA (ex.: processo vital "
        "do PC morreu, backup falhou, a ZARA perdeu a voz). So liga se o "
        "problema impede o trabalho dele e nao ha outro canal mais rapido."
    ),
    "security_alert": (
        "Alerta de seguranca que exige atencao imediata dele (ex.: atividade "
        "estranha detectada). Nunca liga por suspeita fraca: so com evidencia."
    ),
    "scheduled_call": (
        "Ele pediu explicitamente: 'me liga as 8h' / 'me acorda ligando'. "
        "E o unico gatilho que nao depende de juizo dela -- foi ordem direta."
    ),
    "missed_urgent": (
        "Mensagem marcada como urgente nao lida ha muito tempo e o assunto "
        "nao pode esperar ele abrir o app. Ultimo recurso, nao rotina."
    ),
}


class CallNotAuthorizedError(RuntimeError):
    """Levantado quando ha tentativa de ligacao real sem autorizacao explicita."""


@dataclass
class OutboundCall:
    """Uma chamada pedida pela ZARA, antes de discar."""

    id: str
    trigger: str
    detail: str
    script: str
    created_at: float
    status: str = "requested"
    transport_name: str = "simulation"
    authorized_by_user: bool = False


class CallTransport(Protocol):
    """Como a chamada chega ate o telefone dele. O padrao e simulacao."""

    name: str

    def dial(self, call: OutboundCall) -> dict:
        """Disca. Retorna {"ok": bool, ...}."""
        ...

    def hangup(self, call: OutboundCall) -> None:
        ...


class SimulationTransport:
    """Transporte padrao: registra a tentativa, nunca toca em telefonia."""

    name = "simulation"

    def __init__(self) -> None:
        self.dial_attempts: list[str] = []

    def dial(self, call: OutboundCall) -> dict:
        self.dial_attempts.append(call.id)
        return {"ok": True, "simulated": True, "transport": self.name}

    def hangup(self, call: OutboundCall) -> None:
        return None


def _build_script(trigger: str, detail: str) -> str:
    """O que ela fala ao atender: se apresenta, motivo em uma frase, encerra."""
    detalhe = f" {detail.strip()}" if detail and detail.strip() else ""
    base = {
        "critical_failure": (
            f"Oi, aqui e a ZARA.{detalhe} Precisei te ligar porque e urgente. "
            "Me chama quando puder."
        ),
        "security_alert": (
            f"Oi, aqui e a ZARA.{detalhe} Achei melhor te avisar por ligacao. "
            "Da uma olhada quando puder."
        ),
        "scheduled_call": (
            f"Oi, aqui e a ZARA.{detalhe} Voce pediu pra eu te ligar agora. "
            "Estou por aqui."
        ),
        "missed_urgent": (
            f"Oi, aqui e a ZARA.{detalhe} E urgente e voce ainda nao viu. "
            "Me responde quando puder."
        ),
    }
    return base[trigger]


def _default_tts_speak(text: str) -> None:
    """Fala o roteiro com a voz dela (cascata de TTS do app)."""
    from core.voice_tts import TTSConfig, TTSManager

    manager = TTSManager(TTSConfig())
    manager.initialize()
    try:
        manager.speak(text, blocking=True)
    finally:
        manager.cleanup()


class OutboundCallManager:
    """Gatilho + chamada + registro. Fail-closed por construcao."""

    def __init__(
        self,
        *,
        tts_speak: Callable[[str], None] | None = None,
        transport: CallTransport | None = None,
        audit=None,
    ) -> None:
        self._tts_speak = tts_speak or _default_tts_speak
        self._transport = transport or SimulationTransport()
        self._audit = audit
        self.calls: list[OutboundCall] = []

    def _audit_log(self):
        if self._audit is not None:
            return self._audit
        from core.audit_log import audit_log

        return audit_log()

    def request_call(self, trigger: str, detail: str = "") -> OutboundCall:
        """E2a. Registra a intencao de ligar. Gatilho fora da allowlist = erro."""
        if trigger not in CALL_TRIGGERS:
            raise ValueError(f"Gatilho de ligacao desconhecido: {trigger!r}")
        call = OutboundCall(
            id=uuid.uuid4().hex[:12],
            trigger=trigger,
            detail=str(detail or "")[:500],
            script=_build_script(trigger, detail),
            created_at=time.time(),
            transport_name=self._transport.name,
        )
        self.calls.append(call)
        return call

    def place_call(
        self, call: OutboundCall, *, authorized_by_user: bool = False, simulate: bool = True
    ) -> dict:
        """E2b. Executa a chamada.

        - simulate=True (padrao): roda o fluxo inteiro sem telefonia real.
        - simulate=False exige authorized_by_user=True E um transporte real;
          sem isso, bloqueia, registra e levanta CallNotAuthorizedError.
        """
        if call.trigger not in CALL_TRIGGERS:
            raise ValueError(f"Gatilho de ligacao desconhecido: {call.trigger!r}")

        real = not simulate
        if real and not authorized_by_user:
            call.status = "blocked"
            self._audit_log().record("outbound_call", "MEDIUM", "blocked",
                                     "ligacao real sem autorizacao explicita")
            raise CallNotAuthorizedError(
                "Ligacao real bloqueada: exige authorized_by_user=True explicito."
            )
        if real and isinstance(self._transport, SimulationTransport):
            call.status = "blocked"
            self._audit_log().record("outbound_call", "MEDIUM", "blocked",
                                     "nenhum transporte real configurado")
            raise CallNotAuthorizedError(
                "Ligacao real bloqueada: nenhum transporte real configurado."
            )

        call.authorized_by_user = authorized_by_user and real
        try:
            dial_result = self._transport.dial(call)
            if not dial_result.get("ok"):
                raise RuntimeError(f"Transporte falhou: {dial_result}")
            # Ela fala o roteiro com a voz dela assim que "atendem".
            self._tts_speak(call.script)
            try:
                self._transport.hangup(call)
            except Exception:
                pass
            call.status = "simulated" if simulate else "completed"
            self._audit_log().record("outbound_call", "MEDIUM", call.status, None)
            return {
                "ok": True,
                "call_id": call.id,
                "trigger": call.trigger,
                "status": call.status,
                "transport": self._transport.name,
                "simulated": simulate,
            }
        except CallNotAuthorizedError:
            raise
        except Exception as exc:
            call.status = "failed"
            self._audit_log().record("outbound_call", "MEDIUM", "failed", str(exc)[:200])
            raise


__all__ = [
    "CALL_TRIGGERS",
    "CallNotAuthorizedError",
    "CallTransport",
    "OutboundCall",
    "OutboundCallManager",
    "SimulationTransport",
]

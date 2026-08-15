"""ZARA-APRENDIZADO-001 — Alex podendo ver o que ela aprendeu.

Sem isto o aprendizado vira caixa preta que só cresce. Ele precisa poder olhar
dentro: sem olhar não há como corrigir, e uma memória que ninguém revisa acaba
operando com base em besteira.

Uma ação só, de leitura. Apagar lição é decisão dele e vai pelo painel — não por
voz, porque "esquece isso" dito no meio de uma frase é ambíguo demais para
mexer em memória.
"""
from __future__ import annotations

from core.action_registry import ActionResult, action


@action(
    name="aprendizado_resumo",
    category="system",
    description="Conta o que a ZARA aprendeu com o uso",
    capability="LOCAL_PC_CONTROL",
)
def aprendizado_resumo_action(periodo: str = "hoje") -> ActionResult:
    try:
        from core.aprendizado import Aprendizado

        diario = Aprendizado()
        horas = 24.0 if periodo == "hoje" else 24.0 * 7
        frase = diario.contar_o_que_aprendeu(desde_horas=horas)
        resumo = diario.resumo_do_dia(desde_horas=horas)
    except Exception as exc:
        return ActionResult(
            success=False,
            error=f"Não consegui abrir meu diário de aprendizado: {exc}",
        )

    return ActionResult(success=True, output=frase, data=resumo)

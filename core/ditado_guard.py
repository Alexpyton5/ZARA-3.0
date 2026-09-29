"""Item 17 do backlog (PESQUISA-CONCORRENTES.md): guard anti-alucinação no ditado.

Regra de ouro: a IA nunca reescreve o que o Alex não disse.

Antes de colar qualquer reescrita por IA do transcript (tirar "uh", pôr
pontuação, formatar), mede-se a similaridade entre o texto CRU (o que o STT
ouviu) e o texto LIMPO (o que a IA produziu). Se a limpeza se afastar demais
— threshold configurável, padrão 0.80 — usa-se o transcript cru. Reescrita
que inventa palavra é quebra de confiança; aqui ela nunca chega à tela.

Funções puras: sem I/O, sem rede, sem modelo. Testáveis sem hardware.

Ponto de plugue (quando o modo ditado — item 1 do backlog — existir):
    resultado = aplicar_limpeza_com_guard(transcript_cru, ia_limpar_texto)
    colar_no_cursor(resultado.final)

A similaridade é por tokens (Jaccard sobre multiset de palavras
normalizadas): ignora caixa, pontuação e ordem — ou seja, a limpeza legítima
("uh eu quero abrir o excel" -> "Eu quero abrir o Excel.") passa com folga —
mas qualquer palavra inventada OU cortada derruba a nota (tirar um "não"
inverte o sentido, e isso também cai no fallback).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Callable


#: Threshold padrão: abaixo disso, o texto limpo é descartado e o cru vence.
THRESHOLD_PADRAO = 0.80

_PONTUACAO_RE = re.compile(r"[^\w\s]", re.UNICODE)
_ESPACOS_RE = re.compile(r"\s+")


def normalizar_para_comparar(texto: str | None) -> str:
    """Minúsculas, sem pontuação, espaços colapsados. Só serve p/ comparar."""
    texto = (texto or "").casefold()
    texto = _PONTUACAO_RE.sub(" ", texto)
    return _ESPACOS_RE.sub(" ", texto).strip()


def similaridade_transcricao(crua: str | None, limpa: str | None) -> float:
    """Similaridade 0..1 entre o que foi dito e a reescrita, por tokens.

    Jaccard sobre multiset (Counter) de palavras normalizadas:
    interseção/união das contagens. 1.0 = mesmos tokens (ignorando caixa,
    pontuação e ordem); 0.0 = nada em comum.

    Por que Jaccard e não edição/sequência: a limpeza legítima remove
    fillers ("uh"), põe pontuação e reordena um pouco — tudo isso mantém o
    Jaccard alto — enquanto invenção ("e o balanço anual") ou corte que muda
    o sentido (tirar o "não") derrubam a nota. É exatamente a linha que o
    guard precisa patrulhar.
    """
    contagem_crua = Counter(normalizar_para_comparar(crua).split())
    contagem_limpa = Counter(normalizar_para_comparar(limpa).split())
    if not contagem_crua and not contagem_limpa:
        return 1.0
    if not contagem_crua or not contagem_limpa:
        return 0.0
    intersecao = sum(
        min(contagem_crua[token], contagem_limpa[token]) for token in contagem_crua
    )
    uniao = sum(
        max(contagem_crua[token], contagem_limpa.get(token, 0)) for token in contagem_crua
    ) + sum(
        contagem_limpa[token] for token in contagem_limpa if token not in contagem_crua
    )
    return intersecao / uniao if uniao else 1.0


@dataclass(frozen=True)
class ResultadoGuard:
    """O veredito do guard."""

    final: str        #: texto que deve ser usado (limpo ou cru)
    usou_cru: bool    #: True = a reescrita foi descartada (fallback)
    similaridade: float  #: 0..1 medido entre cru e limpo
    motivo: str       #: "ok" | "identico" | "limpeza_vazia" | "limpeza_falhou"
                      #: | "abaixo_do_threshold"


def guard_transcript(
    raw: str | None,
    cleaned: str | None,
    *,
    threshold: float = THRESHOLD_PADRAO,
) -> ResultadoGuard:
    """Passada de similaridade antes de aceitar a reescrita por IA.

    - limpeza vazia -> usa o cru (nunca cola string vazia);
    - similaridade < threshold -> usa o cru (a IA inventou ou cortou demais);
    - senão -> usa o limpo.
    """
    cru = raw or ""
    limpo = (cleaned or "").strip()
    if not limpo:
        return ResultadoGuard(
            final=cru, usou_cru=True, similaridade=0.0, motivo="limpeza_vazia"
        )
    if normalizar_para_comparar(cru) == normalizar_para_comparar(limpo):
        return ResultadoGuard(
            final=limpo, usou_cru=False, similaridade=1.0, motivo="identico"
        )
    sim = similaridade_transcricao(cru, limpo)
    if sim < threshold:
        return ResultadoGuard(
            final=cru, usou_cru=True, similaridade=sim, motivo="abaixo_do_threshold"
        )
    return ResultadoGuard(final=limpo, usou_cru=False, similaridade=sim, motivo="ok")


def aplicar_limpeza_com_guard(
    raw: str | None,
    limpar_fn: Callable[[str], str | None] | None,
    *,
    threshold: float = THRESHOLD_PADRAO,
) -> ResultadoGuard:
    """Aplica a limpeza por IA e passa pelo guard. Falha segura: se a IA
    levantar exceção, o transcript cru vence (motivo "limpeza_falhou")."""
    try:
        limpo = limpar_fn(raw or "") if limpar_fn is not None else None
    except Exception:  # noqa: BLE001 - IA quebrou: o cru continua valendo
        return ResultadoGuard(
            final=raw or "", usou_cru=True, similaridade=0.0, motivo="limpeza_falhou"
        )
    return guard_transcript(raw, limpo, threshold=threshold)

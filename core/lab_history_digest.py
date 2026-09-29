"""Resumo do Lab -> fio unificado (CONVERSA-UNICA, passo 2).

A missao "uma conversa so" diz: o Lab continua com a sala dele (a conversa
de trabalho dos agentes), mas o Alex ve no fio principal UM RESUMO do que
o Lab decidiu. Esta e a peca de traducao: pega o boletim do ciclo
(`lab_cycle_brief.boletim_de_ciclos`, que ja passou no portao do modo
silencioso) ou um relatorio de agente (`lab_report.Relatorio`) e devolve
um turno pronto para `ConversationHistory.append(role, content, engine=...)`.

Regras:
- engine SEMPRE "lab-resumo" (origem honesta: o Alex sabe que e resumo
  do Lab, nao conversa dele).
- Nunca inventa conteudo: o turno carrega so o boletim/relatorio recebido.
- Teto de fio: o fio nao e relatorio — o resumo e enxutado p/ no maximo
  12 linhas antes de entrar (o modo silencioso pede 10; o fio pede legivel).
- Prioridade no enxugamento: cabecalho + FEITO + DECISAO PEDIDA nunca
  saem; ESTADO/ERRO/SUGESTAO entram no que couber. Nada e reescrito, so
  reordenado — e a ultima linha diz quantas linhas ficaram de fora.
- Idempotente: `assinatura()` marca o boletim; o chamador guarda as
  assinaturas vistas e o mesmo ciclo nunca vira 2 turnos.
- Relatorio que nao passa no portao do modo silencioso NAO entra no fio.
- Logica pura, stdlib, zero custo/rede/quota.
"""

from __future__ import annotations

import hashlib
from typing import Any

ENGINE_LAB_RESUMO = "lab-resumo"

# O fio pede legivel; o modo silencioso pede 10. 12 e o meio honesto.
MAX_LINHAS_FIO = 12

_BLOCOS = ("FEITO:", "ESTADO:", "ERRO:", "SUGESTÃO:", "SUGESTAO:")


def assinatura(brief_text: Any) -> str:
    """Assinatura estavel do boletim (p/ o chamador guardar em `vistos`).

    Fluxo: sig = assinatura(texto); se sig nao esta em vistos:
    turno = digest_brief_text(texto); history.append(turno[0], turno[1], engine=turno[2]); vistos.add(sig).
    """
    normalizado = str(brief_text or "").replace("\r\n", "\n").strip()
    return hashlib.sha256(normalizado.encode("utf-8")).hexdigest()


def digest_brief_text(brief_text: Any, *, max_linhas: int = MAX_LINHAS_FIO):
    """Turno ("assistant", resumo, "lab-resumo") a partir do texto do boletim.

    Texto vazio ou invalido -> None. Texto longo -> enxutado no teto,
    com cabecalho + FEITO + DECISAO PEDIDA sempre preservados.
    """
    if not isinstance(brief_text, str):
        return None
    enxuto = _enxugar(brief_text, max_linhas=max_linhas)
    if not enxuto:
        return None
    return ("assistant", enxuto, ENGINE_LAB_RESUMO)


def digest_relatorio(relatorio: Any, *, max_linhas: int = MAX_LINHAS_FIO):
    """Turno a partir de um `lab_report.Relatorio` (duck-typing).

    Relatorio que nao passa no portao do modo silencioso -> None
    (o fio nao recebe o que o protocolo vetaria). Erro de formatacao
    -> None (fail closed, nada entra pela metade).
    """
    formatar = getattr(relatorio, "formatar", None)
    pode_falar = getattr(relatorio, "pode_falar", None)
    if not callable(formatar) or not callable(pode_falar):
        return None
    try:
        if not pode_falar():
            return None
        texto = formatar()
    except Exception:
        return None
    return digest_brief_text(texto, max_linhas=max_linhas)


def _enxugar(texto: str, *, max_linhas: int) -> str:
    linhas = [ln for ln in texto.replace("\r\n", "\n").split("\n")]
    linhas = [ln for ln in linhas if ln.strip()]
    if not linhas:
        return ""

    cabecalho, blocos, decisao = _separar(linhas)

    if not blocos and decisao is None:
        # Texto opaco (nao e boletim formatado): nao inventa bloco,
        # so marca a origem e corta no teto.
        conteudo = linhas[: max_linhas - 1]
        saida = ["RESUMO DO LAB:"] + conteudo
        if len(linhas) > len(conteudo):
            saida.append("(+%d linhas no boletim completo)"
                         % (len(linhas) - len(conteudo)))
        return "\n".join(saida[:max_linhas])

    # Prioridade: cabecalho + FEITO + DECISAO PEDIDA sao fixas (nunca
    # saem); ESTADO/ERRO/SUGESTAO entram no que couber do teto.
    cabeca = [cabecalho] if cabecalho else []
    feito = _linhas_bloco(blocos, "FEITO:")
    meio: list[str] = []
    for titulo in ("ESTADO:", "ERRO:", "SUGESTÃO:", "SUGESTAO:"):
        meio.extend(_linhas_bloco(blocos, titulo))
    cauda = [decisao] if decisao else []

    fixas = cabeca + feito + cauda
    if len(fixas) + len(meio) <= max_linhas:
        return "\n".join(fixas + meio)

    espaco_meio = max_linhas - len(fixas) - 1  # -1: reserva p/ a nota
    if espaco_meio < 0:
        # Patologico (fora do protocolo): nem as fixas cabem — o teto
        # absoluto vence; nada se perde, o boletim completo existe fora.
        cortadas = len(fixas) + len(meio) - max_linhas + 1
        saida = fixas + ["(+%d linhas no boletim completo)" % cortadas]
        return "\n".join(saida[:max_linhas])

    meio_ok = meio[:espaco_meio]
    cortadas = len(meio) - len(meio_ok)
    saida = fixas + meio_ok + ["(+%d linhas no boletim completo)" % cortadas]
    return "\n".join(saida[:max_linhas])


def _linhas_bloco(blocos, titulo: str) -> list:
    for bloco_titulo, conteudo in blocos:
        if bloco_titulo == titulo:
            return [bloco_titulo] + list(conteudo)
    return []


def _separar(linhas):
    """Separa cabecalho, blocos (titulo + conteudo) e linha de decisao."""
    cabecalho = linhas[0]
    blocos: list[tuple[str, list[str]]] = []
    decisao = None
    atual = None
    for ln in linhas[1:]:
        if ln in _BLOCOS:
            atual = (ln, [])
            blocos.append(atual)
            continue
        if ln.startswith("DECISÃO PEDIDA:") or ln.startswith("DECISAO PEDIDA:"):
            decisao = ln
            atual = None
            continue
        if atual is not None:
            atual[1].append(ln)
        else:
            # Linha solta fora de bloco: gruda no cabecalho, nao some.
            cabecalho = cabecalho + " " + ln.strip()
    return cabecalho, blocos, decisao

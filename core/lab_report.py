"""Protocolo de relatório dos agentes — MODO SILENCIOSO (regra permanente do Alex).

O Lab inteiro trabalha calado. Um agente só FALA em 2 casos:
1. TRAVOU de verdade e precisa de decisão (relatório de bloqueio).
2. FIM DO CICLO (relatório de progresso).

Em ambos os casos o relatório segue o formato FEITO / ESTADO / ERRO / SUGESTÃO,
com no máximo 10 linhas de conteúdo. Este módulo é o portão: valida e monta o
relatório; quem não passa no portão não fala.

Lógica pura, stdlib apenas, sem chamadas de modelo (custo/rede/quota = zero).
Peça da GIGANTE 2 "LAB VIVO" Fase A — alicerce, não integração.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# Máximo de linhas de conteúdo permitido pelo modo silencioso (regra do Alex).
MAX_LINHAS = 10

SECOES = ("FEITO", "ESTADO", "ERRO", "SUGESTÃO")

BLOQUEIO = "BLOQUEIO"
PROGRESSO = "PROGRESSO"
STATUS = "STATUS"

TIPOS = (BLOQUEIO, PROGRESSO, STATUS)


@dataclass
class Relatorio:
    """Um relatório de agente no formato do modo silencioso."""

    tipo: str
    feito: List[str] = field(default_factory=list)
    estado: List[str] = field(default_factory=list)
    erro: List[str] = field(default_factory=list)
    sugestao: List[str] = field(default_factory=list)
    decisao_pedida: str = ""

    def total_linhas(self) -> int:
        return len(self.feito) + len(self.estado) + len(self.erro) + len(self.sugestao)

    def validar(self) -> List[str]:
        """Devolve a lista de violações do protocolo. Vazia = pode falar."""
        violacoes: List[str] = []
        if self.tipo not in TIPOS:
            violacoes.append("tipo inválido: %r (vale %s)" % (self.tipo, ", ".join(TIPOS)))
        if self.total_linhas() > MAX_LINHAS:
            violacoes.append(
                "relatório tem %d linhas de conteúdo, o limite é %d"
                % (self.total_linhas(), MAX_LINHAS)
            )
        if self.tipo == BLOQUEIO:
            if not self.decisao_pedida.strip():
                violacoes.append("bloqueio precisa dizer qual decisão está pedindo")
        if self.tipo == PROGRESSO:
            if not self.feito:
                violacoes.append("relatório de fim de ciclo precisa ter FEITO")
        for nome, linhas in (
            ("FEITO", self.feito),
            ("ESTADO", self.estado),
            ("ERRO", self.erro),
            ("SUGESTÃO", self.sugestao),
        ):
            for linha in linhas:
                if "\n" in linha:
                    violacoes.append("%s contém linha com quebra interna" % nome)
                    break
        return violacoes

    def pode_falar(self) -> bool:
        """Modo silencioso: só fala se o relatório passar no portão."""
        return not self.validar()

    def formatar(self) -> str:
        """Monta o texto do relatório. Exige que passe na validação primeiro."""
        violacoes = self.validar()
        if violacoes:
            raise ValueError("relatório inválido: " + "; ".join(violacoes))
        cabecalho = "RELATÓRIO (%s)" % self.tipo
        blocos = [cabecalho]
        for titulo, linhas in (
            ("FEITO", self.feito),
            ("ESTADO", self.estado),
            ("ERRO", self.erro),
            ("SUGESTÃO", self.sugestao),
        ):
            blocos.append(titulo + ":")
            if linhas:
                blocos.extend("- " + linha for linha in linhas)
            else:
                blocos.append("- (nada)")
        if self.tipo == BLOQUEIO:
            blocos.append("DECISÃO PEDIDA: " + self.decisao_pedida.strip())
        return "\n".join(blocos)


def cortar_em_linhas(texto: str, max_linhas: int = MAX_LINHAS) -> List[str]:
    """Quebra um texto em linhas curtas, respeitando o teto do modo silencioso."""
    linhas = [l.strip() for l in texto.replace("\r", "").split("\n")]
    linhas = [l for l in linhas if l]
    return linhas[:max_linhas]


def analisar(texto: str) -> Relatorio:
    """Lê um relatório em texto e devolve o objeto (tolerante a variações)."""
    rel = Relatorio(tipo=STATUS)
    secao_atual: Optional[str] = None
    primeira_linha = True
    for crua in texto.replace("\r", "").split("\n"):
        linha = crua.strip()
        if primeira_linha:
            primeira_linha = False
            for t in TIPOS:
                if t in linha.upper():
                    rel.tipo = t
                    break
            continue
        topo = linha.rstrip(":").upper()
        if topo in SECOES:
            secao_atual = topo
            continue
        if topo.startswith("DECISÃO PEDIDA"):
            rel.decisao_pedida = linha.split(":", 1)[1].strip() if ":" in linha else ""
            secao_atual = None
            continue
        if not linha or secao_atual is None:
            continue
        conteudo = linha[2:].strip() if linha.startswith("- ") else linha
        alvo = {
            "FEITO": rel.feito,
            "ESTADO": rel.estado,
            "ERRO": rel.erro,
            "SUGESTÃO": rel.sugestao,
        }[secao_atual]
        if conteudo and conteudo != "(nada)":
            alvo.append(conteudo)
    return rel

"""Redacao local de dados sensiveis (PII) antes de qualquer saida para a nuvem.

Origem: backlog item 13 de PESQUISA-CONCORRENTES.md (ideia roubada do
isair/jarvis): passada de filtro PII LOCAL antes de mandar historico ou
transcricao para modelos cloud (Gemini Live / voz Kore). O Alex vai falar de
dinheiro, familia e negocio com a ZARA - tem que vazar zero.

Tudo stdlib, sem dependencias. Detecta CPF (com digitos verificadores),
CNPJ, telefone BR, e-mail, cartao de credito (Luhn), chave PIX aleatoria
(UUID) e chaves de API comuns (sk-, nvapi-, AIza...).

A varredura e feita em UMA passada com alternancia ordenada: o padrao mais
especifico ganha na posicao, e trechos que parecem cartao mas falham no Luhn
sao devolvidos intactos sem deixar o padrao de telefone morder por dentro.
"""
from __future__ import annotations

import re

TOKEN_CPF = "[CPF]"
TOKEN_CNPJ = "[CNPJ]"
TOKEN_TELEFONE = "[TELEFONE]"
TOKEN_EMAIL = "[EMAIL]"
TOKEN_CARTAO = "[CARTAO]"
TOKEN_PIX = "[PIX]"
TOKEN_CHAVE_API = "[CHAVE-API]"

_PADROES = {
    "chave_api": r"sk\-[A-Za-z0-9]{8,}|nvapi\-[A-Za-z0-9_\-]{8,}|"
    r"AIza[0-9A-Za-z_\-]{20,}|ghp_[A-Za-z0-9]{20,}|"
    r"xox[bpas]\-[A-Za-z0-9\-]{8,}",
    "email": r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}",
    "pix": r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
    "cartao": r"(?<![\d+])(?:\d[\s.\-]?){13,19}(?!\d)",
    "cnpj": r"(?<!\d)\d{2}[.\s]?\d{3}[.\s]?\d{3}[/\s]?\d{4}[-.\s]?\d{2}(?!\d)",
    "cpf": r"(?<!\d)\d{3}[.\s]?\d{3}[.\s]?\d{3}[-.\s]?\d{2}(?!\d)",
    "telefone": r"(?<!\d)(?:\+55[\s.\-]?)?"
    r"(?:\(?(?:1[1-9]|[2-9]\d)\)?[\s.\-]?)?"
    r"9?\d{4}[\s.\-]?\d{4}(?!\d)",
}

_COMBINADO = re.compile(
    "|".join(f"(?P<{nome}>{padrao})" for nome, padrao in _PADROES.items())
)

_TOKENS = {
    "chave_api": TOKEN_CHAVE_API,
    "email": TOKEN_EMAIL,
    "pix": TOKEN_PIX,
    "telefone": TOKEN_TELEFONE,
}


def _digitos_validos(numeros: str, pesos: list[int]) -> bool:
    soma = sum(int(d) * p for d, p in zip(numeros, pesos))
    resto = soma % 11
    return (0 if resto < 2 else 11 - resto) == int(numeros[len(pesos)])


def cpf_valido(digitos: str) -> bool:
    """True se os 11 digitos passam nos dois digitos verificadores do CPF."""
    if len(digitos) != 11 or len(set(digitos)) == 1:
        return False
    return _digitos_validos(digitos, list(range(10, 1, -1))) and _digitos_validos(
        digitos, list(range(11, 1, -1))
    )


def cnpj_valido(digitos: str) -> bool:
    """True se os 14 digitos passam nos dois digitos verificadores do CNPJ."""
    if len(digitos) != 14 or len(set(digitos)) == 1:
        return False
    return _digitos_validos(digitos, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]) and (
        _digitos_validos(digitos, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    )


def _luhn(digitos: str) -> bool:
    total = 0
    for i, d in enumerate(reversed(digitos)):
        n = int(d)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def _so_digitos(texto: str) -> str:
    return re.sub(r"\D", "", texto)


_DDD_RE = re.compile(r"1[1-9]|[2-9]\d")


def _parece_telefone_br(digitos: str) -> bool:
    """Heuristica p/ corrida de 13+ digitos: e telefone BR sem formatacao?"""
    corpo = digitos[2:] if digitos.startswith("55") and len(digitos) in (12, 13) else digitos
    return len(corpo) in (10, 11) and bool(_DDD_RE.fullmatch(corpo[:2]))


def _classificar(match: re.Match) -> tuple[str, str] | None:
    """(tipo, token) ou None se o trecho nao for PII de verdade."""
    tipo = match.lastgroup or ""
    trecho = match.group(0)
    if tipo in _TOKENS:
        return tipo, _TOKENS[tipo]
    digitos = _so_digitos(trecho)
    if tipo == "cartao":
        if 13 <= len(digitos) <= 19 and _luhn(digitos):
            return tipo, TOKEN_CARTAO
    elif tipo == "cpf":
        if cpf_valido(digitos):
            return tipo, TOKEN_CPF
    elif tipo == "cnpj":
        if cnpj_valido(digitos):
            return tipo, TOKEN_CNPJ
    # Validacao falhou: se era corrida de digitos SEM formatacao, pode ser um
    # telefone BR que o padrao de cpf/cnpj/cartao consumiu antes do telefone
    # (ex.: 71999887766). Trecho com pontos/tracos estilo CPF fica intacto.
    if re.fullmatch(r"\d+", trecho) and _parece_telefone_br(digitos):
        return "telefone", TOKEN_TELEFONE
    return None


def redact(texto: str | None) -> str:
    """Mascara PII no texto. Texto sem PII volta intacto."""

    def _trocar(match: re.Match) -> str:
        achado = _classificar(match)
        return achado[1] if achado else match.group(0)

    return _COMBINADO.sub(_trocar, texto or "")


def find_pii(texto: str | None) -> list[dict]:
    """Lista ocorrencias de PII: [{"tipo", "trecho", "inicio", "fim"}]."""
    achados: list[dict] = []
    for match in _COMBINADO.finditer(texto or ""):
        achado = _classificar(match)
        if achado:
            achados.append(
                {
                    "tipo": achado[0],
                    "trecho": match.group(0),
                    "inicio": match.start(),
                    "fim": match.end(),
                }
            )
    return achados


def redaction_report(texto: str | None) -> dict:
    """Relatorio: {"teve_pii": bool, "contagem": {tipo: n}, "texto": mascarado}."""
    achados = find_pii(texto)
    contagem: dict[str, int] = {}
    for item in achados:
        contagem[item["tipo"]] = contagem.get(item["tipo"], 0) + 1
    return {
        "teve_pii": bool(achados),
        "contagem": contagem,
        "texto": redact(texto),
    }

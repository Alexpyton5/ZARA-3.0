"""ZARA-LATENCIA-MEDIDA-001 — onde o tempo da ZARA realmente vai.

Por que este arquivo existe
---------------------------
Alex reclama que a ZARA é lenta desde o começo, e essa reclamação nunca foi
medida: foi sentida. A única medição que existiu (2026-08-13) mostrou que o
raciocínio dela custa **centésimos de segundo** — 0,01 s numa conversa, 0,34 s
numa ação no PC. Ou seja, a parte que todo mundo tentaria otimizar já é rápida.

O tempo que ele sente está em dois lugares que o banco de histórico não vê:

1. **Fim de turno** — quanto silêncio o servidor espera antes de decidir que ele
   parou de falar. Antes disso, nada começa.
2. **Segunda viagem da voz** — depois de a ação já ter acontecido, a ZARA manda
   o texto de volta ao Gemini e espera a Kore gerar o áudio. Uma ida e volta de
   rede inteira só para falar uma frase que já estava pronta.

Os marcadores `[VOICE_TRACE]` medem parte disso, mas só no console — e o console
morre quando o app fecha. Por isso nunca houve número: ninguém estava com o
terminal aberto na hora em que ele achou lento.

Aqui cada turno vira uma linha em disco. Depois de alguns dias de uso normal dá
para responder "onde está o tempo?" com dado, e não com palpite. Otimizar a
parte errada custa dias — foi exatamente o que essa medição evitou uma vez.

Regra: **isto observa, nunca atrapalha.** Qualquer falha aqui é engolida em
silêncio. Um cronômetro que derruba a voz seria pior que não medir.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

_LIMITE_DE_LINHAS = 5000  # ~semanas de uso; passou disso, corta as antigas


def _arquivo() -> Path | None:
    try:
        from core.paths import user_data_dir

        return user_data_dir() / "latencia.jsonl"
    except Exception:
        return None


class Cronometro:
    """Um turno de voz, do fim da fala dele até a voz dela começar."""

    def __init__(self, entrada: str = "", origem: str = "voz"):
        self.origem = origem
        self.caracteres_ouvidos = len(entrada or "")
        self._inicio = time.perf_counter()
        self._marcas: dict[str, float] = {}

    def marcar(self, etapa: str) -> None:
        """Registra quantos ms se passaram desde o começo do turno."""
        try:
            self._marcas[etapa] = (time.perf_counter() - self._inicio) * 1000.0
        except Exception:
            pass

    def fechar(self, *, rota: str = "", voz: str = "", falou: bool = False) -> dict:
        registro = {
            "quando": time.time(),
            "origem": self.origem,
            "rota": rota,
            "voz": voz,
            "falou": bool(falou),
            "ouvidos": self.caracteres_ouvidos,
            "total_ms": round((time.perf_counter() - self._inicio) * 1000.0),
            "etapas": {k: round(v) for k, v in self._marcas.items()},
        }
        _gravar(registro)
        return registro


def _gravar(registro: dict) -> None:
    try:
        arquivo = _arquivo()
        if arquivo is None:
            return
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        with arquivo.open("a", encoding="utf-8") as saida:
            saida.write(json.dumps(registro, ensure_ascii=False) + "\n")
        _podar(arquivo)
    except Exception:
        pass  # medir nunca pode atrapalhar


def _podar(arquivo: Path) -> None:
    """Impede o arquivo de crescer para sempre no computador dele."""
    try:
        linhas = arquivo.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(linhas) <= _LIMITE_DE_LINHAS:
            return
        cortadas = linhas[-_LIMITE_DE_LINHAS:]
        arquivo.write_text("\n".join(cortadas) + "\n", encoding="utf-8")
    except Exception:
        pass


# ZARA-SILENCIO-VISIVEL-001
#
# Alex: "ela às vezes ouvia um comando e não me respondia nada... eu tinha que
# ficar falando 'Zara, você me entendeu?', aí ela ressuscitava".
#
# O turno descartado não deixava rastro. O banco de conversa só guarda o que
# foi aceito, então o histórico mostrava um diálogo impecável enquanto ele
# falava sozinho na sala. Bug invisível vira adivinhação — e adivinhação é o
# que custou semanas a este projeto.
def anotar_descarte(texto: str, motivo: str) -> None:
    """Uma frase que ela ouviu e jogou fora, com o motivo.

    ZARA-DESCARTE-SEM-SEGREDO-001. Achado 18 da auditoria do Codex: isto
    guardava 160 caracteres exatos do que foi descartado, em texto puro, no
    computador do Alex.

    E o que é descartado é justamente o que ela NÃO deveria estar ouvindo —
    conversa de fundo, televisão, alguém falando ao telefone na sala. Se uma
    dessas falas contiver uma senha, um cartão ou um assunto particular de
    outra pessoa, aquilo virava arquivo.

    O registro existe para responder duas perguntas: *quanto* ela descarta e
    *por quê*. Nenhuma delas precisa do conteúdo. Fica o tamanho, o motivo e as
    primeiras palavras — o suficiente para eu reconhecer "isso era a novela" sem
    transcrever a sala inteira.
    """
    frase = " ".join(str(texto or "").split())
    _gravar({
        "quando": time.time(),
        "origem": "voz",
        "rota": "descartado",
        "motivo": motivo,
        "ouvidos": len(frase),
        "inicio": _so_o_comeco(frase),
        "total_ms": 0,
        "etapas": {},
    })


# Quatro palavras bastam para eu reconhecer o tipo da fala. Uma senha ou um
# número de cartão não cabe em quatro palavras de abertura, e o resto da frase
# nunca chega ao disco.
_PALAVRAS_GUARDADAS = 4
_SEGREDO = re.compile(
    r"\b(?:senha|palavra[-\s]?passe|c[óo]digo|pin|cvv|cart[ãa]o|conta|ag[êe]ncia|"
    r"cpf|cnpj|rg|token|chave|secreta?)\b",
    re.IGNORECASE,
)


def _so_o_comeco(frase: str) -> str:
    """As primeiras palavras, e nada quando elas cheiram a segredo."""
    if not frase:
        return ""
    if _SEGREDO.search(frase):
        # Melhor perder a pista do que gravar o começo de uma senha.
        return "[assunto sensível]"
    palavras = frase.split()
    comeco = " ".join(palavras[:_PALAVRAS_GUARDADAS])
    return comeco + ("..." if len(palavras) > _PALAVRAS_GUARDADAS else "")


def relatorio(ultimos: int = 200) -> dict:
    """Resumo legível: onde o tempo foi parar nos últimos turnos.

    Devolve mediana, não média: um turno de 30 s esperando a rede não pode
    disfarçar vinte turnos rápidos — nem o contrário.
    """
    registros = []
    try:
        arquivo = _arquivo()
        if arquivo is None or not arquivo.exists():
            return {"turnos": 0, "aviso": "nada medido ainda"}
        for linha in arquivo.read_text(encoding="utf-8", errors="replace").splitlines()[-ultimos:]:
            linha = linha.strip()
            if linha.startswith("{"):
                try:
                    registros.append(json.loads(linha))
                except Exception:
                    continue
    except Exception:
        return {"turnos": 0, "aviso": "nao consegui ler o arquivo"}

    # Auditoria do Codex, achado 15: turno descartado tem total_ms = 0 e entrava
    # na mesma conta dos turnos reais. Com a TV ligada, 101 descartes contra 99
    # respostas de dois segundos dariam mediana ZERO — e a ZARA anunciaria
    # "0,0 segundos", que é exatamente o tipo de número bonito e falso que este
    # arquivo existe para impedir.
    descartados = [r for r in registros if r.get("rota") == "descartado"]
    registros = [r for r in registros if r.get("rota") != "descartado"]

    if not registros:
        return {
            "turnos": 0,
            "descartados": len(descartados),
            "aviso": "nada medido ainda",
        }

    def mediana(valores: list[float]) -> float:
        if not valores:
            return 0.0
        ordenados = sorted(valores)
        meio = len(ordenados) // 2
        if len(ordenados) % 2:
            return ordenados[meio]
        return (ordenados[meio - 1] + ordenados[meio]) / 2.0

    etapas: dict[str, list[float]] = {}
    for r in registros:
        for nome, valor in (r.get("etapas") or {}).items():
            etapas.setdefault(nome, []).append(float(valor))

    por_rota: dict[str, list[float]] = {}
    for r in registros:
        por_rota.setdefault(str(r.get("rota") or "?"), []).append(float(r.get("total_ms") or 0))

    return {
        "turnos": len(registros),
        "descartados": len(descartados),
        "total_ms_mediano": round(mediana([float(r.get("total_ms") or 0) for r in registros])),
        "etapas_ms_medianas": {k: round(mediana(v)) for k, v in sorted(etapas.items())},
        "por_rota_ms_mediano": {k: round(mediana(v)) for k, v in sorted(por_rota.items())},
        "falou_em": sum(1 for r in registros if r.get("falou")),
    }

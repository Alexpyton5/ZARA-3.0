"""Resumo estruturado persistido ao fim de cada sessao de conversa.

Origem: backlog item 12 de PESQUISA-CONCORRENTES.md (padroes de memoria em
agente de voz): ao fim de cada conversa, a ZARA grava um resumo estruturado -
o que foi pedido, feito e pendencias. Alimenta direto o ritual do sonho e o
relatorio da manha do Alex, com fonte em vez de achismo.

Formato: uma linha JSON por sessao em
<data_dir>/session-summaries/YYYY-MM-DD.jsonl
(textos armazenados passam pela redacao de PII de core/pii_redaction).
"""
from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

try:
    from core.pii_redaction import redact
except Exception:  # pragma: no cover - fallback defensivo

    def redact(texto):  # type: ignore[misc]
        return texto or ""


try:
    from core.paths import data_dir as _data_dir
except Exception:  # pragma: no cover - fallback defensivo
    _data_dir = None  # type: ignore[assignment]

_MAX_TURNO_CHARS = 400
_TOKEN_RE = re.compile(r"[a-zà-úâêôãõç]{4,}", re.IGNORECASE)
_STOPWORDS = frozenset(
    """
    para que com uma dos das nao não sim ele ela eles elas voce você seu sua
    seus suas meu minha meus minhas isso isto esse essa este esta aqui onde
    como quando qual quais muito mais mas por foi são são tem têm pode fazer
    fez fazer fala fala falei disse disse então então agora hoje ontem amanha
    amanhã coisa coisas tudo nada algo alguem alguém vez vezes sobre entre
    mesmo mesma todos todas cada outra outro outras outros dois duas tres três
    porque pois pelo pela pelos pelas num numa quero quer quer quer pode pode
    """.split()
)


def _agora_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _topicos(turnos_usuario: list[str], limite: int = 8) -> list[str]:
    palavras = [
        token.lower()
        for texto in turnos_usuario
        for token in _TOKEN_RE.findall(texto or "")
        if token.lower() not in _STOPWORDS
    ]
    return [palavra for palavra, _ in Counter(palavras).most_common(limite)]


class SessionRecorder:
    """Grava os turnos de uma sessao e persiste o resumo estruturado."""

    def __init__(
        self,
        canal: str = "voz",
        session_id: str | None = None,
        base_dir: str | Path | None = None,
    ) -> None:
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.canal = canal
        self.inicio = _agora_iso()
        self._turnos: list[dict] = []
        self._base_dir = Path(base_dir) if base_dir else None

    def add_turn(self, papel: str, texto: str | None) -> None:
        """Adiciona um turno ("usuario" ou "zara"). Texto fica redigido."""
        limpo = (texto or "").strip()
        if not limpo:
            return
        self._turnos.append(
            {
                "papel": papel,
                "texto": redact(limpo[:_MAX_TURNO_CHARS]),
                "quando": _agora_iso(),
            }
        )

    def summary(self, resultado: str = "ok", nota: str = "") -> dict:
        """Resumo estruturado da sessao (dicionario pronto p/ JSON)."""
        turnos_usuario = [
            t["texto"] for t in self._turnos if t["papel"] == "usuario"
        ]
        return {
            "session_id": self.session_id,
            "canal": self.canal,
            "inicio": self.inicio,
            "fim": _agora_iso(),
            "resultado": resultado,
            "nota": redact(nota),
            "total_turnos": len(self._turnos),
            "turnos_usuario": len(turnos_usuario),
            "topicos": _topicos(turnos_usuario),
            "pedidos": turnos_usuario[:20],
        }

    def _arquivo(self) -> Path:
        raiz = self._base_dir or (
            _data_dir() / "session-summaries" if _data_dir else Path.cwd() / "data"
        )
        pasta = Path(raiz)
        pasta.mkdir(parents=True, exist_ok=True)
        return pasta / (datetime.now(timezone.utc).strftime("%Y-%m-%d") + ".jsonl")

    def persist(self, resultado: str = "ok", nota: str = "") -> Path:
        """Fecha a sessao e anexa o resumo ao JSONL do dia. Retorna o arquivo."""
        resumo = self.summary(resultado=resultado, nota=nota)
        arquivo = self._arquivo()
        with arquivo.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(resumo, ensure_ascii=False) + "\n")
        return arquivo


def read_day_summaries(
    dia: str, base_dir: str | Path | None = None
) -> list[dict]:
    """Le os resumos de um dia ("YYYY-MM-DD"). Lista vazia se nao houver."""
    raiz = Path(base_dir) if base_dir else (
        _data_dir() / "session-summaries" if _data_dir else Path.cwd() / "data"
    )
    arquivo = Path(raiz) / (dia + ".jsonl")
    if not arquivo.exists():
        return []
    resumos: list[dict] = []
    with arquivo.open(encoding="utf-8") as fh:
        for linha in fh:
            linha = linha.strip()
            if linha:
                resumos.append(json.loads(linha))
    return resumos

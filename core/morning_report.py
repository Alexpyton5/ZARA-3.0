"""Relatorio da manha no formato do Alex — FRENTE H (GIGANTE 3 "JARVIS REAL").

Formato exato que ele pediu:
    "Bom dia Alex, as atualizacoes da Zara de hoje sao essas: [features novas]"

Regras dele, impostas pelo modulo:
- RESULTADOS primeiro: so entra item que mudou no app e ele pode tocar.
- Fonte de dados = SO o verificado (quadro, commits, testes). Item sem
  fonte NAO entra — o gerador nunca inventa uma palavra.
- Noite sem nada tocavel: o texto diz, com estas palavras, "a noite falhou".
- Curto: no maximo 8 itens, 1 frase cada, linguagem simples.

Logica pura, stdlib, sem rede, sem custo. A coleta so LE arquivos do disco;
a geracao so renderiza o que recebeu com fonte. Traducao commit -> frase
simples e feita pelo curador (o loop da noite, que le o quadro); commit sem
traducao volta na lista `sem_traducao` em vez de virar frase inventada.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ABERTURA = "Bom dia Alex, as atualizacoes da Zara de hoje sao essas:"
NOITE_FALHOU = "a noite falhou"

MAX_ITENS = 8
MAX_TEXTO_ITEM = 180

_JANELA_COLETA_HORAS = 24


@dataclass
class ItemNoite:
    """Um fato verificado, em 1 frase simples, pronto p/ o relatorio."""

    texto: str  # 1 frase, linguagem simples, zero jargao
    fonte: str  # onde foi verificado (ex.: "commit 47c3234", "QUADRO 28/09 17:25")
    tocavel: bool = True  # ele toca isso no app? (so tocavel entra no texto dele)


@dataclass
class FatosNoite:
    """Fatos brutos coletados do disco — cada um carrega a propria fonte."""

    commits: list = field(default_factory=list)  # [(sha, assunto)]
    suite: dict = field(default_factory=dict)  # {passed, failed, run_id, summary}
    concluidos: list = field(default_factory=list)  # [(arquivo, titulo)]


def coletar_fatos(raiz) -> FatosNoite:
    """Le do disco (SO leitura) os fatos verificaveis da noite.

    - git log das ultimas 24h (assuntos + SHA — prova do que entrou no codigo)
    - .zara-tests/latest.json (resultado da suite — prova do que esta verde)
    - ZOE-INBOX/concluidas/RELATORIO-*.md das ultimas 24h (missoes fechadas)

    Falha de leitura -> lista vazia / dict vazio (fail closed: dado ausente
    NAO vira item, nunca e inventado).
    """
    raiz = Path(raiz)
    return FatosNoite(
        commits=_coletar_commits(raiz),
        suite=_coletar_suite(raiz),
        concluidos=_coletar_concluidos(raiz),
    )


def _coletar_commits(raiz: Path) -> list:
    try:
        proc = subprocess.run(
            ["git", "-C", str(raiz), "log",
             "--since=24 hours ago",
             "--pretty=format:%H%x00%s",
             "--no-merges"],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    saida = []
    for linha in proc.stdout.splitlines():
        if "\x00" not in linha:
            continue
        sha, _, assunto = linha.partition("\x00")
        if sha and assunto:
            saida.append((sha[:7], assunto.strip()))
    return saida


def _coletar_suite(raiz: Path) -> dict:
    caminho = raiz / ".zara-tests" / "latest.json"
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except Exception:
        return {}
    resultado = dados.get("result") or {}
    if not isinstance(resultado, dict):
        return {}
    return {
        "passed": resultado.get("passed"),
        "failed": resultado.get("failed"),
        "run_id": dados.get("run_id"),
        "summary": resultado.get("summary_line"),
    }


def _coletar_concluidos(raiz: Path) -> list:
    pasta = raiz / "ZOE-INBOX" / "concluidas"
    try:
        arquivos = sorted(pasta.glob("RELATORIO-*.md"))
    except Exception:
        return []
    limite = datetime.now(timezone.utc) - timedelta(hours=_JANELA_COLETA_HORAS)
    saida = []
    for arq in arquivos:
        try:
            mtime = datetime.fromtimestamp(arq.stat().st_mtime, tz=timezone.utc)
            if mtime < limite:
                continue
            primeira = arq.read_text(encoding="utf-8").splitlines()[0]
            titulo = primeira.lstrip("# ").strip() or arq.name
            saida.append((arq.name, titulo))
        except Exception:
            continue
    return saida


def traduzir(fatos: FatosNoite, mapa: dict) -> tuple:
    """Commit -> ItemNoite usando a traducao do curador (sha -> frase simples).

    Commit sem traducao no mapa NAO vira frase: volta em `sem_traducao`
    p/ o loop da noite escrever a frase simples com a fonte do quadro.
    Nada e inventado aqui.
    """
    itens: list[ItemNoite] = []
    sem_traducao: list[str] = []
    for sha, assunto in fatos.commits:
        texto = (mapa or {}).get(sha)
        if texto:
            itens.append(ItemNoite(
                texto=texto,
                fonte="commit %s (%s)" % (sha, assunto[:60]),
                tocavel=True,
            ))
        else:
            sem_traducao.append("%s %s" % (sha, assunto[:60]))
    return itens, sem_traducao


def gerar_relatorio(itens, *, extras: list | None = None) -> str:
    """Monta o texto no formato exato dele.

    - So itens com texto E fonte entram (item sem fonte = erro do chamador).
    - Tocaveis primeiro, na ordem recebida; no maximo MAX_ITENS.
    - Nenhum tocavel -> o texto diz "a noite falhou", com estas palavras.
    - `extras`: itens verificados mas NAO tocaveis (infra, seguranca) que o
      curador queira registrar — NAO vao p/ o texto dele, vao p/ auditoria.
    """
    itens = list(itens or [])
    for item in itens:
        _validar(item)
    tocaveis = [i for i in itens if i.tocavel][:MAX_ITENS]

    linhas = [ABERTURA, ""]
    if not tocaveis:
        linhas.append("- " + NOITE_FALHOU)
    else:
        for item in tocaveis:
            linhas.append("- " + item.texto)
    return "\n".join(linhas)


def auditoria(itens, *, extras: list | None = None) -> str:
    """Rastro verificavel: cada item com a fonte — p/ o loop conferir."""
    linhas = ["AUDITORIA DO RELATORIO DA MANHA"]
    for item in list(itens or []) + list(extras or []):
        marca = "TOCAVEL" if item.tocavel else "infra"
        linhas.append("- [%s] %s | fonte: %s" % (marca, item.texto, item.fonte))
    if len(linhas) == 1:
        linhas.append("(nenhum item)")
    return "\n".join(linhas)


def _validar(item: ItemNoite) -> None:
    if not isinstance(item, ItemNoite):
        raise TypeError("relatorio so aceita ItemNoite (fato verificado)")
    if not item.texto or not item.texto.strip():
        raise ValueError("item sem texto nao entra no relatorio")
    if not item.fonte or not item.fonte.strip():
        raise ValueError("item sem fonte nao entra no relatorio: %r" % item.texto[:40])
    if len(item.texto) > MAX_TEXTO_ITEM:
        raise ValueError(
            "item longo demais (%d > %d): quebre em 1 frase simples — %r"
            % (len(item.texto), MAX_TEXTO_ITEM, item.texto[:40])
        )

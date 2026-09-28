# -*- coding: utf-8 -*-
"""Mãos dos bots do Lab Vivo — o worker REAL que executa ordens no disco.

GIGANTE 2 "LAB VIVO" — Fase A/B. Lógica pura + E/S de disco.
Sem modelo, sem rede, custo zero.

O worker é o que transforma ordem em efeito real: ele não simula,
ele ESCREVE, LÊ e CHECA arquivos de verdade dentro da área de
trabalho do Lab (.lab-vivo/work). O relatório que ele devolve já sai
no formato do modo silencioso (FEITO/ESTADO/ERRO/SUGESTÃO), pronto
para passar pelo portão do lab_report sem retoque.

Linguagem das ordens (primeira linha = verbo):
    ESCREVER <caminho-relativo>
    <conteúdo nas linhas seguintes...>
    LER <caminho-relativo>
    CHECAR <caminho-relativo> CONTEM <trecho>
    LISTAR [caminho-relativo]

Divisão de tarefa (a mãe pede ajuda — Fase B):
    ...ordem normal...
    DIVIDIR-PARA <ASSENTO>: <ordem da parte>
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Fase A: os 11 assentos com papel escrito (espelho no QUADRO-TRABALHO.md)
# ---------------------------------------------------------------------------

SEAT_ORDER: List[str] = [
    "CEO",
    "ARCHITECT",
    "UI_DESIGNER",
    "ENGINEER",
    "SCRIBE",
    "REVIEWER",
    "CRITIC",
    "SECRETARY",
    "TESTER",
    "RESEARCHER",
    "PACKAGER",
]

SEAT_ROLES: Dict[str, str] = {
    "CEO": "Decide e aprova. Monta o plano do turno a partir do backlog aprovado. Nunca executa tarefa.",
    "ARCHITECT": "Desenha antes de codar: estrutura, arquivos e contratos da solução.",
    "UI_DESIGNER": "Cuida da interface: telas, textos e fluxos que o Alex vê.",
    "ENGINEER": "Executa: escreve e altera arquivos, implementa o que foi desenhado.",
    "SCRIBE": "Escreve: relatórios, atas e documentação do que foi feito.",
    "REVIEWER": "Revisa o trabalho dos outros: aponta erro e sugere correção.",
    "CRITIC": "Questiona: pode rejeitar proposta, sempre com motivo obrigatório.",
    "SECRETARY": "Organiza: recados, prazos, mantém caixinha e quadro em ordem.",
    "TESTER": "Verifica no disco se o prometido foi entregue de verdade.",
    "RESEARCHER": "Pesquisa: levanta informação com evidência antes da decisão.",
    "PACKAGER": "Empacota: prepara a entrega final (build, instalador, publicação).",
}


class WorkerError(ValueError):
    """Ordem malformada ou fora da área de trabalho."""


def _resolver(dir_trabalho: Path, rel: str) -> Path:
    """Resolve um caminho relativo SEMPRE dentro da área de trabalho."""
    rel = (rel or "").strip().replace("\\", "/")
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        raise WorkerError(f"caminho recusado: {rel!r}")
    base = dir_trabalho.resolve()
    alvo = (base / rel).resolve()
    if alvo != base and base not in alvo.parents:
        raise WorkerError(f"caminho fora da área de trabalho: {rel!r}")
    return alvo


def relatorio(feito: List[str], estado: List[str],
              erro: Optional[List[str]] = None,
              sugestao: Optional[List[str]] = None) -> str:
    """Monta o relatório no formato que o portão do modo silencioso lê."""
    linhas = ["PROGRESSO", "FEITO:"]
    linhas += [f"- {f}" for f in feito] or ["- (nada)"]
    linhas.append("ESTADO:")
    linhas += [f"- {e}" for e in estado] or ["- (nada)"]
    linhas.append("ERRO:")
    linhas += [f"- {e}" for e in (erro or [])] or ["- (nada)"]
    linhas.append("SUGESTÃO:")
    linhas += [f"- {s}" for s in (sugestao or [])] or ["- (nada)"]
    return "\n".join(linhas)


def executar_ordem(assento: str, texto_ordem: str,
                   dir_trabalho: Path) -> Dict[str, Any]:
    """Executa UMA ordem de verdade no disco. Devolve o resultado.

    Retorna {"ok", "report", "arquivos", "split"} — "split" só aparece
    quando a ordem traz DIVIDIR-PARA (a mãe pedindo ajuda).
    """
    if assento not in SEAT_ROLES:
        return {"ok": False,
                "report": relatorio([], ["ordem recusada"],
                                    [f"assento desconhecido: {assento}"],
                                    ["usar um dos 11 assentos"]),
                "arquivos": []}
    import re
    # acha a primeira ordem de verdade (pula cabeçalhos "[PLANO...]"/"[parte de...]")
    m = re.search(r"(?i)\b(ESCREVER|LER|CHECAR|LISTAR|DIVIDIR-PARA)\b",
                  texto_ordem or "")
    if not m:
        primeira = (texto_ordem or "").strip().split("\n")[0][:60]
        raise WorkerError(f"nenhuma ordem encontrada; primeira linha: '{primeira}'")
    linhas = [ln for ln in texto_ordem[m.start():].split("\n") if ln.strip()]
    verbo, _, resto = linhas[0].strip().partition(" ")
    verbo = verbo.upper()
    resto = resto.strip()
    dir_trabalho.mkdir(parents=True, exist_ok=True)
    arquivos: List[str] = []
    feito: List[str] = []
    estado: List[str] = []
    split: List[Dict[str, Any]] = []

    # Separa bloco de divisão (mãe pedindo ajuda) do corpo da ordem.
    corpo: List[str] = []
    for ln in linhas[1:] if verbo != "DIVIDIR-PARA" else linhas:
        if ln.strip().upper().startswith("DIVIDIR-PARA "):
            _, _, pedido = ln.partition(" ")  # tira o "DIVIDIR-PARA"
            destino, _, ordem_parte = pedido.partition(":")
            destino = destino.strip().upper()
            ordem_parte = ordem_parte.strip()
            if not destino or not ordem_parte:
                raise WorkerError(f"DIVIDIR-PARA malformado: {ln!r}")
            if destino not in SEAT_ROLES:
                raise WorkerError(f"DIVIDIR-PARA assento desconhecido: {destino}")
            split.append({
                "title": f"Parte para {destino}",
                "instruction": ordem_parte,
                "assigned_agent_id": destino,
                "budget_usd": 0.1,  # > 0: o turno só divide com budget
                "max_turns": 2,
            })
        else:
            corpo.append(ln)

    if verbo == "ESCREVER":
        alvo = _resolver(dir_trabalho, resto)
        alvo.parent.mkdir(parents=True, exist_ok=True)
        alvo.write_text("\n".join(corpo) + "\n", encoding="utf-8")
        arquivos.append(str(alvo.relative_to(dir_trabalho.resolve())))
        feito.append(f"arquivo {resto} escrito ({alvo.stat().st_size} bytes)")
        estado.append("tarefa concluída")
    elif verbo == "LER":
        alvo = _resolver(dir_trabalho, resto)
        conteudo = alvo.read_text(encoding="utf-8")
        feito.append(f"arquivo {resto} lido ({len(conteudo)} caracteres)")
        estado.append("tarefa concluída")
    elif verbo == "CHECAR":
        if " CONTEM " not in resto.upper():
            raise WorkerError("CHECAR exige: CHECAR <caminho> CONTEM <trecho>")
        parte_alta = resto.upper()
        idx = parte_alta.index(" CONTEM ")
        caminho = resto[:idx].strip()
        trecho = resto[idx + len(" CONTEM "):]
        alvo = _resolver(dir_trabalho, caminho)
        conteudo = alvo.read_text(encoding="utf-8")
        if trecho not in conteudo:
            return {"ok": False,
                    "report": relatorio(
                        [], ["verificação concluída"],
                        [f"{caminho} NÃO contém o trecho esperado"],
                        ["o responsável refazer a entrega"]),
                    "arquivos": arquivos}
        feito.append(f"{caminho} contém o trecho esperado (verificado no disco)")
        estado.append("tarefa concluída")
    elif verbo == "LISTAR":
        alvo = _resolver(dir_trabalho, resto or ".")
        nomes = sorted(p.name for p in alvo.iterdir())
        feito.append(f"listados {len(nomes)} itens em {resto or '.'}: "
                     + (", ".join(nomes[:10]) if nomes else "(vazio)"))
        estado.append("tarefa concluída")
    elif verbo == "DIVIDIR-PARA":
        feito.append("ordem de divisão registrada (nenhum arquivo tocado)")
        estado.append("tarefa concluída")
    else:
        raise WorkerError(f"verbo desconhecido: {verbo!r} "
                          "(ESCREVER|LER|CHECAR|LISTAR|DIVIDIR-PARA)")

    resultado: Dict[str, Any] = {
        "ok": True,
        "report": relatorio(feito, estado, None,
                            ["nada a sugerir"] if not split
                            else [f"divisão pedida para {s['assigned_agent_id']}"
                                  for s in split]),
        "arquivos": arquivos,
    }
    if split:
        resultado["split"] = split
    return resultado


def worker_vivo_factory(dir_trabalho: Path,
                        backlog: Any = None
                        ) -> Callable[[str, str, Dict[str, Any]], Dict[str, Any]]:
    """Devolve o worker no contrato que o LabTurn chama: (assento, ordem, ctx).

    O recado da caixinha carrega só o cabeçalho do plano (nomes e estados,
    nunca conteúdo); a instrução de verdade mora na descrição do item do
    backlog — o worker busca por ctx["item_id"]. Filhas de divisão usam a
    ordem que veio no próprio recado (ctx traz "parent_item_id").
    """
    def worker(assento: str, texto_ordem: str,
               ctx: Dict[str, Any]) -> Dict[str, Any]:
        ordem = texto_ordem
        if backlog is not None and "parent_item_id" not in (ctx or {}):
            try:
                item = backlog.get((ctx or {}).get("item_id"))
                if item is not None and (item.description or "").strip():
                    ordem = item.description
            except Exception:
                pass
        try:
            return executar_ordem(assento, ordem, dir_trabalho)
        except WorkerError as e:
            return {"ok": False,
                    "report": relatorio([], ["ordem não executada"], [str(e)],
                                        ["corrigir a ordem e reenviar"]),
                    "arquivos": []}
        except OSError as e:
            return {"ok": False,
                    "report": relatorio([], ["falha de disco"], [str(e)],
                                        ["verificar espaço e permissão"]),
                    "arquivos": []}
    return worker

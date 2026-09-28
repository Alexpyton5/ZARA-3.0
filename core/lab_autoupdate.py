"""Pipeline de autoupdate do Lab Vivo (MISSAO GIGANTE 2, Fase C).

O portao (autoupdate_gate.py) e a primitiva: snapshot/aplica/verifica/rollback
com prova por hash. Este modulo e o CONDUTOR: puxa o plano, passa pelo portao
e PUBLICA sozinho somente se os gates passarem. Se qualquer etapa quebrar,
volta atras com prova em vez de deixar o app num estado quebrado.

Logica pura: sem rede, sem chamar modelo nenhum, sem custo. Quem usa o
pipeline injeta como o mundo real funciona:

    fetch_plan() -> dict | None   puxa o plano {caminho: conteudo_novo}
                                  (ex.: diff do git, item aprovado do backlog)
    read_fn(path) -> str | None    le o conteudo atual (None = nao existe)
    apply_fn(path, content)        escreve o conteudo novo
    remove_fn(path)                apaga o arquivo (desfaz uma criacao)
    run_gates() -> (bool, str)     os gates (ex.: suite de testes)
    publish(msg) -> bool           publica (ex.: git push); False/raise = falhou
    notify(text)                   avisa (ex.: caixinha/e-mail da CEO)
    now() -> float                 relogio injetavel (padrao: time.time)

Maquina de estados de cada ciclo:
    BUSCANDO -> SEM_PLANO | BUSCA_FALHOU | SEM_MUDANCA   (nada e tocado)
    BUSCANDO -> APLICANDO -> GATES_FALHOU -> REVERTIDO   (rollback provado)
                                  |-> PUBLICANDO -> PUBLICADO
                                  |-> PUBLISH_FALHOU -> REVERTIDO

Regras que o pipeline garante:
  1. Sem plano (None ou vazio) = nada a fazer: volta pra IDLE sem tocar em nada.
  2. Plano sem mudanca real (conteudo identico ao atual) = recusado; nao
     publica ruido. Arquivos identicos sao filtrados; se sobrar zero, recusa.
  3. Gates vermelhos ou explodindo = rollback provado + aviso (fail closed).
  4. Publish que falha DEPOIS dos gates verdes = rollback do mesmo jeito +
     aviso especifico (o codigo local volta; nada foi publicado).
  5. O notify NUNCA recebe conteudo de arquivo: so nomes de arquivo e estados.
  6. Journal auditavel com relogio injetavel; cada ciclo tem numero sequencial.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

try:
    from core.autoupdate_gate import AutoUpdateGate
except ImportError:  # layout flat (teste local / execucao isolada)
    from autoupdate_gate import AutoUpdateGate


# Estados finais de um ciclo (o que a CEO le no relatorio).
ESTADO_SEM_PLANO = "SEM_PLANO"
ESTADO_BUSCA_FALHOU = "BUSCA_FALHOU"
ESTADO_SEM_MUDANCA = "SEM_MUDANCA"
ESTADO_PUBLICADO = "PUBLICADO"
ESTADO_REVERTIDO = "REVERTIDO"


@dataclass
class CycleReport:
    """Resultado de um ciclo do pipeline."""

    ciclo: int
    estado: str
    arquivos: List[str] = field(default_factory=list)
    publicado: bool = False
    revertido: bool = False
    prova_rollback: Optional[dict] = None  # {"ok": bool, "arquivos": {path: bool}}
    journal: List[dict] = field(default_factory=list)
    resumo: str = ""


class AutoupdatePipeline:
    """O condutor. Criado uma vez, roda um ciclo por vez com run_once()."""

    def __init__(
        self,
        fetch_plan: Callable[[], Optional[Dict[str, str]]],
        read_fn: Callable[[str], Optional[str]],
        apply_fn: Callable[[str, str], None],
        remove_fn: Callable[[str], None],
        run_gates: Callable[[], Tuple[bool, str]],
        publish: Callable[[str], bool],
        notify: Callable[[str], None],
        now: Callable[[], float] = time.time,
    ) -> None:
        self._fetch_plan = fetch_plan
        self._read = read_fn
        self._apply = apply_fn
        self._remove = remove_fn
        self._run_gates = run_gates
        self._publish = publish
        self._notify = notify
        self._now = now
        self._gate = AutoUpdateGate(read_fn, apply_fn, remove_fn)
        self._ciclo = 0
        self._historico: List[CycleReport] = []

    def history(self) -> List[CycleReport]:
        """Relatorios dos ciclos ja rodados, em ordem."""
        return list(self._historico)

    # -- internos ---------------------------------------------------------

    def _log(self, journal: List[dict], evento: str, **campos) -> None:
        entrada = {"ts": self._now(), "evento": evento}
        entrada.update(campos)
        journal.append(entrada)

    def _avisar(self, journal: List[dict], texto: str) -> None:
        # Regra 5 por construcao: este e o unico caminho de saida do notify,
        # e so recebe textos montados aqui — nomes de arquivo e estados,
        # nunca conteudo de arquivo.
        self._notify(texto)
        self._log(journal, "aviso", texto=texto)

    @staticmethod
    def _prova_do_journal(journal: List[dict]) -> Optional[dict]:
        arquivos: Dict[str, bool] = {}
        for entrada in journal:
            if entrada.get("evento") == "rollback":
                arquivos[entrada["arquivo"]] = bool(entrada.get("prova_hash"))
        if not arquivos:
            return None
        return {"ok": all(arquivos.values()), "arquivos": arquivos}

    def _fechar_ciclo(self, relatorio: CycleReport) -> CycleReport:
        self._historico.append(relatorio)
        return relatorio

    # -- o ciclo ----------------------------------------------------------

    def run_once(self) -> CycleReport:
        """Roda um ciclo completo: buscar -> portao -> publicar ou reverter."""
        self._ciclo += 1
        ciclo = self._ciclo
        journal: List[dict] = []
        self._log(journal, "ciclo_inicio", ciclo=ciclo)

        # 1. Buscar o plano (regra 1: sem plano, nada e tocado).
        try:
            plano = self._fetch_plan()
        except Exception as e:
            self._log(journal, "busca_falhou", erro=str(e))
            self._avisar(journal,
                         f"[lab-autoupdate] ciclo {ciclo}: falha ao buscar o plano "
                         f"({e}); nada foi aplicado")
            return self._fechar_ciclo(CycleReport(
                ciclo=ciclo, estado=ESTADO_BUSCA_FALHOU, journal=journal,
                resumo=f"ciclo {ciclo}: busca do plano falhou; nada foi tocado"))

        if not plano:
            self._log(journal, "sem_plano")
            return self._fechar_ciclo(CycleReport(
                ciclo=ciclo, estado=ESTADO_SEM_PLANO, journal=journal,
                resumo=f"ciclo {ciclo}: sem plano; nada a fazer"))

        # 2. Filtrar mudancas reais (regra 2: nao publica ruido).
        mudancas: Dict[str, str] = {}
        for path in sorted(plano):
            if self._read(path) != plano[path]:
                mudancas[path] = plano[path]
        if not mudancas:
            self._log(journal, "sem_mudanca", arquivos=sorted(plano))
            self._avisar(journal,
                         f"[lab-autoupdate] ciclo {ciclo}: plano sem mudanca real "
                         f"({len(plano)} arquivo(s) identicos); ignorado")
            return self._fechar_ciclo(CycleReport(
                ciclo=ciclo, estado=ESTADO_SEM_MUDANCA,
                arquivos=sorted(plano), journal=journal,
                resumo=f"ciclo {ciclo}: plano sem mudanca real; nada publicado"))

        arquivos = sorted(mudancas)
        self._log(journal, "plano", arquivos=arquivos)

        # 3. Snapshot do estado original ANTES de qualquer escrita (portao).
        plano_snapshot = self._gate.propose(mudancas, journal)

        # 4. Aplicar.
        aplicados: List[str] = []
        try:
            for path in arquivos:
                self._apply(path, plano_snapshot[path]["novo"])
                aplicados.append(path)
                self._log(journal, "aplicado", arquivo=path)
        except Exception as e:
            prova = self._gate.rollback(plano_snapshot, aplicados, journal)
            self._avisar(journal,
                         f"[lab-autoupdate] ciclo {ciclo}: falha ao aplicar "
                         f"({e}); rollback executado")
            return self._fechar_ciclo(CycleReport(
                ciclo=ciclo, estado=ESTADO_REVERTIDO, arquivos=arquivos,
                revertido=True, prova_rollback=prova, journal=journal,
                resumo=f"ciclo {ciclo}: falha ao aplicar; rollback executado"))

        # 5. Gates (regra 3: vermelho ou explosao = volta atras).
        try:
            ok, detalhe = self._run_gates()
        except Exception as e:
            ok, detalhe = False, f"gate explodiu: {e}"
        self._log(journal, "verificacao", passou=ok, detalhe=detalhe)
        if not ok:
            prova = self._gate.rollback(plano_snapshot, aplicados, journal)
            ok_prova = prova["ok"] if prova else "n/a"
            self._avisar(journal,
                         f"[lab-autoupdate] ciclo {ciclo}: gates reprovaram "
                         f"({detalhe}) em {len(arquivos)} arquivo(s); revertido")
            return self._fechar_ciclo(CycleReport(
                ciclo=ciclo, estado=ESTADO_REVERTIDO, arquivos=arquivos,
                revertido=True, prova_rollback=prova, journal=journal,
                resumo=f"ciclo {ciclo}: gates reprovaram; rollback executado "
                       f"(prova: {ok_prova})"))

        # 6. Publicar sozinho — e se a publicacao falhar, volta atras (regra 4).
        self._log(journal, "publicando", arquivos=arquivos)
        msg = (f"lab: autoupdate ciclo {ciclo} "
               f"({len(arquivos)} arquivo(s): {', '.join(arquivos)})")
        try:
            publicou = self._publish(msg)
            erro_pub = "" if publicou else "publish retornou False"
        except Exception as e:
            publicou, erro_pub = False, str(e)
        if not publicou:
            prova = self._gate.rollback(plano_snapshot, aplicados, journal)
            self._avisar(journal,
                         f"[lab-autoupdate] ciclo {ciclo}: publicacao falhou "
                         f"({erro_pub}); codigo revertido, nada foi publicado")
            return self._fechar_ciclo(CycleReport(
                ciclo=ciclo, estado=ESTADO_REVERTIDO, arquivos=arquivos,
                revertido=True, prova_rollback=prova, journal=journal,
                resumo=f"ciclo {ciclo}: publicacao falhou; rollback executado, "
                       f"nada foi publicado"))

        self._log(journal, "publicado", arquivos=arquivos)
        return self._fechar_ciclo(CycleReport(
            ciclo=ciclo, estado=ESTADO_PUBLICADO, arquivos=arquivos,
            publicado=True, journal=journal,
            resumo=f"ciclo {ciclo}: {len(arquivos)} arquivo(s) publicados"))

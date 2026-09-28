"""Doutor do alicerce LAB VIVO — o portão de saúde da fundação.

Uso (a CEO, ou o Codex no passo 0 da GIGANTE 2 "LAB VIVO"):

    from core import lab_doctor
    d = lab_doctor.diagnosticar()
    print(lab_doctor.texto(d))   # SAUDÁVEL ou a lista do que quebrou

O que ele checa, em ordem de dependência:
  base:       lab_backlog, lab_report, lab_dropbox, lab_memory
  conversa:   lab_task_split
  custo:      lab_cost_ledger, lab_spend
  plano:      lab_ceo_plan, lab_seed_proposals
  motor:      lab_turn, lab_loop
  ciclo:      lab_cycle_brief, lab_ceo_decision
  publicação: autoupdate_gate, lab_autoupdate
  testes:     test_lab_seats_ping, test_lab_conversation_roundtrip,
              test_lab_vivo_integration (só importação)

Cada módulo passa por 3 portões: importa, expõe a API esperada e roda uma
fumaça (um exercício mínimo de verdade do contrato principal). Qualquer
portão que falha vira uma checagem vermelha com o motivo — o doutor nunca
esconde peça quebrada.

Lógica pura, stdlib, zero custo/rede/quota, sem chamar modelo nenhum.
O doutor é só leitura: não escreve no app, não muda estado de módulo
nenhum (as fumaças usam cópias em memória e pastas temporárias).
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Catálogo: (módulo, camada, descrição, API esperada, fumaça ou None)
# ---------------------------------------------------------------------------

def _fumaça_backlog(m, ctx):
    bl = m.LabBacklog(clock=lambda: "T-DOUTOR")
    it = bl.propose(title="Corrigir teste quebrado da voz",
                    description="fumaça do doutor",
                    proposed_by="ENGINEER", impact=5, urgency=4, cost=2)
    bl.approve(it.item_id, by="CEO")
    bl.claim(it.item_id, agent_id="TESTER")
    bl.complete(it.item_id, agent_id="TESTER", note="ok")
    if bl.get(it.item_id).state != m.BacklogState.DONE:
        raise AssertionError("não chegou em DONE")
    return "propor→aprovar→reivindicar→concluir OK"


def _fumaça_report(m, ctx):
    ok = m.Relatorio(tipo="PROGRESSO", feito=["fiz X"], estado=["estável"])
    if not ok.pode_falar():
        raise AssertionError("PROGRESSO válido não pode falar")
    ruim = m.Relatorio(tipo="BLOQUEIO", feito=["travei em Y"])
    if ruim.pode_falar():
        raise AssertionError("BLOQUEIO sem decisão pedida não pode falar")
    txt = ok.formatar()
    if "FEITO" not in txt or "ESTADO" not in txt:
        raise AssertionError("formatar() sem FEITO/ESTADO")
    return "portão do silêncio OK"


def _fumaça_dropbox(m, ctx):
    pasta = ctx["tmpdir"]("caixa")
    cx = m.Dropbox(pasta, clock=lambda: "T-DOUTOR")
    r = cx.depositar(de="CEO", para="ENGINEER", tipo="RECADO",
                     conteudo="ping do doutor")
    if len(cx.pendentes("ENGINEER")) != 1:
        raise AssertionError("recado não chegou")
    cx.reclamar(r.msg_id, por="ENGINEER")
    cx.responder(r.msg_id, de="ENGINEER", conteudo="pong do doutor")
    if len(cx.fio(r.msg_id)) != 2:
        raise AssertionError("fio quebrou")
    return "depositar→reclamar→responder OK"


def _fumaça_memory(m, ctx):
    mem = m.LabMemory(now=lambda: 1.0)
    mem.write("CEO", "doutor.ping", "pong")
    if mem.read("doutor.ping") != "pong":
        raise AssertionError("leitura não bateu")
    try:
        mem.write("ENGINEER", "doutor.ping", "outro")
    except m.MemoryDenied:
        return "fato com dono OK"
    raise AssertionError("outro assento sobrescreveu o fato")


def _fumaça_task_split(m, ctx):
    dom = ctx["importar"]("core.lab_v1.domain")
    mae = dom.Task(id="T-DOUTOR", session_id="S-DOUTOR", title="mãe",
                   instruction="i", created_by_agent_id="CEO",
                   assigned_agent_id="ENGINEER",
                   state=dom.TaskState.ASSIGNED,
                   budget_usd=1.0, max_turns=5)
    filhas = m.split_task(
        mae,
        [m.SplitPart(title="fatia 1", instruction="i1", acceptance="a1",
                     assigned_agent_id="ENGINEER",
                     budget_usd=0.4, max_turns=2)],
        splitter_agent_id="ENGINEER")
    if len(filhas) != 1 or filhas[0].budget_usd != 0.4:
        raise AssertionError("divisão não respeitou o budget")
    st, _ = m.parent_outcome(filhas)
    if st == dom.TaskState.COMPLETED:
        raise AssertionError("mãe completou com filha pendente")
    filhas[0].state = dom.TaskState.COMPLETED
    st, _ = m.parent_outcome(filhas)
    if st != dom.TaskState.COMPLETED:
        raise AssertionError("mãe não completou com filha pronta")
    return "dividir→agregar OK"


def _fumaça_ledger(m, ctx):
    lg = m.CostLedger(relogio=lambda: 1.0)
    lg.registrar(ciclo="C-DOUTOR", assento="CEO", tarefa="T1", usd="0")
    lg.registrar(ciclo="C-DOUTOR", assento="CEO", tarefa="T2", usd="0.1")
    lg.registrar(ciclo="C-DOUTOR", assento="CEO", tarefa="T3", usd="0.2")
    from decimal import Decimal
    if lg.gasto_total() != Decimal("0.3"):
        raise AssertionError("Decimal não fechou 0.1+0.2")
    return "livro-caixa exato OK"


def _fumaça_spend(m, ctx):
    lgm = ctx["dep"]("core.lab_cost_ledger")
    lg = lgm.CostLedger(relogio=lambda: 1.0)
    r1 = m.autorizar_gasto(lg, ciclo="C-DOUTOR", tarefa="T1",
                           pedido_usd="0.000001", teto_tarefa_usd="0.01")
    if r1["decisao"] != m.OK:
        raise AssertionError("gasto dentro do teto negado")
    r2 = m.autorizar_gasto(lg, ciclo="C-DOUTOR", tarefa="T1",
                           pedido_usd="1.00", teto_tarefa_usd="0.01")
    if r2["decisao"] != m.NEGADO:
        raise AssertionError("gasto acima do teto passou")
    return "teto consultado antes de gastar OK"


def _fumaça_ceo_plan(m, ctx):
    blm = ctx["dep"]("core.lab_backlog")
    bl = blm.LabBacklog(clock=lambda: "T-DOUTOR")
    it = bl.propose(title="Corrigir teste quebrado da voz",
                    description="fumaça do doutor",
                    proposed_by="ENGINEER", impact=5, urgency=5, cost=1)
    bl.approve(it.item_id, by="CEO")
    plano = m.CeoPlan(now=lambda: 1.0).build(bl, "C-DOUTOR")
    if not plano.entries or not all(e.seat for e in plano.entries):
        raise AssertionError("plano sem dono")
    donos = {e.seat for e in plano.entries}
    if len(donos) != len(plano.entries):
        raise AssertionError("dois donos na mesma tarefa")
    return "plano com um dono por tarefa OK"


def _fumaça_seed(m, ctx):
    blm = ctx["dep"]("core.lab_backlog")
    bl = blm.LabBacklog(clock=lambda: "T-DOUTOR")
    novos1 = m.seed(bl)
    novos2 = m.seed(bl)
    if len(novos1) != 8:
        raise AssertionError(f"esperava 8 propostas, vieram {len(novos1)}")
    if novos2:
        raise AssertionError("re-semeadura duplicou")
    if len(bl.plan_for_ceo()) != 8:
        raise AssertionError("backlog não tem as 8")
    return "8 propostas, sem duplicar OK"


def _fumaça_turn(m, ctx):
    blm = ctx["dep"]("core.lab_backlog")
    dbm = ctx["dep"]("core.lab_dropbox")
    bl = blm.LabBacklog(clock=lambda: "T-DOUTOR")
    it = bl.propose(title="Corrigir teste quebrado da voz",
                    description="fumaça do doutor",
                    proposed_by="ENGINEER", impact=5, urgency=5, cost=1)
    bl.approve(it.item_id, by="CEO")
    cx = dbm.Dropbox(ctx["tmpdir"]("caixa-turno"), clock=lambda: "T-DOUTOR")

    def worker(seat, order_text, c):
        return {"ok": True, "report": "FEITO: fiz X\nESTADO: estável"}

    out = m.LabTurn(now=lambda: 1.0).run(backlog=bl, dropbox=cx,
                                         worker=worker, cycle="C-DOUTOR")
    if out.completed < 1:
        raise AssertionError("turno não concluiu nada")
    return f"turno: {out.completed} concluída(s) OK"


def _fumaça_loop(m, ctx):
    blm = ctx["dep"]("core.lab_backlog")
    dbm = ctx["dep"]("core.lab_dropbox")
    bl = blm.LabBacklog(clock=lambda: "T-DOUTOR")
    cx = dbm.Dropbox(ctx["tmpdir"]("caixa-loop"), clock=lambda: "T-DOUTOR")
    loop = m.LabLoop(now=lambda: 1.0)
    rels = loop.run_until_idle(bl, cx,
                               worker=lambda *a, **k: {"ok": True},
                               max_cycles=3)
    if not rels or not rels[-1].idle:
        raise AssertionError("loop não ficou ocioso")
    if rels[-1].idle_reason != "NO_APPROVED_WORK":
        raise AssertionError(f"motivo errado: {rels[-1].idle_reason}")
    return "loop ocioso sem girar em falso OK"


def _fumaça_brief(m, ctx):
    txt = m.boletim_de_ciclos([], loop_state="RUNNING")
    if not txt.strip():
        raise AssertionError("boletim vazio")
    if len(txt.splitlines()) > 12:
        raise AssertionError("boletim estourou o teto")
    return "boletim de fila vazia OK"


def _fumaça_decision(m, ctx):
    reg = m.DecisionRegistry(clock=lambda: "T-DOUTOR")
    d = reg.registrar(m.DecisionType.RETOMAR, cycle=1,
                      motivo="retomar o loop de testes do doutor",
                      decidido_por="CEO")

    class LoopFalso:
        def __init__(self):
            self.retomado = False
        def resume(self):
            self.retomado = True
        def state(self):
            return "PAUSED"

    loop = LoopFalso()
    m.aplicar(d, loop, registry=reg)
    if not loop.retomado:
        raise AssertionError("RETOMAR não retomou")
    return "decisão RETOMAR aplicada OK"


def _fumaça_gate(m, ctx):
    arquivos = {"a.txt": "bom"}

    def _ler(p):
        return arquivos.get(p)

    def _aplicar(p, c):
        arquivos[p] = c

    def _remover(p):
        arquivos.pop(p, None)

    gate = m.AutoUpdateGate(read_fn=_ler, apply_fn=_aplicar,
                            remove_fn=_remover)
    v = gate.execute({"a.txt": "ruim"}, verify_fn=lambda: (False, "quebrou"))
    if not v.rolled_back:
        raise AssertionError("não voltou atrás")
    if arquivos.get("a.txt") != "bom":
        raise AssertionError("conteúdo não restaurado")
    return "snapshot→aplica→falha→rollback OK"


def _fumaça_autoupdate(m, ctx):
    arquivos = {"a.txt": "v1"}
    publicados = []

    pipe = m.AutoupdatePipeline(
        fetch_plan=lambda: {"a.txt": "v2"},
        read_fn=arquivos.get,
        apply_fn=lambda p, c: arquivos.__setitem__(p, c),
        remove_fn=lambda p: arquivos.pop(p, None),
        run_gates=lambda: (True, "ok"),
        publish=lambda nome: publicados.append(nome) or True,
        notify=lambda t: None)
    rel = pipe.run_once()
    if rel.estado != m.ESTADO_PUBLICADO:
        raise AssertionError(f"estado errado: {rel.estado}")
    if arquivos.get("a.txt") != "v2" or not publicados:
        raise AssertionError("não publicou de verdade")
    return "puxa→testa→publica OK"


MODULOS = [
    # base
    ("lab_backlog", "base", "backlog priorizado do Lab",
     ["LabBacklog", "BacklogState", "BacklogItem", "priority_score",
      "BacklogError"], _fumaça_backlog),
    ("lab_report", "base", "portão do modo silencioso",
     ["Relatorio", "analisar", "cortar_em_linhas"], _fumaça_report),
    ("lab_dropbox", "base", "caixinha de recados dos assentos",
     ["Dropbox", "Recado", "ASSENTOS", "TIPOS", "DropboxError"],
     _fumaça_dropbox),
    ("lab_memory", "base", "memória compartilhada com dono",
     ["LabMemory", "MemoryEntry", "MemoryDenied", "SEATS"], _fumaça_memory),
    # conversa
    ("lab_task_split", "conversa", "divisão de tarefa entre assentos",
     ["split_task", "complete_child", "fail_child", "parent_outcome",
      "SplitPart", "TaskSplitError"], _fumaça_task_split),
    # custo
    ("lab_cost_ledger", "custo", "livro-caixa de custo do Lab",
     ["CostLedger", "Lancamento", "LedgerError", "CASAS"], _fumaça_ledger),
    ("lab_spend", "custo", "caixa da operação (teto antes de gastar)",
     ["registrar_gasto", "autorizar_gasto", "fechar_ciclo",
      "linhas_para_boletim", "OK", "NEGADO"], _fumaça_spend),
    # plano
    ("lab_ceo_plan", "plano", "plano do turno da CEO",
     ["CeoPlan", "TurnPlan", "PlanEntry", "kind_for", "CEO", "PlanError"],
     _fumaça_ceo_plan),
    ("lab_seed_proposals", "plano", "primeiras propostas semeadas",
     ["seed", "seeded_keys", "seed_marker"], _fumaça_seed),
    # motor
    ("lab_turn", "motor", "motor do turno",
     ["LabTurn", "TurnOutcome", "TurnError"], _fumaça_turn),
    ("lab_loop", "motor", "condutor do loop contínuo",
     ["LabLoop", "CycleReport", "LoopError"], _fumaça_loop),
    # ciclo
    ("lab_cycle_brief", "ciclo", "boletim do ciclo da CEO",
     ["agregar", "montar_brief", "texto_brief", "boletim_de_ciclos",
      "ResumoCiclos", "BriefError"], _fumaça_brief),
    ("lab_ceo_decision", "ciclo", "decisão registrada da CEO",
     ["DecisionRegistry", "CeoDecision", "DecisionType", "decisao_valida",
      "aplicar", "resumir_para_boletim", "DecisionError"],
     _fumaça_decision),
    # publicação
    ("autoupdate_gate", "publicação", "portão de autoupdate seguro",
     ["AutoUpdateGate", "GateVerdict"], _fumaça_gate),
    ("lab_autoupdate", "publicação", "condutor do autoupdate",
     ["AutoupdatePipeline", "CycleReport", "ESTADO_PUBLICADO",
      "ESTADO_REVERTIDO", "ESTADO_SEM_PLANO"], _fumaça_autoupdate),
    # testes do alicerce (só importação: provam que existem e carregam)
    ("test_lab_seats_ping", "testes", "ping dos 11 assentos", [], None),
    ("test_lab_conversation_roundtrip", "testes", "roundtrip da conversa",
     [], None),
    ("test_lab_vivo_integration", "testes", "ensaio geral de integração",
     [], None),
]


# ---------------------------------------------------------------------------
# Diagnóstico
# ---------------------------------------------------------------------------

@dataclass
class Checagem:
    modulo: str
    camada: str
    ok: bool
    detalhe: str = ""


@dataclass
class Diagnostico:
    checagens: List[Checagem] = field(default_factory=list)
    raiz: str = ""
    pacote: str = ""

    @property
    def saudavel(self) -> bool:
        return bool(self.checagens) and all(c.ok for c in self.checagens)

    @property
    def falhas(self) -> List[Checagem]:
        return [c for c in self.checagens if not c.ok]

    def resumo(self) -> List[str]:
        """Linhas compactas, no teto do modo silencioso (máx 12)."""
        total = len(self.checagens)
        nfalhas = len(self.falhas)
        if self.saudavel:
            linhas = [f"DOUTOR LAB VIVO: SAUDÁVEL "
                       f"({total} checagens, 0 falhas)"]
            por_camada: Dict[str, int] = {}
            for c in self.checagens:
                por_camada[c.camada] = por_camada.get(c.camada, 0) + 1
            for camada, n in por_camada.items():
                linhas.append(f"  {camada}: {n} OK")
            return linhas[:12]
        linhas = [f"DOUTOR LAB VIVO: DOENTE ({nfalhas} falha(s) "
                   f"em {total} checagens)"]
        for f in self.falhas[:9]:
            linhas.append(f"  FALHA [{f.camada}] {f.modulo}: {f.detalhe}")
        if nfalhas > 9:
            linhas.append(f"  ... e mais {nfalhas - 9} falha(s)")
        return linhas[:12]


def texto(d: Diagnostico) -> str:
    """O boletim do doutor em texto."""
    return "\n".join(d.resumo())


def _resolver_raiz(raiz=None):
    """Devolve (pasta_pai, pacote). Aceita a raiz do app (contém core/)
    ou o próprio core/. Checa a ESTRUTURA (pastas), nunca um módulo
    específico — um módulo ausente é justamente o que o doutor acusa."""
    if raiz is None:
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raiz = os.path.abspath(str(raiz))
    if (os.path.isdir(os.path.join(raiz, "core")) and
            os.path.isdir(os.path.join(raiz, "core", "lab_v1"))):
        return raiz, "core."
    if os.path.isdir(os.path.join(raiz, "lab_v1")):
        return os.path.dirname(raiz), os.path.basename(raiz) + "."
    return None, None


def diagnosticar(raiz=None, journal: Optional[list] = None,
                 relogio: Callable[[], str] = None) -> Diagnostico:
    """Roda o check-up completo do alicerce. Devolve o Diagnostico."""
    import time as _time
    relogio = relogio or (lambda: _time.strftime("%Y-%m-%dT%H:%M:%S"))

    def _log(evento, **campos):
        if journal is not None:
            journal.append({"ts": relogio(), "evento": evento, **campos})

    pasta_pai, pacote = _resolver_raiz(raiz)
    diag = Diagnostico(raiz=str(raiz or ""), pacote=pacote or "")
    if pasta_pai is None:
        diag.checagens.append(Checagem(
            "raiz", "doutor", False,
            f"alicerce não encontrado em {raiz}"))
        _log("raiz_invalida", raiz=str(raiz))
        return diag

    _log("inicio", raiz=pasta_pai, pacote=pacote,
         modulos=len(MODULOS))
    # O doutor diagnostica os ARQUIVOS da raiz indicada: expulsa do
    # sys.modules qualquer importação anterior do mesmo pacote, senão
    # o Python devolveria o módulo velho em cache e a fumaça mentiria.
    prefixo = pacote  # ex.: "core."
    raiz_pacote = pacote.rstrip(".")
    for chave in [k for k in sys.modules
                  if k == raiz_pacote or k.startswith(prefixo)]:
        del sys.modules[chave]
    sys.path.insert(0, pasta_pai)
    try:
        modulos: Dict[str, Any] = {}
        tmp_base = Path(tempfile.mkdtemp(prefix="doutor-lab-vivo-"))
        n_tmp = [0]

        def _tmpdir(nome: str) -> Path:
            n_tmp[0] += 1
            p = tmp_base / f"{n_tmp[0]:02d}-{nome}"
            p.mkdir(parents=True, exist_ok=True)
            return p

        def _importar(nome: str):
            return importlib.import_module(nome)

        def _dep(nome: str):
            mod = modulos.get(nome)
            if mod is None:
                raise RuntimeError(f"dependência indisponível: {nome}")
            return mod

        ctx = {"tmpdir": _tmpdir, "importar": _importar,
               "modulos": modulos, "dep": _dep}

        for nome, camada, descricao, api, fumaça in MODULOS:
            chave = pacote + nome
            try:
                mod = _importar(chave)
            except Exception as e:  # noqa: BLE001 - o doutor relata, não crasha
                detalhe = f"IMPORT_ERROR: {type(e).__name__}: {e}"
                diag.checagens.append(Checagem(nome, camada, False,
                                               detalhe))
                _log("falha", modulo=nome, etapa="import",
                     detalhe=detalhe[:140])
                continue
            modulos[chave] = mod
            # Honestidade de origem: o arquivo importado TEM que ser o da
            # raiz indicada. (Pacote namespace junta porções de todo o
            # sys.path — sem esse portão, um módulo ausente aqui seria
            # silenciosamente carregado de outro lugar e a fumaça mentiria.)
            alvo_dir = os.path.realpath(os.path.join(pasta_pai, raiz_pacote))
            origem = os.path.realpath(getattr(mod, "__file__", ""))
            if not origem.startswith(alvo_dir + os.sep):
                detalhe = (f"IMPORT_ERROR: {nome} veio de fora da raiz "
                           f"({origem})")
                diag.checagens.append(Checagem(nome, camada, False,
                                               detalhe))
                _log("falha", modulo=nome, etapa="origem",
                     detalhe=detalhe[:140])
                del modulos[chave]
                continue
            faltando = [n for n in api if not hasattr(mod, n)]
            if faltando:
                detalhe = f"API_INCOMPLETA: faltam {faltando}"
                diag.checagens.append(Checagem(nome, camada, False,
                                               detalhe))
                _log("falha", modulo=nome, etapa="api",
                     detalhe=detalhe[:140])
                continue
            if fumaça is None:  # teste do alicerce: importar já é a prova
                diag.checagens.append(Checagem(nome, camada, True,
                                               "importa OK"))
                _log("ok", modulo=nome, etapa="import")
                continue
            try:
                detalhe = fumaça(mod, ctx) or "OK"
            except Exception as e:  # noqa: BLE001
                tb = traceback.format_exc(limit=3).strip().splitlines()
                causa = tb[-1] if tb else f"{type(e).__name__}: {e}"
                detalhe = f"FUMAÇA: {causa}"
                diag.checagens.append(Checagem(nome, camada, False,
                                               detalhe))
                _log("falha", modulo=nome, etapa="fumaça",
                     detalhe=detalhe[:140])
                continue
            diag.checagens.append(Checagem(nome, camada, True, detalhe))
            _log("ok", modulo=nome, etapa="fumaça")
    finally:
        if pasta_pai in sys.path:
            sys.path.remove(pasta_pai)

    _log("fim", saudavel=diag.saudavel,
         falhas=len(diag.falhas), total=len(diag.checagens))
    return diag

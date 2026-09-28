"""ENSAIO GERAL DO LAB VIVO (GIGANTE 2 "LAB VIVO" — prova de composição).

As peças do alicerce trabalhando JUNTAS num cenário só, de ponta a ponta,
sem chamar modelo nenhum (custo/rede/quota = zero):

  ENGINEER propõe uma melhoria no backlog
    -> a CEO aprova
    -> a CEO divide a tarefa entre ENGINEER e REVIEWER (budgets limitados)
    -> ENGINEER chama o REVIEWER pela caixinha; ele responde no mesmo fio
    -> cada um conclui a sua parte; a mãe completa com o resultado agregado
    -> o relatório de progresso passa no portão do modo silencioso
    -> o TESTER registra o fato na memória compartilhada (fato tem dono)
    -> o portão de autoupdate publica o update bom e volta atrás na sabotagem

Cada teste exercita 2+ peças juntas — é aqui que uma incompatibilidade
entre módulos apareceria. Lógica pura, stdlib apenas.
"""

from __future__ import annotations

import tempfile

import pytest

from core.autoupdate_gate import AutoUpdateGate
from core.lab_backlog import BacklogState, LabBacklog
from core.lab_dropbox import Dropbox, DropboxError
from core.lab_memory import LabMemory, MemoryDenied
from core.lab_report import BLOQUEIO, PROGRESSO, Relatorio
from core.lab_task_split import (
    SplitPart,
    TaskSplitError,
    complete_child,
    parent_outcome,
    split_task,
)
from core.lab_v1.domain import Task, TaskState


# ---------------------------------------------------------------- cenário
def _tarefa_mae() -> Task:
    """A tarefa que a CEO passou: implementar o rollback automático."""
    return Task(
        id="mae-rollback-01",
        session_id="sessao-ensaio-01",
        title="implementar rollback automático",
        instruction="fazer o portão voltar atrás sozinho quando o gate reprovar",
        created_by_agent_id="CEO",
        assigned_agent_id="CEO",
        state=TaskState.ASSIGNED,
        acceptance="gate verde + rollback provado por hash",
        max_turns=3,
        budget_usd=2.0,
    )


def _duas_filhas():
    mae = _tarefa_mae()
    filhas = split_task(
        mae,
        [
            SplitPart(
                title="codar o rollback",
                instruction="implementar snapshot + restore com prova por hash",
                acceptance="rollback restaura o conteúdo original",
                assigned_agent_id="ENGINEER",
                budget_usd=1.2,
                max_turns=2,
            ),
            SplitPart(
                title="revisar o rollback",
                instruction="conferir a prova por hash e os casos de borda",
                acceptance="nenhum caso de borda sem cobertura",
                assigned_agent_id="REVIEWER",
                budget_usd=0.5,
                max_turns=1,
            ),
        ],
        splitter_agent_id="CEO",
    )
    return mae, filhas


def _fs_gate():
    """Um 'disco' de mentira para o portão de autoupdate brincar."""
    disco = {"relatorio.txt": "versao antiga"}
    gate = AutoUpdateGate(
        read_fn=disco.get,
        apply_fn=lambda p, c: disco.__setitem__(p, c),
        remove_fn=lambda p: disco.pop(p, None),
    )
    return gate, disco


# ------------------------------------------------------------- Fase D + B
def test_01_backlog_ceo_aprova_e_tester_conclui():
    bl = LabBacklog(clock=lambda: "t0")
    item = bl.propose(
        title="rollback automático no autoupdate",
        description="se o gate reprovar depois de aplicar, voltar tudo sozinho",
        proposed_by="ENGINEER",
        impact=5,
        urgency=4,
        cost=2,
    )
    assert item.item_id == "BLG-0001"
    assert item.score == 5 * 3 + 4 * 2 - 2 * 2  # fórmula auditável: 19

    bl.approve(item.item_id, by="CEO")
    assert bl.get(item.item_id).state is BacklogState.APPROVED

    bl.claim(item.item_id, "TESTER")
    bl.complete(item.item_id, "TESTER", note="14/14 verdes")
    assert bl.get(item.item_id).state is BacklogState.DONE


def test_02_quem_nao_e_ceo_nao_aprova():
    bl = LabBacklog(clock=lambda: "t0")
    item = bl.propose(
        title="ideia qualquer", description="desc", proposed_by="ENGINEER",
        impact=3, urgency=3, cost=3,
    )
    with pytest.raises(Exception):
        bl.approve(item.item_id, by="ENGINEER")  # só a CEO aprova
    # o item segue proposto, visível no plano da CEO
    plano = bl.plan_for_ceo()
    assert [i.item_id for i in plano] == [item.item_id]


def test_03_split_duas_filhas_com_budget_limitado():
    mae, filhas = _duas_filhas()
    assert len(filhas) == 2
    # filhas herdam a missão e registram quem dividiu
    for f in filhas:
        assert f.session_id == mae.session_id == "sessao-ensaio-01"
        assert f.created_by_agent_id == "CEO"
        assert f.state is TaskState.ASSIGNED
    assert {f.assigned_agent_id for f in filhas} == {"ENGINEER", "REVIEWER"}
    # a soma dos budgets nunca passa do budget da mãe
    assert sum(f.budget_usd for f in filhas) <= mae.budget_usd


def test_04_split_que_estoura_o_budget_e_recusado():
    mae = _tarefa_mae()
    with pytest.raises(TaskSplitError):
        split_task(
            mae,
            [SplitPart(title="a", instruction="i", acceptance="a",
                       assigned_agent_id="ENGINEER", budget_usd=1.5),
             SplitPart(title="b", instruction="i", acceptance="a",
                       assigned_agent_id="REVIEWER", budget_usd=1.5)],
            splitter_agent_id="CEO",
        )  # 3.0 > 2.0: recusado antes de criar qualquer filha


# ------------------------------------------------------------- Fase A (caixinha)
def test_05_caixinha_engineer_chama_reviewer_no_fio():
    with tempfile.TemporaryDirectory() as pasta:
        caixa = Dropbox(pasta, clock=lambda: "t0")
        pergunta = caixa.depositar(
            de="ENGINEER",
            para="REVIEWER",
            tipo="PERGUNTA",
            conteudo="revisou a prova por hash do rollback?",
        )
        # o REVIEWER vê o recado pendente, reclama e responde no fio
        pendentes = caixa.pendentes("REVIEWER")
        assert [r.msg_id for r in pendentes] == [pergunta.msg_id]
        caixa.reclamar(pergunta.msg_id, "REVIEWER")
        resposta = caixa.responder(
            pergunta.msg_id, de="REVIEWER",
            conteudo="revisei: 14/14 verdes, nenhum caso de borda sem cobertura",
        )
        assert resposta.correlation_id == pergunta.msg_id
        fio = caixa.fio(pergunta.msg_id)
        assert [r.msg_id for r in fio] == [pergunta.msg_id, resposta.msg_id]


def test_06_recado_alheio_nao_pode_ser_lido():
    with tempfile.TemporaryDirectory() as pasta:
        caixa = Dropbox(pasta, clock=lambda: "t0")
        recado = caixa.depositar(de="ENGINEER", para="REVIEWER",
                                 tipo="RECADO", conteudo="só pro revisor")
        with pytest.raises(DropboxError):
            caixa.reclamar(recado.msg_id, "CEO")  # ninguém lê recado dos outros


# ------------------------------------------------------------- Fase B (conclusão)
def test_07_somente_o_responsavel_conclui_a_filha():
    _, filhas = _duas_filhas()
    filha_eng = next(f for f in filhas if f.assigned_agent_id == "ENGINEER")
    with pytest.raises(TaskSplitError):
        complete_child(filha_eng, result="pronto", by_agent_id="REVIEWER")
    complete_child(filha_eng, result="rollback codado, 14/14 verdes",
                   by_agent_id="ENGINEER")
    assert filha_eng.state is TaskState.COMPLETED


def test_08_mae_completa_quando_todas_as_filhas_concluem():
    _, filhas = _duas_filhas()
    for f in filhas:
        complete_child(f, result="ok", by_agent_id=f.assigned_agent_id)
    estado, resumo = parent_outcome(filhas)
    assert estado is TaskState.COMPLETED
    # o resultado agregado carrega as duas entregas
    assert "codar o rollback" in resumo or "revisar o rollback" in resumo


def test_09_filha_que_falha_derruba_a_mae_com_motivo():
    from core.lab_task_split import fail_child

    _, filhas = _duas_filhas()
    filha_eng = next(f for f in filhas if f.assigned_agent_id == "ENGINEER")
    filha_rev = next(f for f in filhas if f.assigned_agent_id == "REVIEWER")
    complete_child(filha_eng, result="ok", by_agent_id="ENGINEER")
    fail_child(filha_rev, reason="achei um caso de borda sem cobertura",
               by_agent_id="REVIEWER")
    estado, resumo = parent_outcome(filhas)
    assert estado is TaskState.FAILED
    assert "caso de borda" in resumo


# ------------------------------------------------------------- modo silencioso
def test_10_relatorio_de_progresso_passa_no_portao():
    rel = Relatorio(
        tipo=PROGRESSO,
        feito=["rollback codado e revisado", "14/14 testes verdes"],
        estado=["mãe completa, resultado agregado no disco"],
        erro=[],
        sugestao=["ligar a flag do roteador na próxima"],
    )
    assert rel.pode_falar()
    texto = rel.formatar()
    assert "FEITO" in texto and "rollback codado" in texto


def test_11_bloqueio_sem_dizer_a_decisao_nao_fala():
    rel = Relatorio(tipo=BLOQUEIO, feito=[], estado=["travei no gate"],
                    erro=["hash não bate"], sugestao=[])
    violacoes = rel.validar()
    assert any("decisão" in v for v in violacoes)
    assert not rel.pode_falar()


# ------------------------------------------------------------- memória compartilhada
def test_12_fato_tem_dono_na_memoria():
    mem = LabMemory(now=lambda: 1.0)
    mem.write("TESTER", "rollback.testado", "verde em 14/14")
    assert mem.read("rollback.testado") == "verde em 14/14"
    # outro assento não pisa no fato alheio
    with pytest.raises(MemoryDenied):
        mem.write("ENGINEER", "rollback.testado", "mudei de ideia")
    # a CEO pode corrigir
    mem.write("CEO", "rollback.testado", "verde em 14/14, confirmado pela CEO")
    historico = mem.history("rollback.testado")
    assert [l.op for l in historico] == ["WRITE", "WRITE"]
    assert mem.provenance("rollback.testado")["seat"] == "CEO"


# ------------------------------------------------------------- Fase C (portão)
def test_13_update_bom_e_publicado():
    gate, disco = _fs_gate()
    veredito = gate.execute(
        {"relatorio.txt": "versao nova: rollback automático pronto"},
        verify_fn=lambda: (True, "14/14 testes verdes"),
    )
    assert veredito.approved and not veredito.rolled_back
    assert disco["relatorio.txt"] == "versao nova: rollback automático pronto"


def test_14_sabotagem_nao_publica_e_volta_atras():
    gate, disco = _fs_gate()
    veredito = gate.execute(
        {"relatorio.txt": "versao SABOTADA"},
        verify_fn=lambda: (False, "teste quebrou: hash não bate"),
    )
    assert not veredito.approved and veredito.rolled_back
    # o conteúdo original foi restaurado (prova por hash no journal)
    assert disco["relatorio.txt"] == "versao antiga"
    eventos = [j["evento"] for j in veredito.journal]
    assert "snapshot" in eventos and "rollback" in eventos

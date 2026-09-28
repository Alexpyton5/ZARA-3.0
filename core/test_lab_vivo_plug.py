# -*- coding: utf-8 -*-
"""Testes do plug do Lab Vivo — as peças do alicerce trabalhando de verdade.

GIGANTE 2 "LAB VIVO". Estes testes ESTENDEM os testes do alicerce
(não os substituem): aqui o worker é REAL (disco de verdade), a
caixinha é REAL (pasta de verdade) e a tarefa dividida termina com
arquivo no disco.
"""

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.lab_autoupdate import AutoupdatePipeline  # noqa: E402
from core.lab_backlog import BacklogState, LabBacklog  # noqa: E402
from core.lab_dropbox import Dropbox  # noqa: E402
from core.lab_turn import LabTurn  # noqa: E402
from core.lab_workers import (  # noqa: E402
    SEAT_ORDER,
    SEAT_ROLES,
    worker_vivo_factory,
)

# ---------------------------------------------------------------------------
# Fase A — ping do protocolo: os 11 assentos respondem pela caixinha
# ---------------------------------------------------------------------------


def test_onze_assentos_tem_papel_escrito():
    assert len(SEAT_ROLES) == 11
    assert list(SEAT_ROLES) == SEAT_ORDER
    for assento, papel in SEAT_ROLES.items():
        assert isinstance(papel, str) and len(papel) >= 10, assento


def test_ping_protocolo_onze_assentos_respondem(tmp_path):
    """CEO pinga cada assento pela caixinha real; todos respondem no fio."""
    box = Dropbox(tmp_path / "caixinha")
    pings = []
    for assento in SEAT_ORDER:
        if assento == "CEO":
            continue
        recado = box.depositar(de="CEO", para=assento, tipo="PERGUNTA",
                               conteudo="PING: você está ouvindo?",
                               correlation_id=f"ping-{assento}")
        box.reclamar(recado.msg_id, assento)
        box.responder(recado.msg_id, assento, "PONG: ouvindo e pronto")
        pings.append((assento, recado.msg_id))
    for assento, msg_id in pings:
        fio = box.fio(msg_id)
        tipos = [m.tipo for m in fio]
        assert "PERGUNTA" in tipos and "RESPOSTA" in tipos, assento
        assert any("PONG" in m.conteudo for m in fio), assento


# ---------------------------------------------------------------------------
# Fase B — tarefa dividida de verdade, com arquivo no disco
# ---------------------------------------------------------------------------

ORDEM_MAE = (
    "ESCREVER relatorio-turno.txt\n"
    "Relatório do turno vivo.\n"
    "Os bots conversaram pela caixinha e executaram de verdade.\n"
    'DIVIDIR-PARA TESTER: CHECAR relatorio-turno.txt CONTEM executaram de verdade'
)


def test_tarefa_dividida_executa_de_verdade(tmp_path):
    """Mãe no ENGINEER/ARCHITECT escreve; filha no TESTER checa no disco."""
    work = tmp_path / "work"
    box = Dropbox(tmp_path / "caixinha")
    backlog = LabBacklog(clock=lambda: "T-PLUG")
    item = backlog.propose(
        title="Bot redator: escrever relatório do turno no disco",
        description=ORDEM_MAE,
        proposed_by="CEO", impact=4, urgency=4, cost=2)
    backlog.approve(item.item_id, by="CEO")
    worker = worker_vivo_factory(work, backlog)
    turno = LabTurn()
    saida = turno.run(backlog=backlog, dropbox=box, worker=worker,
                      cycle="plug-b", budget_usd=1.0, max_splits=3)
    assert backlog.get(item.item_id).state == BacklogState.DONE, \
        f"mae nao chegou em DONE: {saida}"
    alvo = work / "relatorio-turno.txt"
    assert alvo.exists(), "arquivo da prova real não existe no disco"
    assert "executaram de verdade" in alvo.read_text(encoding="utf-8")
    # a conversa bot<->bot passou pela caixinha de verdade
    eventos = box.journal()
    depositados = [e for e in eventos if e.get("evento") == "depositar"]
    tipos = {e.get("tipo") for e in depositados}
    assert "RECADO" in tipos  # ordens da CEO e das partes
    assert "RESPOSTA" in tipos  # respostas no fio
    assert any(e.get("para") == "TESTER" for e in depositados)


# ---------------------------------------------------------------------------
# Fase C — sabotagem não publica; rollback provado por hash
# ---------------------------------------------------------------------------


def _sandbox(tmp_path):
    alvo = tmp_path / "alvo"
    alvo.mkdir()
    (alvo / "app.txt").write_text("versao boa 1", encoding="utf-8")

    def ler(caminho):
        p = alvo / caminho
        return p.read_text(encoding="utf-8") if p.exists() else None

    def aplicar(caminho, conteudo):
        (alvo / caminho).write_text(conteudo, encoding="utf-8")

    def remover(caminho):
        p = alvo / caminho
        if p.exists():
            p.unlink()

    return alvo, ler, aplicar, remover


def test_sabotagem_nao_publica_e_rollback_eh_provado(tmp_path):
    alvo, ler, aplicar, remover = _sandbox(tmp_path)
    antes = hashlib.sha256((alvo / "app.txt").read_bytes()).hexdigest()
    plano = {"app.txt": "versao QUEBRADA <<< syntax !!! error"}
    pipe = AutoupdatePipeline(
        fetch_plan=lambda: dict(plano),
        read_fn=ler, apply_fn=aplicar, remove_fn=remover,
        run_gates=lambda: (False, "gate: conteúdo com marcador de quebra"),
        publish=lambda _rel: True,
        notify=lambda _txt: None,
    )
    rel = pipe.run_once()
    assert rel.publicado is False
    depois = hashlib.sha256((alvo / "app.txt").read_bytes()).hexdigest()
    assert antes == depois, "rollback falhou: arquivo mudou!"
    assert (alvo / "app.txt").read_text(encoding="utf-8") == "versao boa 1"


def test_update_bom_passa_no_gate_e_publica(tmp_path):
    alvo, ler, aplicar, remover = _sandbox(tmp_path)
    publicado = {}

    def publicar(rel_txt):
        publicado["ok"] = True
        (tmp_path / "publicado.txt").write_text("app.txt", encoding="utf-8")
        return True

    plano = {"app.txt": "versao boa 2"}
    pipe = AutoupdatePipeline(
        fetch_plan=lambda: dict(plano),
        read_fn=ler, apply_fn=aplicar, remove_fn=remover,
        run_gates=lambda: (True, "gate: conteúdo íntegro"),
        publish=publicar,
        notify=lambda _txt: None,
    )
    rel = pipe.run_once()
    assert rel.publicado is True
    assert publicado.get("ok") is True
    assert (alvo / "app.txt").read_text(encoding="utf-8") == "versao boa 2"


# ---------------------------------------------------------------------------
# Loop contínuo — aprova e executa até a fila esvaziar
# ---------------------------------------------------------------------------


def test_loop_continuo_executa_ate_esvaziar(tmp_path):
    from core.lab_vivo import LabVivo

    vivo = LabVivo(tmp_path)
    vivo.estado.mkdir(parents=True, exist_ok=True)
    for d in (vivo.dir_caixinha, vivo.dir_work):
        d.mkdir(parents=True, exist_ok=True)
    tarefas = [
        ("Testar escrita do arquivo um", "ESCREVER t1.txt\nconteudo um"),
        ("Testar escrita do arquivo dois", "ESCREVER t2.txt\nconteudo dois"),
    ]
    for titulo, desc in tarefas:
        it = vivo.backlog.propose(title=titulo, description=desc,
                                  proposed_by="CEO", impact=5, urgency=5, cost=1)
        assert it.state == BacklogState.PROPOSED
    rels = vivo.rodar_ate_ocioso(max_cycles=4)
    assert len(rels) >= 2, "o loop deveria rodar um ciclo por tarefa"
    assert all(r.failed == 0 for r in rels)
    estados = {i.state for i in vivo.backlog.ranked()}
    assert estados == {BacklogState.DONE}, estados
    assert (vivo.dir_work / "t1.txt").exists()
    assert (vivo.dir_work / "t2.txt").exists()


# ---------------------------------------------------------------------------
# Fase D — backlog: só a CEO aprova; proposta vira tarefa
# ---------------------------------------------------------------------------


def test_so_a_ceo_aprova_e_item_vira_tarefa():
    backlog = LabBacklog(clock=lambda: "T-PLUG")
    item = backlog.propose(title="Melhoria: documentar o protocolo dos bots",
                           description="Fase D do Lab Vivo",
                           proposed_by="ENGINEER", impact=3, urgency=3, cost=1)
    with pytest.raises(Exception):
        backlog.approve(item.item_id, by="ENGINEER")
    backlog.approve(item.item_id, by="CEO")
    assert backlog.get(item.item_id).state == BacklogState.APPROVED
    assert backlog.get(item.item_id).claimed_by is None  # um dono por vez

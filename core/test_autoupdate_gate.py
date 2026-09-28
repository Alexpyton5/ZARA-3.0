"""Testes do portão de autoupdate seguro (core/autoupdate_gate.py).

Provam a mecânica da Fase C da MISSÃO GIGANTE 2 "LAB VIVO" sem chamar modelo
nenhum e sem tocar no disco de verdade: o "mundo real" aqui é um dicionário
em memória. O Codex roda este arquivo na suíte; a zoe já rodou localmente
contra o módulo REAL do app.
"""

import pytest

from autoupdate_gate import AutoUpdateGate, GateVerdict, _sha256


class FakeFS:
    """Mundo real de mentira: um dict fingindo ser o disco."""

    def __init__(self, inicial=None):
        self.arquivos = dict(inicial or {})
        self.ordem_aplicacao = []

    def read(self, path):
        return self.arquivos.get(path)

    def apply(self, path, content):
        self.arquivos[path] = content
        self.ordem_aplicacao.append(path)

    def remove(self, path):
        self.arquivos.pop(path, None)


def make_gate(fs):
    return AutoUpdateGate(fs.read, fs.apply, fs.remove)


def gate_ok():
    return (True, "todos os gates verdes")


def gate_falha():
    return (False, "teste X quebrou")


# 1. plano vazio é recusado
def test_plano_vazio_recusado():
    fs, gate = FakeFS(), make_gate(FakeFS())
    v = gate.execute({}, gate_ok)
    assert isinstance(v, GateVerdict)
    assert v.approved is False and v.rolled_back is False
    assert "vazio" in v.detail


# 2. caminho feliz: aplica e aprova, journal registra hashes
def test_caminho_feliz_aprova():
    fs = FakeFS({"a.py": "velho"})
    v = make_gate(fs).execute({"a.py": "novo"}, gate_ok)
    assert v.approved is True and v.rolled_back is False
    assert fs.read("a.py") == "novo"
    snaps = [e for e in v.journal if e["evento"] == "snapshot"]
    assert snaps[0]["hash_antes"] == _sha256("velho")
    assert "aprovado" in v.detail


# 3. gate reprovou -> rollback restaura o original idêntico
def test_gate_falhou_restaura_original():
    fs = FakeFS({"a.py": "velho", "b.py": "velho-b"})
    v = make_gate(fs).execute({"a.py": "novo", "b.py": "novo-b"}, gate_falha)
    assert v.approved is False and v.rolled_back is True
    assert fs.read("a.py") == "velho"
    assert fs.read("b.py") == "velho-b"


# 4. a prova do rollback: hash depois == hash do snapshot
def test_rollback_provado_por_hash():
    fs = FakeFS({"a.py": "velho"})
    v = make_gate(fs).execute({"a.py": "novo"}, gate_falha)
    rbs = [e for e in v.journal if e["evento"] == "rollback"]
    assert len(rbs) == 1 and rbs[0]["prova_hash"] is True


# 5. rollback desfaz na ordem reversa da aplicação
def test_rollback_ordem_reversa():
    fs = FakeFS({"1.py": "v1", "2.py": "v2", "3.py": "v3"})
    ordem_rb = []
    orig_remove = fs.remove
    gate = AutoUpdateGate(fs.read, fs.apply, fs.remove)
    # espiona a ordem do rollback pelo journal
    v = gate.execute({"1.py": "n1", "2.py": "n2", "3.py": "n3"}, gate_falha)
    rbs = [e["arquivo"] for e in v.journal if e["evento"] == "rollback"]
    assert rbs == ["3.py", "2.py", "1.py"]
    # a ordem de aplicação inclui o restore do rollback (que também escreve):
    # aplica 1,2,3 e restaura 3,2,1
    assert fs.ordem_aplicacao == ["1.py", "2.py", "3.py", "3.py", "2.py", "1.py"]


# 6. arquivo que não existia volta a não existir (sem lixo)
def test_arquivo_novo_some_no_rollback():
    fs = FakeFS({"a.py": "velho"})
    v = make_gate(fs).execute({"a.py": "novo", "novo.py": "criado"}, gate_falha)
    assert v.rolled_back is True
    assert fs.read("novo.py") is None
    assert fs.read("a.py") == "velho"


# 7. apply quebra no meio -> o que já aplicou volta atrás
def test_apply_quebra_no_meio_desfaz():
    fs = FakeFS({"a.py": "va", "b.py": "vb"})

    def apply_quebradiço(path, content):
        if path == "b.py":
            raise OSError("disco cheio (simulado)")
        fs.apply(path, content)

    gate = AutoUpdateGate(fs.read, apply_quebradiço, fs.remove)
    v = gate.execute({"a.py": "na", "b.py": "nb"}, gate_ok)
    assert v.approved is False and v.rolled_back is True
    assert fs.read("a.py") == "va"  # o que aplicou antes da quebra voltou
    assert fs.read("b.py") == "vb"  # o que quebrou nem saiu do lugar


# 8. gate que explode conta como gate que falhou -> rollback
def test_gate_que_explode_da_rollback():
    fs = FakeFS({"a.py": "velho"})

    def verify_boom():
        raise RuntimeError("gate travou")

    v = make_gate(fs).execute({"a.py": "novo"}, verify_boom)
    assert v.approved is False and v.rolled_back is True
    assert fs.read("a.py") == "velho"
    assert "explodiu" in v.journal[-2]["detalhe"] or any(
        "explodiu" in str(e.get("detalhe", "")) for e in v.journal)


# 9. journal é auditável: tem snapshot, aplicação, verificação e rollback
def test_journal_auditoria_completa():
    fs = FakeFS({"a.py": "velho"})
    v = make_gate(fs).execute({"a.py": "novo"}, gate_falha)
    eventos = [e["evento"] for e in v.journal]
    assert eventos == ["snapshot", "aplicado", "verificacao", "rollback"]
    assert all("ts" in e for e in v.journal)


# 10. dois updates seguidos: o segundo parte do estado do primeiro
def test_updates_sequenciais():
    fs = FakeFS({"a.py": "v1"})
    gate = make_gate(fs)
    v1 = gate.execute({"a.py": "v2"}, gate_ok)
    assert v1.approved and fs.read("a.py") == "v2"
    v2 = gate.execute({"a.py": "v3"}, gate_falha)
    assert v2.rolled_back and fs.read("a.py") == "v2"  # volta p/ v2, não p/ v1


# 11. rollback manual sem snapshot prévio não inventa nada
def test_rollback_sem_plano_nao_faz_nada():
    fs = FakeFS({"a.py": "velho"})
    gate = make_gate(fs)
    journal = []
    prova = gate.rollback({}, [], journal)
    assert prova["ok"] is True and prova["arquivos"] == {}
    assert fs.read("a.py") == "velho"


# 12. hashes no journal batem com o conteúdo real
def test_hashes_do_journal_conferem():
    fs = FakeFS({"a.py": "conteudo-xyz"})
    v = make_gate(fs).execute({"a.py": "outro-conteudo"}, gate_ok)
    snap = next(e for e in v.journal if e["evento"] == "snapshot")
    aplic = next(e for e in v.journal if e["evento"] == "aplicado")
    assert snap["hash_antes"] == _sha256("conteudo-xyz")
    assert aplic["hash_depois"] == _sha256("outro-conteudo")


# 13. detalhe do veredito carrega o motivo da reprovação
def test_veredito_carrega_motivo():
    fs = FakeFS({"a.py": "velho"})
    v = make_gate(fs).execute({"a.py": "novo"}, gate_falha)
    assert "teste X quebrou" in v.detail


# 14. update aprovado não deixa rastro de rollback no journal
def test_aprovado_sem_rollback():
    fs = FakeFS({"a.py": "velho"})
    v = make_gate(fs).execute({"a.py": "novo"}, gate_ok)
    assert not any(e["evento"] == "rollback" for e in v.journal)

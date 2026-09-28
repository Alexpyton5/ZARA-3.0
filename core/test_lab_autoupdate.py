"""Testes do pipeline de autoupdate do Lab Vivo (Fase C).

Roda contra o autoupdate_gate.py REAL do app (primitiva do portao),
com sistema de arquivos, gates, publish e relogio falsos injetados.
Custo/rede/quota: zero.
"""

try:
    from core.autoupdate_gate import AutoUpdateGate  # noqa: F401 (prova que o portao existe)
    from core.lab_autoupdate import (
        AutoupdatePipeline, CycleReport,
        ESTADO_SEM_PLANO, ESTADO_BUSCA_FALHOU, ESTADO_SEM_MUDANCA,
        ESTADO_PUBLICADO, ESTADO_REVERTIDO,
    )
except ImportError:  # layout flat
    from autoupdate_gate import AutoUpdateGate  # noqa: F401
    from lab_autoupdate import (
        AutoupdatePipeline, CycleReport,
        ESTADO_SEM_PLANO, ESTADO_BUSCA_FALHOU, ESTADO_SEM_MUDANCA,
        ESTADO_PUBLICADO, ESTADO_REVERTIDO,
    )


class FakeFS:
    """Arquivos falsos em memoria."""

    def __init__(self, inicial=None, falha_no_apply=None):
        self.arquivos = dict(inicial or {})
        self.falha_no_apply = falha_no_apply  # path que explode ao aplicar
        self.escritas = []

    def read(self, path):
        return self.arquivos.get(path)

    def apply(self, path, content):
        if path == self.falha_no_apply:
            raise RuntimeError(f"disco cheio ao escrever {path}")
        self.arquivos[path] = content
        self.escritas.append(path)

    def remove(self, path):
        self.arquivos.pop(path, None)


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        self.t += 1.0
        return self.t


def montar(fs, plano="PLANO", gates=(True, "tudo verde"), publish_ok=True,
            publish_raise=False, gates_raise=False, fetch_raise=False):
    """Monta o pipeline com as pecas falsas. Devolve (pipeline, espiões)."""
    espião = {"notify": [], "publish": [], "gates_chamado": 0}
    clock = FakeClock()

    def fetch_plan():
        if fetch_raise:
            raise RuntimeError("git pull falhou")
        return plano

    def run_gates():
        espião["gates_chamado"] += 1
        if gates_raise:
            raise RuntimeError("pytest travou")
        return gates

    def publish(msg):
        espião["publish"].append(msg)
        if publish_raise:
            raise RuntimeError("git push recusado")
        return publish_ok

    def notify(texto):
        espião["notify"].append(texto)

    pipe = AutoupdatePipeline(
        fetch_plan=fetch_plan,
        read_fn=fs.read, apply_fn=fs.apply, remove_fn=fs.remove,
        run_gates=run_gates, publish=publish, notify=notify, now=clock,
    )
    return pipe, espião


# -- sem plano: nada e tocado ---------------------------------------------

def test_sem_plano_none():
    fs = FakeFS({"a.py": "velho"})
    pipe, esp = montar(fs, plano=None)
    rel = pipe.run_once()
    assert rel.estado == ESTADO_SEM_PLANO
    assert fs.arquivos == {"a.py": "velho"}
    assert esp["notify"] == [] and esp["publish"] == [] and esp["gates_chamado"] == 0


def test_plano_vazio():
    fs = FakeFS({"a.py": "velho"})
    pipe, esp = montar(fs, plano={})
    rel = pipe.run_once()
    assert rel.estado == ESTADO_SEM_PLANO
    assert fs.arquivos == {"a.py": "velho"}
    assert esp["publish"] == []


def test_busca_falhou():
    fs = FakeFS({"a.py": "velho"})
    pipe, esp = montar(fs, fetch_raise=True)
    rel = pipe.run_once()
    assert rel.estado == ESTADO_BUSCA_FALHOU
    assert fs.arquivos == {"a.py": "velho"}  # nada tocado
    assert len(esp["notify"]) == 1
    assert "velho" not in esp["notify"][0]  # regra 5: sem conteudo no aviso


# -- plano sem mudanca real ------------------------------------------------

def test_sem_mudanca_real():
    fs = FakeFS({"a.py": "igual", "b.py": "igual"})
    pipe, esp = montar(fs, plano={"a.py": "igual", "b.py": "igual"})
    rel = pipe.run_once()
    assert rel.estado == ESTADO_SEM_MUDANCA
    assert esp["publish"] == [] and esp["gates_chamado"] == 0
    assert fs.arquivos == {"a.py": "igual", "b.py": "igual"}


def test_mudanca_parcial_filtra_identicos():
    fs = FakeFS({"a.py": "velho", "b.py": "igual"})
    pipe, esp = montar(fs, plano={"a.py": "novo", "b.py": "igual"})
    rel = pipe.run_once()
    assert rel.estado == ESTADO_PUBLICADO
    assert rel.arquivos == ["a.py"]  # o identico nem entrou no ciclo
    assert fs.arquivos == {"a.py": "novo", "b.py": "igual"}


# -- caminho feliz ----------------------------------------------------------

def test_caminho_feliz_publica():
    fs = FakeFS({"a.py": "velho", "b.py": "velho"})
    pipe, esp = montar(fs, plano={"a.py": "novo", "b.py": "novo"})
    rel = pipe.run_once()
    assert rel.estado == ESTADO_PUBLICADO
    assert rel.publicado and not rel.revertido
    assert fs.arquivos == {"a.py": "novo", "b.py": "novo"}
    assert len(esp["publish"]) == 1
    assert "ciclo 1" in esp["publish"][0] and "a.py" in esp["publish"][0]
    eventos = [e["evento"] for e in rel.journal]
    for esperado in ("ciclo_inicio", "plano", "snapshot", "aplicado",
                     "verificacao", "publicando", "publicado"):
        assert esperado in eventos, f"faltou {esperado} no journal: {eventos}"


# -- gates vermelhos: volta atras ------------------------------------------

def test_gates_vermelhos_revertem():
    fs = FakeFS({"a.py": "velho"})
    pipe, esp = montar(fs, plano={"a.py": "novo"}, gates=(False, "3 testes falharam"))
    rel = pipe.run_once()
    assert rel.estado == ESTADO_REVERTIDO
    assert rel.revertido and not rel.publicado
    assert fs.arquivos == {"a.py": "velho"}  # restaurado
    assert esp["publish"] == []  # publica SO depois de verde
    assert rel.prova_rollback is not None and rel.prova_rollback["ok"] is True
    assert len(esp["notify"]) == 1 and "gates" in esp["notify"][0]


def test_gates_explodem_fail_closed():
    fs = FakeFS({"a.py": "velho"})
    pipe, esp = montar(fs, plano={"a.py": "novo"}, gates_raise=True)
    rel = pipe.run_once()
    assert rel.estado == ESTADO_REVERTIDO
    assert fs.arquivos == {"a.py": "velho"}
    assert esp["publish"] == []
    assert rel.prova_rollback["ok"] is True


def test_arquivo_novo_some_no_rollback():
    fs = FakeFS({})
    pipe, esp = montar(fs, plano={"novo.py": "conteudo"}, gates=(False, "quebrou"))
    rel = pipe.run_once()
    assert rel.estado == ESTADO_REVERTIDO
    assert "novo.py" not in fs.arquivos  # sem lixo
    assert rel.prova_rollback["ok"] is True


# -- publish falha depois dos gates verdes -----------------------------------

def test_publish_falso_reverte():
    fs = FakeFS({"a.py": "velho"})
    pipe, esp = montar(fs, plano={"a.py": "novo"}, publish_ok=False)
    rel = pipe.run_once()
    assert rel.estado == ESTADO_REVERTIDO
    assert fs.arquivos == {"a.py": "velho"}  # codigo local voltou
    assert rel.prova_rollback["ok"] is True
    assert any("publicacao" in n for n in esp["notify"])


def test_publish_explode_reverte():
    fs = FakeFS({"a.py": "velho"})
    pipe, esp = montar(fs, plano={"a.py": "novo"}, publish_raise=True)
    rel = pipe.run_once()
    assert rel.estado == ESTADO_REVERTIDO
    assert fs.arquivos == {"a.py": "velho"}
    assert rel.prova_rollback["ok"] is True


# -- apply quebra no meio -----------------------------------------------------

def test_apply_quebra_no_meio():
    fs = FakeFS({"a.py": "velho", "b.py": "velho"}, falha_no_apply="b.py")
    pipe, esp = montar(fs, plano={"a.py": "novo", "b.py": "novo"})
    rel = pipe.run_once()
    assert rel.estado == ESTADO_REVERTIDO
    assert fs.arquivos == {"a.py": "velho", "b.py": "velho"}
    assert esp["gates_chamado"] == 0 and esp["publish"] == []
    assert rel.prova_rollback["ok"] is True


# -- ciclos sequenciais + historico --------------------------------------------

def test_dois_ciclos_sequenciais():
    fs = FakeFS({"a.py": "v1"})
    planos = [{"a.py": "v2"}, {"a.py": "v3"}]
    pipe, esp = montar(fs, plano=planos[0])
    r1 = pipe.run_once()
    pipe._fetch_plan = lambda: planos[1]
    r2 = pipe.run_once()
    assert (r1.estado, r2.estado) == (ESTADO_PUBLICADO, ESTADO_PUBLICADO)
    assert (r1.ciclo, r2.ciclo) == (1, 2)
    assert fs.arquivos == {"a.py": "v3"}  # segundo aplicou sobre o primeiro
    assert [r.ciclo for r in pipe.history()] == [1, 2]


# -- regra 5: notify nunca vaza conteudo -----------------------------------------

def test_notify_nunca_tem_conteudo():
    conteudos = ["SEGREDO_DO_ARQUIVO_XYZ", "novo", "velho"]
    fs = FakeFS({"a.py": "velho"})
    for kwargs in ({"gates": (False, "x")}, {"publish_ok": False},
                   {"fetch_raise": True}, {}):
        pipe, esp = montar(fs, plano={"a.py": "novo"}, **kwargs)
        pipe.run_once()
        for texto in esp["notify"]:
            for segredo in conteudos:
                assert segredo not in texto, f"vazou conteudo no notify: {texto}"


# -- journal com relogio injetavel --------------------------------------------------

def test_journal_usa_relogio_injetavel():
    fs = FakeFS({"a.py": "velho"})
    pipe, esp = montar(fs, plano={"a.py": "novo"})
    rel = pipe.run_once()
    ts = [e["ts"] for e in rel.journal if e["evento"] in
          ("ciclo_inicio", "plano", "aplicado", "verificacao", "publicando", "publicado")]
    assert ts == sorted(ts) and len(set(ts)) == len(ts)  # crescente, sem repetir
    assert all(t >= 1000.0 for t in ts)  # veio do FakeClock, nao do relogio real

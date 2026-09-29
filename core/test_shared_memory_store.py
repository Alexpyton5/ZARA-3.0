"""Testes da peca 2 da memoria compartilhada: o store le as fontes reais.

Padrao da casa: unittest, roda no pytest do .venv do PC.
"""
import unittest

from core.lab_memory import LabMemory
from core.shared_memory_spec import (
    SharedEntry,
    SharedMemoryError,
    SharedMemorySpec,
    from_dict,
)
from core.shared_memory_store import (
    SharedMemoryStore,
    zara_entries_from_turns,
    zara_entry_from_turn,
    zara_key,
)


def _spec(**kw):
    base = {"bot_id": "teste-bot", "sources": ["lab", "zara"],
            "max_entries": 100}
    base.update(kw)
    return from_dict(base)


def _turn(**kw):
    base = {"role": "assistant", "content": "ola",
            "engine": "ponte-zoe", "timestamp": 1759000000000}
    base.update(kw)
    return base


class TestZaraAdapter(unittest.TestCase):
    def test_turno_valido_vira_entry(self):
        entry = zara_entry_from_turn(_turn())
        self.assertIsInstance(entry, SharedEntry)
        self.assertEqual(entry.source, "zara")
        self.assertEqual(entry.author, "ponte-zoe")
        self.assertEqual(entry.written_at, 1759000000.0)
        self.assertTrue(entry.key.startswith("fio.ponte-zoe."))

    def test_turno_do_alex_autor_alex(self):
        entry = zara_entry_from_turn(
            _turn(role="user", content="abre o bloco de notas"))
        self.assertEqual(entry.author, "alex")

    def test_chave_estavel_dedup(self):
        t = _turn()
        self.assertEqual(zara_entry_from_turn(t).key,
                         zara_entry_from_turn(dict(t)).key)

    def test_turno_sem_timestamp_nao_entra(self):
        self.assertIsNone(zara_entry_from_turn(_turn(timestamp=None)))
        self.assertIsNone(zara_entry_from_turn(_turn(timestamp=0)))
        self.assertIsNone(zara_entry_from_turn(_turn(timestamp="ontem")))

    def test_turno_sem_texto_nao_entra(self):
        self.assertIsNone(zara_entry_from_turn(_turn(content="")))
        self.assertIsNone(zara_entry_from_turn(_turn(content="   ")))

    def test_turno_grande_demais_nao_entra(self):
        self.assertIsNone(zara_entry_from_turn(_turn(content="x" * 4097)))

    def test_role_desconhecida_nao_entra(self):
        self.assertIsNone(zara_entry_from_turn(_turn(role="sistema")))
        self.assertIsNone(zara_entry_from_turn(_turn(role="")))

    def test_nao_mapping_nao_entra(self):
        self.assertIsNone(zara_entry_from_turn("lixo"))
        self.assertIsNone(zara_entry_from_turn(None))

    def test_lista_mista_so_entra_o_valido(self):
        turns = [_turn(), _turn(timestamp=None), _turn(content=""),
                 _turn(role="sistema"), _turn(content="segundo")]
        entries = zara_entries_from_turns(turns)
        self.assertEqual(len(entries), 2)

    def test_zara_key_formato(self):
        key = zara_key("ponte-zoe", 1759000000000, "ola")
        self.assertRegex(key, r"^[a-z0-9][a-z0-9_.\-]{0,63}$")


class TestSharedMemoryStore(unittest.TestCase):
    def test_le_lab_memory_real(self):
        mem = LabMemory(now=lambda: 1700000000.0)
        mem.write("ENGINEER", "build.verde", "suite 2778/0")
        mem.write("CEO", "decisao.1", "manter a trava")
        store = SharedMemoryStore.from_lab_memory(
            _spec(sources=["lab"]), mem, now=lambda: 1700000001.0)
        view = store.read()
        self.assertEqual(len(view.entries), 2)
        por_chave = {e.key: e for e in view.entries}
        self.assertEqual(por_chave["build.verde"].author, "ENGINEER")
        self.assertEqual(por_chave["decisao.1"].value, "manter a trava")
        self.assertEqual(view.bot_id, "teste-bot")

    def test_le_fio_zara_real(self):
        turns = [_turn(), _turn(role="user", content="oi zara",
                                timestamp=1759000001000)]
        store = SharedMemoryStore(
            _spec(sources=["zara"]), zara_turns=lambda: turns,
            now=lambda: 1700000001.0)
        view = store.read()
        self.assertEqual(len(view.entries), 2)
        autores = {e.author for e in view.entries}
        self.assertEqual(autores, {"ponte-zoe", "alex"})

    def test_fonte_fora_da_spec_nao_chama_leitor(self):
        def _explode():
            raise AssertionError("leitor nao devia ser chamado")
        store = SharedMemoryStore(_spec(sources=["lab"]),
                                  lab_facts=lambda: {},
                                  zara_turns=_explode)
        view = store.read()
        self.assertEqual(len(view.entries), 0)

    def test_fonte_na_spec_sem_leitor_erro(self):
        store = SharedMemoryStore(_spec(sources=["lab", "zara"]))
        with self.assertRaises(SharedMemoryError):
            store.read()
        store2 = SharedMemoryStore(_spec(sources=["lab"]),
                                   zara_turns=lambda: [])
        with self.assertRaises(SharedMemoryError):
            store2.read()

    def test_leitor_quebrado_vira_erro_com_nome_da_fonte(self):
        def _quebra():
            raise RuntimeError("banco fora do ar")
        store = SharedMemoryStore(_spec(sources=["lab"]), lab_facts=_quebra)
        with self.assertRaises(SharedMemoryError) as ctx:
            store.read()
        self.assertIn("lab", str(ctx.exception))

        store2 = SharedMemoryStore(_spec(sources=["zara"]),
                                   zara_turns=_quebra)
        with self.assertRaises(SharedMemoryError) as ctx2:
            store2.read()
        self.assertIn("zara", str(ctx2.exception))

    def test_fato_lab_invalido_erro(self):
        store = SharedMemoryStore(
            _spec(sources=["lab"]),
            lab_facts=lambda: {"k": {"value": "v"}})  # sem seat/written_at
        with self.assertRaises(SharedMemoryError):
            store.read()

    def test_max_entries_respeitado(self):
        mem = LabMemory(now=lambda: 1700000000.0)
        for i in range(5):
            mem.write("ENGINEER", f"fato.{i}", f"valor {i}")
        store = SharedMemoryStore.from_lab_memory(
            _spec(sources=["lab"], max_entries=2), mem)
        view = store.read()
        self.assertEqual(len(view.entries), 2)

    def test_visao_ordenada_deterministica(self):
        mem = LabMemory(now=lambda: 1700000000.0)
        mem.write("ENGINEER", "zeta", "1")
        mem.write("ENGINEER", "alfa", "2")
        # spec so com lab: o leitor zara nem e chamado
        def _explode():
            raise AssertionError("leitor zara nao devia ser chamado")
        store_lab = SharedMemoryStore.from_lab_memory(
            _spec(sources=["lab"]), mem, now=lambda: 1700000001.0)
        chaves = [e.key for e in store_lab.read().entries]
        self.assertEqual(chaves, ["alfa", "zeta"])

    def test_from_lab_memory_sem_facts_erro(self):
        with self.assertRaises(SharedMemoryError):
            SharedMemoryStore.from_lab_memory(_spec(), object())

    def test_spec_invalida_erro(self):
        with self.assertRaises(SharedMemoryError):
            SharedMemoryStore("nao-e-spec", lab_facts=lambda: {})

    def test_visao_das_duas_fontes_juntas(self):
        mem = LabMemory(now=lambda: 1700000000.0)
        mem.write("SCRIBE", "nota.1", "anotado")
        store = SharedMemoryStore.from_lab_memory(
            _spec(), mem, zara_turns=lambda: [_turn()],
            now=lambda: 1700000001.0)
        view = store.read()
        fontes = {e.source for e in view.entries}
        self.assertEqual(fontes, {"lab", "zara"})
        # ordenacao deterministica: lab antes de zara
        self.assertEqual(view.entries[0].source, "lab")
        linhas = view.describe()
        self.assertTrue(linhas[0].startswith("visao de teste-bot:"))


if __name__ == "__main__":
    unittest.main()

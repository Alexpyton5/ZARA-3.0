"""Testes da peca 3 da memoria compartilhada: a API.

Padrao da casa: unittest, roda no pytest do .venv do PC.
"""
import unittest

from core.lab_memory import LabMemory
from core.shared_memory_api import SharedMemoryAPI, SharedMemoryAPIError


def _mem():
    mem = LabMemory(now=lambda: 1700000000.0)
    mem.write("ENGINEER", "build.verde", "suite 2778/0")
    mem.write("CEO", "decisao.1", "manter a trava")
    return mem


def _turns():
    return [
        {"role": "user", "content": "oi zara", "engine": "",
         "timestamp": 1759000001000},
        {"role": "assistant", "content": "ola, Alex",
         "engine": "ponte-zoe", "timestamp": 1759000002000},
    ]


def _spec(**kw):
    base = {"bot_id": "teste-bot", "sources": ["lab", "zara"],
            "max_entries": 100, "include_provenance": True}
    base.update(kw)
    return base


def _api(**kw):
    kw.setdefault("lab_memory", _mem())
    kw.setdefault("zara_turns", _turns)
    return SharedMemoryAPI(**kw)


class TestReadView(unittest.TestCase):
    def test_le_as_duas_fontes_reais(self):
        result = _api().read_view(_spec())
        self.assertEqual(result["bot_id"], "teste-bot")
        self.assertEqual(result["count"], 4)
        self.assertEqual(len(result["entries"]), 4)
        fontes = {e["source"] for e in result["entries"]}
        self.assertEqual(fontes, {"lab", "zara"})
        self.assertIn("built_at", result)
        self.assertEqual(result["sources"], ["lab", "zara"])

    def test_entradas_com_procedencia(self):
        result = _api().read_view(_spec())
        por_chave = {e["key"]: e for e in result["entries"]}
        lab = por_chave["build.verde"]
        self.assertEqual(lab["value"], "suite 2778/0")
        self.assertEqual(lab["author"], "ENGINEER")
        self.assertEqual(lab["written_at"], 1700000000.0)
        zara = [e for e in result["entries"] if e["source"] == "zara"]
        autores = {e["author"] for e in zara}
        self.assertEqual(autores, {"alex", "ponte-zoe"})

    def test_sem_procedencia_quando_pedido(self):
        result = _api().read_view(_spec(include_provenance=False))
        for entry in result["entries"]:
            self.assertNotIn("author", entry)
            self.assertNotIn("written_at", entry)
        self.assertEqual(result["count"], 4)

    def test_so_lab_quando_spec_pede(self):
        result = _api().read_view(_spec(sources=["lab"]))
        fontes = {e["source"] for e in result["entries"]}
        self.assertEqual(fontes, {"lab"})
        self.assertEqual(result["count"], 2)

    def test_max_entries_corta(self):
        result = _api().read_view(_spec(max_entries=1))
        self.assertEqual(result["count"], 1)

    def test_visao_vazia_e_valida(self):
        api = SharedMemoryAPI(lab_memory=LabMemory(now=lambda: 1.0),
                              zara_turns=lambda: [])
        result = api.read_view(_spec())
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["entries"], [])


class TestFailClosed(unittest.TestCase):
    def test_spec_nao_dict_erro(self):
        with self.assertRaises(SharedMemoryAPIError):
            _api().read_view("lixo")

    def test_spec_bot_id_invalido_erro(self):
        with self.assertRaises(SharedMemoryAPIError):
            _api().read_view(_spec(bot_id="BOT MAIUSCULO"))

    def test_spec_fonte_desconhecida_erro(self):
        with self.assertRaises(SharedMemoryAPIError):
            _api().read_view(_spec(sources=["lab", "narnia"]))

    def test_spec_campo_desconhecido_erro(self):
        spec = _spec()
        spec["cor_favorita"] = "azul"
        with self.assertRaises(SharedMemoryAPIError):
            _api().read_view(spec)

    def test_spec_max_entries_fora_erro(self):
        with self.assertRaises(SharedMemoryAPIError):
            _api().read_view(_spec(max_entries=0))
        with self.assertRaises(SharedMemoryAPIError):
            _api().read_view(_spec(max_entries=501))

    def test_zara_na_spec_sem_leitor_erro(self):
        api = SharedMemoryAPI(lab_memory=_mem(), zara_turns=None)
        with self.assertRaises(SharedMemoryAPIError) as ctx:
            api.read_view(_spec(sources=["zara"]))
        self.assertIn("zara", str(ctx.exception))

    def test_lab_na_spec_sem_leitor_erro(self):
        api = SharedMemoryAPI(lab_memory=None, zara_turns=_turns)
        # lab_memory padrao existe (novo, vazio) - entao OK e vazio
        result = api.read_view(_spec(sources=["lab"]))
        self.assertEqual(result["count"], 0)

    def test_leitor_lab_quebrado_erro_nomeia_fonte(self):
        class Quebrado:
            def facts(self):
                raise RuntimeError("disco sumiu")
        api = SharedMemoryAPI(lab_memory=Quebrado(), zara_turns=lambda: [])
        with self.assertRaises(SharedMemoryAPIError) as ctx:
            api.read_view(_spec(sources=["lab"]))
        self.assertIn("lab", str(ctx.exception))

    def test_leitor_zara_quebrado_erro_nomeia_fonte(self):
        def _explode():
            raise RuntimeError("sqlite travou")
        api = SharedMemoryAPI(lab_memory=_mem(), zara_turns=_explode)
        with self.assertRaises(SharedMemoryAPIError) as ctx:
            api.read_view(_spec(sources=["zara"]))
        self.assertIn("zara", str(ctx.exception))

    def test_lab_memory_sem_facts_erro(self):
        api = SharedMemoryAPI(lab_memory=object(), zara_turns=lambda: [])
        with self.assertRaises(SharedMemoryAPIError):
            api.read_view(_spec(sources=["lab"]))


class TestReadSpec(unittest.TestCase):
    def test_valida_e_devolve_dict(self):
        result = _api().read_spec(_spec())
        self.assertEqual(result["bot_id"], "teste-bot")
        self.assertEqual(result["sources"], ["lab", "zara"])

    def test_invalida_erro(self):
        with self.assertRaises(SharedMemoryAPIError):
            _api().read_spec(_spec(bot_id=""))


class TestDescribe(unittest.TestCase):
    def test_describe_traz_fontes_e_limites(self):
        d = SharedMemoryAPI.describe()
        self.assertEqual(d["sources"], ["lab", "zara"])
        self.assertEqual(d["defaults"]["max_entries"], 100)
        self.assertEqual(d["limits"]["max_entries"], 500)
        self.assertEqual(d["limits"]["value_len"], 4096)
        self.assertTrue(d["rules"])


if __name__ == "__main__":
    unittest.main()

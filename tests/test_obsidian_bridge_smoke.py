"""Smoke test da ObsidianBridge — memória/vault local (Galaxy).

Alvo da auditoria de restauração (seção 20/08/2026): core/obsidian_bridge.py
estava em 0% de cobertura real. Este smoke cobre o ciclo completo do vault
(galaxy, add_memory, link_memories, persistência) de forma **isolada do
vault real do Alex**: redireciona via ZARA3_HOME para uma pasta temporária,
exatamente como o conftest da suíte isola as medições. Não escreve nada no
vault real do usuário.
"""

from __future__ import annotations

import pytest

from core import obsidian_bridge
from core.obsidian_bridge import ObsidianBridge, get_bridge


@pytest.fixture()
def vault_home(tmp_path, monkeypatch):
    """Isola o vault numa pasta temporária via ZARA3_HOME e reseta o singleton."""
    monkeypatch.setenv("ZARA3_HOME", str(tmp_path))
    ObsidianBridge._instance = None
    obsidian_bridge._bridge_instance = None
    return tmp_path


def test_singleton_retorna_mesma_instancia(vault_home):
    b1 = ObsidianBridge()
    b2 = ObsidianBridge()
    assert b1 is b2


def test_vault_e_criado_na_primeira_instanciacao(vault_home):
    ObsidianBridge()
    assert (vault_home / "vault").is_dir()
    assert (vault_home / "vault" / "memories").is_dir()
    assert (vault_home / "vault" / "knowledge").is_dir()
    assert (vault_home / "vault" / "projects").is_dir()


def test_galaxy_vazio_na_origem(vault_home):
    bridge = ObsidianBridge()
    g = bridge.galaxy()
    assert g["nodes"] == []
    assert g["links"] == []


def test_add_memory_cria_no_grafo_e_no_disco(vault_home):
    bridge = ObsidianBridge()
    node_id = bridge.add_memory("Primeira", "conteúdo", tags=["teste"], category="memories")
    assert node_id

    g = bridge.galaxy()
    assert len(g["nodes"]) == 1
    assert g["nodes"][0]["title"] == "Primeira"
    assert g["nodes"][0]["tags"] == ["teste"]

    # arquivo markdown criado com frontmatter
    md_files = list((vault_home / "vault" / "memories").glob("*.md"))
    assert len(md_files) == 1
    text = md_files[0].read_text(encoding="utf-8")
    assert "title: Primeira" in text
    assert "conteúdo" in text


def test_link_memories_adiciona_link(vault_home):
    bridge = ObsidianBridge()
    a = bridge.add_memory("A", "x")
    b = bridge.add_memory("B", "y")
    bridge.link_memories(a, b, relation="depends_on")

    g = bridge.galaxy()
    assert len(g["links"]) == 1
    assert g["links"][0]["source"] == a
    assert g["links"][0]["target"] == b
    assert g["links"][0]["relation"] == "depends_on"


def test_dados_persistem_apos_nova_instancia(vault_home):
    bridge = ObsidianBridge()
    bridge.add_memory("Persiste", "dado", tags=["p"])
    bridge.link_memories("abc", "def")

    # nova instância (mesmo vault_home) lê o que foi salvo
    bridge2 = ObsidianBridge()
    g = bridge2.galaxy()
    assert len(g["nodes"]) == 1
    assert len(g["links"]) == 1


def test_galaxy_resiste_a_index_corrompido(vault_home):
    bridge = ObsidianBridge()
    (vault_home / "vault" / ".zara_index.json").write_text("{corrompido!!!", encoding="utf-8")
    g = bridge.galaxy()
    assert g["nodes"] == []
    assert g["links"] == []


def test_get_bridge_retorna_instancia_global(vault_home):
    assert isinstance(get_bridge(), ObsidianBridge)

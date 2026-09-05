"""
Testa _extract_memory_links (Memory Galaxy) isoladamente, como funcao pura.

Nao instancia IPCHandler nem toca em stores reais: os nodes sao fabricados
a mao, no mesmo formato que handle_memory_galaxy_list ja produz
({id, kind, title, content, source, updated_at}).
"""

from core.ipc_handlers import _extract_memory_links


def _node(node_id, title, content):
    return {
        "id": node_id,
        "kind": "test",
        "title": title,
        "content": content,
        "source": "test",
        "updated_at": None,
    }


def test_link_created_when_title_appears_in_other_content():
    nodes = [
        _node("project:alpha", "Projeto Alpha", "Falamos sobre o Projeto Beta ontem."),
        _node("project:beta", "Projeto Beta", "Sem referencias cruzadas aqui."),
    ]

    links = _extract_memory_links(nodes)

    assert {"source": "project:alpha", "target": "project:beta"} in links


def test_no_self_link():
    nodes = [
        _node("project:alpha", "Projeto Alpha", "O Projeto Alpha comeca hoje."),
    ]

    links = _extract_memory_links(nodes)

    assert links == []


def test_no_duplicate_pair_in_both_directions():
    # A cita B e B cita A -- so pode aparecer um dos dois sentidos, nunca os dois.
    nodes = [
        _node("user:a", "Café da manhã", "Combinei com o Café da manhã de sempre e falei do Almoço."),
        _node("user:b", "Almoço", "Depois do Almoço, penso no Café da manhã."),
    ]

    links = _extract_memory_links(nodes)

    pairs = [frozenset((link["source"], link["target"])) for link in links]
    assert len(pairs) == len(set(pairs)), "par duplicado (A->B e B->A) nao pode acontecer"
    assert len(links) == 1


def test_no_link_when_no_reference():
    nodes = [
        _node("a", "Maçã", "Conteudo qualquer sem nada em comum."),
        _node("b", "Banana", "Outro conteudo completamente diferente."),
    ]

    links = _extract_memory_links(nodes)

    assert links == []


def test_empty_nodes_returns_empty_links():
    assert _extract_memory_links([]) == []


def test_respects_max_links_limit():
    # Gera N nodes onde o node 0 cita todos os outros pelo titulo, garantindo
    # mais links possiveis que o limite, e confirma que o corte e respeitado.
    nodes = []
    other_titles = [f"Titulo Unico Numero {i}" for i in range(1, 250)]
    content_zero = " ".join(other_titles)
    nodes.append(_node("node:0", "Raiz", content_zero))
    for i, title in enumerate(other_titles, start=1):
        nodes.append(_node(f"node:{i}", title, "conteudo vazio de referencia"))

    links = _extract_memory_links(nodes, max_links=200)

    assert len(links) == 200


def test_ignores_very_short_titles_to_avoid_noise():
    nodes = [
        _node("a", "Ok", "Isso aqui diz Ok em algum lugar do texto, mas o titulo é curto demais."),
        _node("b", "Memória de longo prazo", "sem relacao"),
    ]

    links = _extract_memory_links(nodes)

    # titulo "Ok" tem 2 caracteres, abaixo do minimo -- nao devia gerar link
    assert links == []


def test_returns_list_of_plain_dicts_with_expected_keys():
    nodes = [
        _node("project:alpha", "Projeto Alpha", "Cita o Projeto Beta aqui."),
        _node("project:beta", "Projeto Beta", "nada"),
    ]

    links = _extract_memory_links(nodes)

    assert isinstance(links, list)
    for link in links:
        assert set(link.keys()) == {"source", "target"}
        assert link["source"] != link["target"]

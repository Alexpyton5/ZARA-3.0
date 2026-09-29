"""Memoria compartilhada ZARA <-> bots: a API (peca 3).

A camada de servico que o bot (via IPC, peca 4) chama pra LER a visao
unificada. Empilha a peca 1 (spec/contrato) e a peca 2 (store lendo as
fontes reais): monta a spec a partir do que chega do bot, liga o
LabMemory real e o fio unificado, le a visao e devolve tudo serializado
(pronto pra JSON).

Fail-closed do inicio ao fim: spec invalida, fonte sem leitor ou leitor
quebrado viram SharedMemoryAPIError com mensagem em portugues. Nada aqui
inventa valor quando falta dado, e o bot nunca escreve na fonte do outro
lado - a escrita continua no escopo proprio de cada lado.

Logica pura sobre os stores; sem rede, sem modelo, custo zero.
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Mapping

try:  # dentro do app (pacote core.*)
    from core.lab_memory import LabMemory
    from core.shared_memory_spec import (
        KNOWN_SOURCES,
        SharedMemoryError,
        SharedMemoryView,
        from_dict as spec_from_dict,
        to_dict as spec_to_dict,
    )
    from core.shared_memory_store import SharedMemoryStore
except ImportError:  # teste flat
    from lab_memory import LabMemory
    from shared_memory_spec import (
        KNOWN_SOURCES,
        SharedMemoryError,
        SharedMemoryView,
        from_dict as spec_from_dict,
        to_dict as spec_to_dict,
    )
    from shared_memory_store import SharedMemoryStore

_ZARA_TURNS_LIMIT = 200


class SharedMemoryAPIError(Exception):
    """A visao da memoria compartilhada nao pode ser entregue (spec
    invalida, fonte sem leitor ou fonte quebrada). Mensagem sempre em
    portugues, para a UI mostrar direto ao Alex."""


def _wrap(exc: Exception) -> SharedMemoryAPIError:
    return SharedMemoryAPIError(str(exc))


def _serialize_view(
    view: SharedMemoryView, *, include_provenance: bool
) -> dict[str, Any]:
    """Visao congelada -> dict pronto pra JSON.

    Com include_provenance=False, autor/quando saem (o bot pediu pra nao
    ver procedencia - a regra da spec manda respeitar).
    """
    entries = []
    for entry in view.entries:
        item: dict[str, Any] = {
            "source": entry.source,
            "key": entry.key,
            "value": entry.value,
        }
        if include_provenance:
            item["author"] = entry.author
            item["written_at"] = entry.written_at
        entries.append(item)
    return {
        "bot_id": view.bot_id,
        "sources": list(view.sources),
        "built_at": view.built_at,
        "count": len(entries),
        "entries": entries,
    }


class SharedMemoryAPI:
    """Ponto unico de entrada para ler a memoria compartilhada.

    `lab_memory`/`zara_turns` podem ser injetados (testes); sem eles:
    - lab_memory: um LabMemory novo (vazio ate o runtime ligar o real -
      o futuro plug injeta o LabMemory do Lab de verdade);
    - zara_turns: None - e spec com fonte 'zara' sem leitor vira ERRO
      (regra 1 do store: nunca visao inventada nem fonte ignorada em
      silencio).
    """

    def __init__(
        self,
        lab_memory: Any | None = None,
        zara_turns: Callable[[], Iterable[Mapping[str, Any]]] | None = None,
    ) -> None:
        self._lab_memory = lab_memory
        self._zara_turns = zara_turns

    def _lab(self) -> Any:
        if self._lab_memory is None:
            self._lab_memory = LabMemory()
        return self._lab_memory

    # -- leitura ----------------------------------------------------------

    def read_view(self, spec_data: Mapping[str, Any]) -> dict[str, Any]:
        """Monta a spec do que o bot pediu, le as fontes reais e devolve
        a visao unificada serializada.

        spec_data: {"bot_id": ..., "sources": ["lab", "zara"],
                    "max_entries": N, "include_provenance": bool}.
        Invalida = SharedMemoryAPIError, nada e devolvido.
        """
        if not isinstance(spec_data, Mapping):
            raise SharedMemoryAPIError(
                "a spec da visao precisa ser um dicionario")
        try:
            spec = spec_from_dict(spec_data)
        except SharedMemoryError as exc:
            raise _wrap(exc) from exc
        lab_memory = self._lab()
        facts = getattr(lab_memory, "facts", None)
        if not callable(facts):
            raise SharedMemoryAPIError(
                "lab_memory sem o metodo facts() - fonte 'lab' nao ligada")
        try:
            store = SharedMemoryStore(
                spec,
                lab_facts=facts,
                zara_turns=self._zara_turns,
            )
            view = store.read()
        except SharedMemoryError as exc:
            raise _wrap(exc) from exc
        return _serialize_view(view, include_provenance=spec.include_provenance)

    def read_spec(self, spec_data: Mapping[str, Any]) -> dict[str, Any]:
        """So valida a spec e devolve como dict (a UI confere antes de
        pedir a visao)."""
        if not isinstance(spec_data, Mapping):
            raise SharedMemoryAPIError(
                "a spec da visao precisa ser um dicionario")
        try:
            return spec_to_dict(spec_from_dict(spec_data))
        except SharedMemoryError as exc:
            raise _wrap(exc) from exc

    # -- vocabulario p/ a UI ----------------------------------------------

    @staticmethod
    def describe() -> dict[str, Any]:
        """Tudo que a UI precisa pra montar o pedido SEM inventar valores:
        fontes conhecidas, padroes e limites. O que nao estiver aqui, o
        backend rejeita."""
        return {
            "sources": sorted(KNOWN_SOURCES),
            "defaults": {
                "sources": ["lab", "zara"],
                "max_entries": 100,
                "include_provenance": True,
            },
            "limits": {
                "max_entries": 500,
                "value_len": 4096,
            },
            "rules": [
                "o bot LE a visao; nunca escreve na fonte do outro lado",
                "fonte desconhecida e recusada, nunca inventada",
                "sem procedencia (fonte, autor, quando), o item nao entra",
                "fonte na spec sem leitor = erro, nunca visao parcial",
            ],
        }

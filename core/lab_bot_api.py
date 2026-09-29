"""Camada de servico dos bots customizaveis ("bots faceis", peca 3).

A API que a futura UI (via IPC) vai chamar: criar, ler, atualizar, apagar
e listar bots, mais `describe()` (os vocabularios validos, para a UI montar
o formulario sem inventar valores) e `sync_lab()` (garante que toda spec
salva esta registrada no Lab).

Empilha a peca 1 (spec declarativa validada) e a peca 2 (BotStore +
register). Fail-closed do inicio ao fim: entrada invalida vira BotAPIError
com mensagem em portugues; nada aqui inventa valor quando falta dado.

Logica pura sobre os stores; sem rede, sem modelo, custo zero.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Mapping

try:  # dentro do app (pacote core.*)
    from core.lab_bot_spec import (
        DANGEROUS_CAPABILITIES,
        DEFAULT_CAPABILITIES,
        DEFAULT_MODEL,
        DEFAULT_PROVIDER_ID,
        KNOWN_CAPABILITIES,
        MAX_INSTRUCTIONS_LEN,
        MAX_NAME_LEN,
        MAX_TURNS_LIMIT,
        BotSpecError,
        from_dict,
        to_dict,
    )
    from core.lab_bot_store import BotStore, BotStoreError, register
    from core.lab_v1.domain import Lifecycle, RoleName
    from core.lab_v1.store import LabStore
except ImportError:  # teste flat
    from lab_bot_spec import (
        DANGEROUS_CAPABILITIES,
        DEFAULT_CAPABILITIES,
        DEFAULT_MODEL,
        DEFAULT_PROVIDER_ID,
        KNOWN_CAPABILITIES,
        MAX_INSTRUCTIONS_LEN,
        MAX_NAME_LEN,
        MAX_TURNS_LIMIT,
        BotSpecError,
        from_dict,
        to_dict,
    )
    from lab_bot_store import BotStore, BotStoreError, register
    from lab_v1.domain import Lifecycle, RoleName
    from lab_v1.store import LabStore


class BotAPIError(Exception):
    """A operacao com bots nao pode ser cumprida (entrada invalida ou
    store com problema). Mensagem sempre em portugues, para a UI mostrar
    direto ao Alex."""


def _wrap_store(exc: Exception) -> BotAPIError:
    return BotAPIError(str(exc))


class BotAPI:
    """Ponto unico de entrada para gerenciar bots customizaveis.

    `bot_store`/`lab_store` podem ser injetados (testes); sem eles, usam os
    padroes do app (specs em <data_dir>/lab/bots, banco do Lab).
    """

    def __init__(
        self, bot_store: BotStore | None = None, lab_store: LabStore | None = None
    ) -> None:
        self._store = bot_store if bot_store is not None else BotStore()
        self._lab = lab_store if lab_store is not None else LabStore()
        self._lab.initialize()

    # -- escrita ---------------------------------------------------------

    def create_bot(self, data: Mapping[str, Any]) -> dict[str, Any]:
        """Cria um bot a partir de um dict (o que a UI envia).

        Mesmo id = sobrescreve (upsert, igual ao store). Retorna a spec
        salva como dict. Invalida = BotAPIError, nada e escrito.
        """
        if not isinstance(data, Mapping):
            raise BotAPIError("dados do bot precisam ser um dicionario")
        try:
            spec = from_dict(data)
            self._store.save(spec)
            register(self._lab, spec)
        except (BotSpecError, BotStoreError) as exc:
            raise _wrap_store(exc) from exc
        return to_dict(spec)

    def update_bot(self, bot_id: str, patch: Mapping[str, Any]) -> dict[str, Any]:
        """Atualiza so os campos do patch; o resto continua igual.

        O id nao pode mudar. Campo desconhecido = erro (nunca default
        silencioso). Bot inexistente = erro. Retorna a spec final.
        """
        if not isinstance(patch, Mapping):
            raise BotAPIError("atualizacao precisa ser um dicionario")
        try:
            merged = to_dict(self._store.load(bot_id))
        except BotStoreError as exc:
            raise _wrap_store(exc) from exc
        for key, value in patch.items():
            if key == "id" and value != bot_id:
                raise BotAPIError("o id do bot nao pode mudar")
            merged[key] = value
        try:
            spec = from_dict(merged)
            self._store.save(spec)
            register(self._lab, spec)
        except (BotSpecError, BotStoreError) as exc:
            raise _wrap_store(exc) from exc
        return to_dict(spec)

    def delete_bot(self, bot_id: str) -> dict[str, Any]:
        """Apaga a spec e ARQUIVA o agente no Lab (historico preservado).

        Bot inexistente = erro (nao finge que apagou).
        """
        try:
            self._store.delete(bot_id)
        except BotStoreError as exc:
            raise _wrap_store(exc) from exc
        archived = False
        agent = self._lab.get_agent(bot_id)
        if agent is not None and not agent.archived:
            self._lab.save_agent(replace(agent, archived=True))
            archived = True
        return {"id": bot_id, "spec_deleted": True, "lab_archived": archived}

    def sync_lab(self) -> dict[str, int]:
        """Registra no Lab todas as specs salvas (p.ex. depois de um boot).

        Retorna quantas foram registradas.
        """
        try:
            specs = self._store.list()
        except BotStoreError as exc:
            raise _wrap_store(exc) from exc
        for spec in specs:
            register(self._lab, spec)
        return {"registered": len(specs)}

    # -- leitura ----------------------------------------------------------

    def get_bot(self, bot_id: str) -> dict[str, Any]:
        """Uma spec como dict. Inexistente = BotAPIError."""
        try:
            return to_dict(self._store.load(bot_id))
        except BotStoreError as exc:
            raise _wrap_store(exc) from exc

    def list_bots(self) -> list[dict[str, Any]]:
        """Todas as specs como dicts, ordenadas por id."""
        try:
            return [to_dict(spec) for spec in self._store.list()]
        except BotStoreError as exc:
            raise _wrap_store(exc) from exc

    # -- vocabulario p/ a UI ------------------------------------------------

    @staticmethod
    def describe() -> dict[str, Any]:
        """Tudo que a UI precisa para montar o formulario SEM inventar
        valores: roles, lifecycles e capabilities validos, padroes e
        limites. O que nao estiver aqui, o backend rejeita."""
        return {
            "roles": [r.value for r in RoleName],
            "lifecycles": [l.value for l in Lifecycle],
            "capabilities": sorted(KNOWN_CAPABILITIES),
            "dangerous_capabilities": sorted(DANGEROUS_CAPABILITIES),
            "defaults": {
                "role": RoleName.MEMBER.value,
                "lifecycle": Lifecycle.PERMANENT.value,
                "provider_id": DEFAULT_PROVIDER_ID,
                "model": DEFAULT_MODEL,
                "capabilities": list(DEFAULT_CAPABILITIES),
                "max_turns": 1,
            },
            "limits": {
                "max_turns": MAX_TURNS_LIMIT,
                "name_len": MAX_NAME_LEN,
                "instructions_len": MAX_INSTRUCTIONS_LEN,
            },
        }

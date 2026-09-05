"""ZARA-COMPOUND-E-SOLTO-001

Bug real do Alex: "abra o YouTube, pesquise Bruno Mars e bote para tocar e
pule o anúncio" só dividia em 2 pedaços, porque o split de
`_try_compound_pc_intent` só quebra em vírgula/";"/"depois", nunca em "e"
solto. O segundo pedaço virava um pedido de 3 ações que nenhum comando único
reconhecia como um todo.

Estes testes cobrem o fallback: "e" solto só quebra um pedaço quando TODOS
os sub-pedaços resultantes batem sozinhos como intent de PC — e nunca toca
um pedaço que já é uma consulta legítima só (ex.: "pesquise rock e blues no
youtube", que é uma busca só e tem que continuar sendo uma etapa só).
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.ipc_handlers import IPCHandler


@pytest.mark.asyncio
async def test_loose_e_splits_when_no_single_command_matches_the_whole_piece():
    handler = IPCHandler(AsyncMock())
    handler._try_pc_intent = AsyncMock(
        side_effect=(
            "YouTube aberto e verificado.",
            "Busca por Bruno Mars feita.",
            "Reprodução iniciada.",
            "Anúncio pulado e confirmado.",
        )
    )

    reply = await handler._try_compound_pc_intent(
        "Zara, abra o YouTube, pesquise Bruno Mars e bote para tocar e pule o anúncio"
    )

    assert [call.args[0] for call in handler._try_pc_intent.await_args_list] == [
        "abra o YouTube",
        "pesquise Bruno Mars",
        "bote para tocar",
        "pule o anúncio",
    ]
    assert reply == (
        "Resultado por etapa: 1) YouTube aberto e verificado. "
        "2) Busca por Bruno Mars feita. 3) Reprodução iniciada. "
        "4) Anúncio pulado e confirmado."
    )


@pytest.mark.asyncio
async def test_loose_e_never_splits_a_piece_that_already_matches_as_one_search():
    handler = IPCHandler(AsyncMock())
    handler._try_pc_intent = AsyncMock(
        side_effect=(
            "Buscando rock e blues no YouTube.",
            "Downloads aberto e verificado.",
        )
    )

    reply = await handler._try_compound_pc_intent(
        "Zara, pesquise rock e blues no youtube, abra Downloads"
    )

    # "blues no youtube" sozinho não bate com nenhum comando, então o
    # fallback tem que desistir de dividir e manter a busca inteira como
    # uma etapa só -- exatamente como funcionava antes desta mudança.
    assert [call.args[0] for call in handler._try_pc_intent.await_args_list] == [
        "pesquise rock e blues no youtube",
        "abra Downloads",
    ]
    assert reply == (
        "Resultado por etapa: 1) Buscando rock e blues no YouTube. "
        "2) Downloads aberto e verificado."
    )


@pytest.mark.asyncio
async def test_loose_e_split_still_reports_unsupported_step_honestly():
    handler = IPCHandler(AsyncMock())
    handler._try_pc_intent = AsyncMock()

    reply = await handler._try_compound_pc_intent(
        "Zara, abra o YouTube, conte uma piada e resolva a prova e assine o contrato"
    )

    # Nem o pedaço inteiro nem nenhum dos sub-pedaços batem com um comando de
    # PC, então o fallback desiste de dividir e o pedaço volta intacto, caindo
    # no caminho honesto de "etapa não suportada" -- sem executar nada.
    assert "não é suportada" in reply
    handler._try_pc_intent.assert_not_awaited()

"""Peca 4 ("bots faceis"): fiacao IPC lab-bot-* -> BotAPI.

Roda no PC do Alex contra o .venv real do projeto:
    .venv\\Scripts\\python.exe -m pytest core/test_lab_bot_ipc.py -q

Usa um dono falso (sabe send_response/send_error) e uma BotAPI com
stores em tmp — nada toca no banco de verdade.
"""
from __future__ import annotations

import asyncio

import pytest

from core.lab_bot_api import BotAPI
from core.lab_bot_ipc import LAB_BOT_ROUTES, build_lab_bot_handlers
from core.lab_bot_store import BotStore
from core.lab_v1.store import LabStore


class FakeMsg:
    def __init__(self, request_id="req-1", payload=None):
        self.request_id = request_id
        self.payload = payload


class FakeOwner:
    def __init__(self, api):
        self._lab_bot_api = api
        self.responses = []
        self.errors = []

    async def send_response(self, request_id, response=None, **kwargs):
        self.responses.append((request_id, response))

    async def send_error(self, msg, error):
        self.errors.append((msg, error))


def _owner(tmp_path):
    api = BotAPI(BotStore(tmp_path / "bots"), LabStore(tmp_path / "lab.db"))
    return FakeOwner(api)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_rotas_esperadas():
    assert set(LAB_BOT_ROUTES) == {
        "lab-bot-create",
        "lab-bot-get",
        "lab-bot-list",
        "lab-bot-update",
        "lab-bot-delete",
        "lab-bot-sync",
        "lab-bot-describe",
    }


def test_build_liga_todas_ao_dono(tmp_path):
    owner = _owner(tmp_path)
    handlers = build_lab_bot_handlers(owner)
    assert set(handlers) == set(LAB_BOT_ROUTES)
    _run(handlers["lab-bot-describe"](FakeMsg()))
    assert owner.responses and "roles" in owner.responses[0][1]


def test_create_e_get_via_ipc(tmp_path):
    owner = _owner(tmp_path)
    _run(
        LAB_BOT_ROUTES["lab-bot-create"](
            owner,
            FakeMsg(payload={"id": "ajudante", "name": "Ajudante", "instructions": "ajuda"}),
        )
    )
    assert owner.responses[0][1]["id"] == "ajudante"
    owner.responses.clear()
    _run(LAB_BOT_ROUTES["lab-bot-get"](owner, FakeMsg(payload={"bot_id": "ajudante"})))
    assert owner.responses[0][1]["name"] == "Ajudante"


def test_create_invalido_vira_erro_pt(tmp_path):
    owner = _owner(tmp_path)
    _run(LAB_BOT_ROUTES["lab-bot-create"](owner, FakeMsg(payload={"id": "x", "role": "REI"})))
    assert not owner.responses
    assert owner.errors and owner.errors[0][1]


def test_create_sem_payload(tmp_path):
    owner = _owner(tmp_path)
    _run(LAB_BOT_ROUTES["lab-bot-create"](owner, FakeMsg(payload=None)))
    assert owner.errors and "ausentes" in owner.errors[0][1]


def test_get_sem_id(tmp_path):
    owner = _owner(tmp_path)
    _run(LAB_BOT_ROUTES["lab-bot-get"](owner, FakeMsg(payload={})))
    assert owner.errors and "ausente" in owner.errors[0][1]


def test_get_inexistente(tmp_path):
    owner = _owner(tmp_path)
    _run(LAB_BOT_ROUTES["lab-bot-get"](owner, FakeMsg(payload={"bot_id": "fantasma"})))
    assert owner.errors and owner.errors[0][1]


def test_list_ordenado(tmp_path):
    owner = _owner(tmp_path)
    for bid in ("zeta", "alfa"):
        _run(
            LAB_BOT_ROUTES["lab-bot-create"](
                owner, FakeMsg(payload={"id": bid, "name": bid, "instructions": "x"})
            )
        )
    owner.responses.clear()
    _run(LAB_BOT_ROUTES["lab-bot-list"](owner, FakeMsg()))
    assert [b["id"] for b in owner.responses[0][1]] == ["alfa", "zeta"]


def test_update_via_ipc(tmp_path):
    owner = _owner(tmp_path)
    _run(
        LAB_BOT_ROUTES["lab-bot-create"](
            owner, FakeMsg(payload={"id": "b1", "name": "Um", "instructions": "x"})
        )
    )
    owner.responses.clear()
    _run(
        LAB_BOT_ROUTES["lab-bot-update"](
            owner, FakeMsg(payload={"bot_id": "b1", "patch": {"name": "Dois"}})
        )
    )
    assert owner.responses[0][1]["name"] == "Dois"


def test_update_muda_id_rejeitado(tmp_path):
    owner = _owner(tmp_path)
    _run(
        LAB_BOT_ROUTES["lab-bot-create"](
            owner, FakeMsg(payload={"id": "b1", "name": "Um", "instructions": "x"})
        )
    )
    owner.errors.clear()
    _run(
        LAB_BOT_ROUTES["lab-bot-update"](
            owner, FakeMsg(payload={"bot_id": "b1", "patch": {"id": "outro"}})
        )
    )
    assert owner.errors and "id" in owner.errors[0][1].lower()


def test_update_sem_patch(tmp_path):
    owner = _owner(tmp_path)
    _run(LAB_BOT_ROUTES["lab-bot-update"](owner, FakeMsg(payload={"bot_id": "b1"})))
    assert owner.errors and "patch" in owner.errors[0][1].lower()


def test_delete_arquiva_no_lab(tmp_path):
    owner = _owner(tmp_path)
    db_owner_api = owner._lab_bot_api
    _run(
        LAB_BOT_ROUTES["lab-bot-create"](
            owner, FakeMsg(payload={"id": "b1", "name": "Um", "instructions": "x"})
        )
    )
    owner.responses.clear()
    _run(LAB_BOT_ROUTES["lab-bot-delete"](owner, FakeMsg(payload={"bot_id": "b1"})))
    out = owner.responses[0][1]
    assert out["spec_deleted"] is True and out["lab_archived"] is True
    assert db_owner_api._lab.get_agent("b1").archived is True


def test_sync_registra_specs(tmp_path):
    owner = _owner(tmp_path)
    _run(
        LAB_BOT_ROUTES["lab-bot-create"](
            owner, FakeMsg(payload={"id": "b1", "name": "Um", "instructions": "x"})
        )
    )
    owner.responses.clear()
    _run(LAB_BOT_ROUTES["lab-bot-sync"](owner, FakeMsg()))
    assert owner.responses[0][1]["registered"] == 1


def test_describe_tem_vocabulario(tmp_path):
    owner = _owner(tmp_path)
    _run(LAB_BOT_ROUTES["lab-bot-describe"](owner, FakeMsg()))
    d = owner.responses[0][1]
    assert "MEMBER" in d["roles"] and "capabilities" in d and "limits" in d

"""Testes do auto-reparo — FRENTE F (MISSÃO GIGANTE 3).

F1: classificação simples x complexo (fail-closed).
F2: erro simples simulado é consertado sem intervenção e a nota aparece no vault.
F3: erro complexo gera o pedido curto de permissão.

Isolamento: o vault usado nos testes é sempre um tmp_path — nunca o cofre
real do Alex (ver tests/conftest.py).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from core import auto_repair
from core.auto_repair import (
    Classification,
    ErrorClass,
    RepairMemory,
    ask_permission,
    classify_error,
    handle_error,
    resolve_segundo_cerebro,
)


def _fake_vault(tmp_path: Path) -> Path:
    """Monta um segundo-cérebro de mentira: vault/segundo-cerebro."""
    vault = tmp_path / "vault"
    segundo = vault / "segundo-cerebro"
    segundo.mkdir(parents=True)
    return segundo


# ---------------------------------------------------------------------------
# F1 — classificação
# ---------------------------------------------------------------------------

def test_transitorio_com_retry_eh_simples():
    c = classify_error(TimeoutError("demorou demais"), retry_available=True)
    assert c.error_class == ErrorClass.SIMPLE


def test_transitorio_sem_retry_vira_complexo():
    c = classify_error(TimeoutError("demorou demais"), retry_available=False)
    assert c.error_class == ErrorClass.COMPLEX


def test_sqlite_locked_com_retry_eh_simples():
    c = classify_error(sqlite3.OperationalError("database is locked"), retry_available=True)
    assert c.error_class == ErrorClass.SIMPLE


def test_pasta_ausente_eh_simples():
    c = classify_error(FileNotFoundError("x"), context={"target_path": "C:/tmp/zara-x"})
    assert c.error_class == ErrorClass.SIMPLE


def test_cache_json_corrompido_eh_simples():
    exc = json.JSONDecodeError("msg", "doc", 0)
    c = classify_error(exc, context={"target_path": "C:/tmp/cache/zara-cache.json"})
    assert c.error_class == ErrorClass.SIMPLE


def test_config_com_padrao_conhecido_eh_simples():
    c = classify_error(KeyError("voz"), context={"defaults": {"voz": "kore"}})
    assert c.error_class == ErrorClass.SIMPLE


def test_permission_error_nunca_eh_simples():
    c = classify_error(PermissionError("acesso negado"), retry_available=True)
    assert c.error_class == ErrorClass.COMPLEX


def test_erro_desconhecido_eh_complexo_fail_closed():
    c = classify_error(RuntimeError("algo muito estranho aconteceu"))
    assert c.error_class == ErrorClass.COMPLEX
    assert "desconhecida" in c.reason


def test_dinheiro_eh_bloqueado():
    c = classify_error(ValueError("falha no pagamento via pix"), context={"operation": "cobrar"})
    assert c.error_class == ErrorClass.COMPLEX
    assert c.blocked is True


def test_quarentena_supercerebro_eh_bloqueada():
    c = classify_error(
        FileNotFoundError("x"),
        context={"target_path": "C:/app/core/supercerebro_grant.py"},
    )
    assert c.error_class == ErrorClass.COMPLEX
    assert c.blocked is True


# ---------------------------------------------------------------------------
# F2 — auto-reparo de erro simples + nota no vault
# ---------------------------------------------------------------------------

def test_reparo_recria_pasta_e_salva_nota(tmp_path):
    segundo = _fake_vault(tmp_path)
    alvo = tmp_path / "dados" / "voz"  # não existe

    outcome = handle_error(
        FileNotFoundError(str(alvo)),
        context={
            "target_path": str(alvo),
            "component": "voz",
            "operation": "carregar perfil de voz",
            "how_broke": "A pasta do perfil de voz sumiu do disco.",
            "note_title": "voz — FileNotFoundError",
        },
        vault_path=segundo,
        simulated=True,
    )

    assert outcome.fixed is True
    assert outcome.error_class == ErrorClass.SIMPLE
    assert outcome.strategy == "recriar_pasta"
    assert alvo.is_dir()

    # A nota apareceu no vault, com como-quebrou + como-consertou.
    notas = list((segundo / "aprendizados").glob("*.md"))
    assert len(notas) == 1
    texto = notas[0].read_text(encoding="utf-8")
    assert "## Como quebrou" in texto
    assert "## Como consertou" in texto
    assert "pasta do perfil de voz sumiu" in texto
    assert "pasta recriada" in texto
    assert "[[INDICE]]" in texto
    assert "SIMULADO" in texto
    assert outcome.note_path == str(notas[0])


def test_reparo_retry_transitorio_salva_nota(tmp_path):
    segundo = _fake_vault(tmp_path)
    chamadas = {"n": 0}

    def flaky():
        chamadas["n"] += 1
        if chamadas["n"] < 3:
            raise TimeoutError("demorou demais")

    outcome = handle_error(
        TimeoutError("demorou demais"),
        context={"component": "rede local", "operation": "ping no serviço"},
        retry=flaky,
        vault_path=segundo,
        simulated=True,
    )

    assert outcome.fixed is True
    assert outcome.strategy == "retry_transitorio"
    assert chamadas["n"] == 3
    assert len(list((segundo / "aprendizados").glob("*.md"))) == 1


def test_reparo_que_falha_na_verificacao_escala():
    # Cache fora de pasta tmp/cache não é elegível -> complexo por fail-closed.
    outcome = handle_error(
        json.JSONDecodeError("msg", "doc", 0),
        context={"target_path": "C:/app/dados/importante.json"},
        vault_path=None,
    )
    assert outcome.fixed is False
    assert outcome.error_class == ErrorClass.COMPLEX
    assert outcome.message  # pedido de permissão gerado


def test_config_padrao_preenchido_e_verificado(tmp_path):
    segundo = _fake_vault(tmp_path)
    config: dict = {}
    outcome = handle_error(
        KeyError("voz"),
        context={
            "component": "voz",
            "defaults": {"voz": "kore"},
            "config": config,
        },
        vault_path=segundo,
        simulated=True,
    )
    assert outcome.fixed is True
    assert config["voz"] == "kore"


# ---------------------------------------------------------------------------
# F3 — erro complexo: pedido curto de permissão
# ---------------------------------------------------------------------------

def test_pedido_de_permissao_formato_do_alex():
    msg = ask_permission(PermissionError("microfone bloqueado pelo sistema"),
                         context={"component_pt": "a voz"})
    assert msg.startswith("Quebrei a voz:")
    assert "Posso tentar consertar?" in msg
    assert len(msg) <= 160


def test_pedido_de_permissao_dinheiro_nao_pede_para_consertar():
    msg = ask_permission(ValueError("erro no pagamento"), context={"component_pt": "o pagamento"})
    assert "dinheiro" in msg
    assert "não mexo sem você mandar" in msg


def test_handle_error_complexo_devolve_mensagem_sem_consertar(tmp_path):
    outcome = handle_error(
        PermissionError("microfone bloqueado"),
        context={"component_pt": "a voz", "component": "voz"},
        vault_path=_fake_vault(tmp_path),
    )
    assert outcome.fixed is False
    assert outcome.error_class == ErrorClass.COMPLEX
    assert outcome.message is not None
    assert "Quebrei a voz:" in outcome.message


# ---------------------------------------------------------------------------
# Robustez: best-effort, nunca quebra o app
# ---------------------------------------------------------------------------

def test_nota_best_effort_sem_vault(tmp_path):
    mem = RepairMemory(vault_path=tmp_path / "nao-existe")
    assert mem.save_repair_note(
        title="x", component="y", error_text="z",
        how_broke="a", how_fixed="b",
    ) is None


def test_resolve_segundo_cerebro_prefere_subpasta(tmp_path):
    segundo = _fake_vault(tmp_path)
    assert resolve_segundo_cerebro(segundo.parent) == segundo


def test_resolve_segundo_cerebro_cai_para_raiz_sem_subpasta(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    assert resolve_segundo_cerebro(vault) == vault


def test_resolve_segundo_cerebro_none_quando_indisponivel(tmp_path):
    assert resolve_segundo_cerebro(tmp_path / "nao-existe") is None


def test_scan_user_profiles_acha_vault_mais_recente(tmp_path):
    from core.auto_repair import _scan_user_profiles_for_obsidian
    users = tmp_path / "Users"
    vault_novo = tmp_path / "vault-novo"
    vault_velho = tmp_path / "vault-velho"
    vault_novo.mkdir()
    vault_velho.mkdir()
    for user, vault, ts in (("ana", vault_velho, 100), ("alex", vault_novo, 200)):
        cfg = users / user / "AppData" / "Roaming" / "obsidian"
        cfg.mkdir(parents=True)
        (cfg / "obsidian.json").write_text(
            json.dumps({"vaults": {"x": {"path": str(vault), "ts": ts}}}),
            encoding="utf-8",
        )
    assert _scan_user_profiles_for_obsidian(users) == vault_novo


def test_scan_user_profiles_none_sem_config(tmp_path):
    from core.auto_repair import _scan_user_profiles_for_obsidian
    assert _scan_user_profiles_for_obsidian(tmp_path / "vazio") is None


def test_handle_error_nunca_levanta(tmp_path):
    # Mesmo com vault quebrado e retry que explode, não pode levantar.
    def boom():
        raise RuntimeError("tudo quebrou")

    outcome = handle_error(
        TimeoutError("x"),
        context={"component": "t"},
        retry=boom,
        vault_path=tmp_path / "nao-existe",
    )
    assert outcome.fixed is False
    assert outcome.error_class == ErrorClass.COMPLEX

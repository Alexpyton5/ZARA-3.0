"""AUDITORIA_2026-08-27: sistema de plugins (inspirado no Mark LI, escrito do
zero). Capacidade nova = arquivo solto em plugins/, sem editar
core/actions/__init__.py. Um plugin quebrado nao pode derrubar o resto."""
from __future__ import annotations

import core.actions
from core.actions import _load_plugins
from core.action_registry import get_registry


def test_plugin_loader_registers_the_real_example_plugin():
    assert get_registry().get_spec("exemplo_piada") is not None


def test_broken_plugin_does_not_crash_the_loader_and_good_ones_still_load(tmp_path, capsys):
    (tmp_path / "bom.py").write_text(
        "from core.action_registry import ActionResult, action\n"
        "@action(name='plugin_teste_bom', category='plugin')\n"
        "def plugin_teste_bom_action():\n"
        "    return ActionResult(success=True, output='ok')\n",
        encoding="utf-8",
    )
    (tmp_path / "quebrado.py").write_text(
        "isso nao e python valido !!! ][\n",
        encoding="utf-8",
    )

    _load_plugins(plugins_dir=tmp_path)

    assert get_registry().get_spec("plugin_teste_bom") is not None
    captured = capsys.readouterr()
    assert "BROKEN quebrado.py" in captured.out


def test_loader_is_a_no_op_when_plugins_folder_does_not_exist(tmp_path):
    _load_plugins(plugins_dir=tmp_path / "nao-existe")

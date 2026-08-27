"""AUDITORIA_2026-08-27 item 1.4 — core/storage.py e core/paths.py tinham
duas funcoes user_data_dir() com bases diferentes (ZARA3/data vs ZARA3).
A de storage.py nunca era importada por ninguem (confirmado por busca no
repo inteiro); foi removida. Este teste tranca que ela nao volta por engano
e que core.paths continua sendo a unica fonte de verdade re-exportada por
core/__init__.py.
"""
from __future__ import annotations

import core
import core.paths
import core.storage


def test_storage_has_no_duplicate_user_data_dir():
    assert not hasattr(core.storage, "user_data_dir")


def test_core_package_exports_paths_user_data_dir():
    assert core.user_data_dir is core.paths.user_data_dir

"""Entry canary must report the packaged Lab's persisted source workspace."""

import json
import sqlite3
from contextlib import closing

import pytest

from tools.electron_lab_canary import inspect_entry_workspace


def _checkout(root):
    for name in (
        '.git/HEAD', 'tools/build_current.py', 'core/lab_v1/autopilot.py',
        'core/lab_v1/evolution.py',
    ):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
    (root / 'pyproject.toml').write_text('[project]\nname = "zara-3.0"\n', encoding='utf-8')
    return root


def _policy_db(path, workspace):
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute('CREATE TABLE lab_autonomy_policy(id INTEGER PRIMARY KEY, document TEXT NOT NULL)')
        conn.execute('INSERT INTO lab_autonomy_policy VALUES(1, ?)',
                     (json.dumps({'workspace': str(workspace)}),))
    return path


def _snapshot(workspace, state='STOPPED'):
    return {'autonomy_policy': {'workspace': str(workspace),
                                'background_task_state': state}}


def test_entry_workspace_accepts_verified_persisted_checkout(tmp_path):
    checkout = _checkout(tmp_path / 'persistent-source')
    database = _policy_db(tmp_path / 'lab.db', checkout)

    assert inspect_entry_workspace(_snapshot(checkout), database, tmp_path / 'canary-home') == checkout.resolve()


@pytest.mark.parametrize('kind', ['missing', 'mei', 'disposable'])
def test_entry_workspace_rejects_missing_or_transient_checkout(tmp_path, kind):
    home = tmp_path / 'canary-home'
    if kind == 'missing':
        workspace = tmp_path / 'missing-source'
    elif kind == 'mei':
        workspace = _checkout(tmp_path / '_MEI123456' / 'source')
    else:
        workspace = _checkout(home / 'source')
    database = _policy_db(tmp_path / 'lab.db', workspace)

    with pytest.raises(RuntimeError, match='PACKAGED_WORKSPACE_NOT_CONFIGURED'):
        inspect_entry_workspace(_snapshot(workspace), database, home)


def test_entry_workspace_requires_same_path_in_sqlite_policy(tmp_path):
    checkout = _checkout(tmp_path / 'persistent-source')
    database = _policy_db(tmp_path / 'lab.db', tmp_path / 'another-source')

    with pytest.raises(RuntimeError, match='PACKAGED_WORKSPACE_NOT_PERSISTED'):
        inspect_entry_workspace(_snapshot(checkout), database, tmp_path / 'canary-home')


def test_entry_workspace_requires_paused_supervisor(tmp_path):
    checkout = _checkout(tmp_path / 'persistent-source')
    database = _policy_db(tmp_path / 'lab.db', checkout)

    with pytest.raises(RuntimeError, match='ENTRY_CANARY_SUPERVISOR_NOT_PAUSED'):
        inspect_entry_workspace(_snapshot(checkout, 'RUNNING'), database,
                                tmp_path / 'canary-home')

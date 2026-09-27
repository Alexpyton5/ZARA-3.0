"""The Agency catalog is read-only until a separate invitation gate exists."""

import json

from core.lab_v1.agency_catalog import default_roster_directory, inspect_agency_roster


def test_missing_roster_is_dormant(tmp_path):
    result = inspect_agency_roster(None, default_directory=tmp_path)
    assert result == {'status': 'DORMANT', 'count': 0, 'agents': [], 'dispatch_enabled': False}


def test_configured_roster_is_read_but_not_dispatched(tmp_path):
    default_dir = tmp_path / 'default'
    configured = tmp_path / 'agency' / 'agency-agents.json'
    configured.parent.mkdir()
    configured.write_text(json.dumps({'agents': [
        {'id': 'researcher-1', 'name': 'Researcher', 'capabilities': ['research'],
         'description': 'Reads public sources'},
        {'id': 'reviewer-1', 'name': 'Reviewer', 'capabilities': ['review']},
    ]}), encoding='utf-8')

    result = inspect_agency_roster(str(configured), default_directory=default_dir)
    assert result['status'] == 'READY'
    assert result['count'] == 2
    assert result['dispatch_enabled'] is False
    assert [agent['id'] for agent in result['agents']] == ['researcher-1', 'reviewer-1']


def test_invalid_roster_never_becomes_ready(tmp_path):
    path = tmp_path / 'agency-agents.json'
    path.write_text(json.dumps({'agents': [
        {'id': 'same', 'name': 'First', 'capabilities': []},
        {'id': 'same', 'name': 'Second', 'capabilities': []},
    ]}), encoding='utf-8')

    result = inspect_agency_roster(None, default_directory=tmp_path)
    assert result['status'] == 'INVALID'
    assert result['count'] == 0
    assert result['agents'] == []
    assert result['dispatch_enabled'] is False


def test_roster_path_must_be_absolute_and_named_for_agency(tmp_path):
    for configured in ('relative/agency-agents.json', str(tmp_path / '.env')):
        result = inspect_agency_roster(configured, default_directory=tmp_path)
        assert result['status'] == 'INVALID_CONFIG'
        assert result['agents'] == []


def test_unsupported_schema_version_is_invalid(tmp_path):
    path = tmp_path / 'agency-agents.json'
    path.write_text(json.dumps({'schema_version': 2, 'agents': []}), encoding='utf-8')
    assert inspect_agency_roster(None, default_directory=tmp_path)['status'] == 'INVALID'


def test_default_directory_follows_isolated_zara_home_without_creating_it(tmp_path, monkeypatch):
    home = tmp_path / 'isolated-home'
    monkeypatch.setenv('ZARA3_HOME', str(home))
    assert default_roster_directory() == home / 'data'
    assert not home.exists()


def test_d_volume_is_rejected_before_read(tmp_path):
    result = inspect_agency_roster('D:\\agency-agents.json', default_directory=tmp_path)
    assert result['status'] == 'INVALID_CONFIG'
    assert result['agents'] == []

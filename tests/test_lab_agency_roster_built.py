"""O roster real do Lab (Agency Agents) passa no catalogo do Lab V1."""

import json
from pathlib import Path

from core.lab_v1.agency_catalog import inspect_agency_roster

ROSTER_JSON = Path(__file__).resolve().parent.parent / "lab" / "roster" / "agency-agents.json"


def test_built_roster_is_ready():
    assert ROSTER_JSON.exists(), "rode o build do roster (lab/roster)"
    result = inspect_agency_roster(str(ROSTER_JSON), default_directory=ROSTER_JSON.parent)
    assert result["status"] == "READY"
    assert result["count"] > 0
    assert result["dispatch_enabled"] is False


def test_built_roster_matches_md_files():
    md_files = sorted((ROSTER_JSON.parent).glob("*/*.md"))
    result = inspect_agency_roster(str(ROSTER_JSON), default_directory=ROSTER_JSON.parent)
    assert result["count"] == len(md_files)
    ids = [agent["id"] for agent in result["agents"]]
    assert len({i.casefold() for i in ids}) == len(ids), "ids duplicados no roster"
    # o catalogo retorna so id/name/capabilities/description/source; o caminho
    # do .md vem do JSON bruto
    raw = {a["id"]: a for a in json.loads(ROSTER_JSON.read_text(encoding="utf-8"))["agents"]}
    assert set(raw) == set(ids)
    for agent_id, entry in raw.items():
        assert entry["name"] and entry["capabilities"]
        rel = entry["roster_path"].replace("lab/roster/", "")
        assert (ROSTER_JSON.parent / rel).exists(), agent_id

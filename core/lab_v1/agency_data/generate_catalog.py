"""Rebuild the bundled Agency Agents catalog from a pinned local Git checkout.

Usage: python -m core.lab_v1.agency_data.generate_catalog --source PATH
The generator requires no third-party Python packages or network access.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import subprocess
import zlib
from pathlib import Path

SOURCE_URL = "https://github.com/msitarzewski/agency-agents"
OUTPUT = Path(__file__).with_name("catalog_payload.py")


def _frontmatter(markdown: str, path: Path) -> dict[str, str]:
    lines = markdown.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError(f"Agent has no frontmatter: {path}")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError(f"Agent frontmatter is not closed: {path}") from exc
    values: dict[str, str] = {}
    for line in lines[1:end]:
        match = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if not match:
            continue
        key, value = match.groups()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key] = value
    if not values.get("name") or not values.get("description"):
        raise ValueError(f"Agent needs a name and description: {path}")
    return values


def _source_commit(source: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def generate(source: Path, output: Path = OUTPUT) -> tuple[int, str]:
    source = source.resolve(strict=True)
    division_data = json.loads((source / "divisions.json").read_text(encoding="utf-8"))
    divisions = {
        key: value["label"] for key, value in division_data["divisions"].items()
    }
    source_commit = _source_commit(source)
    license_text = (source / "LICENSE").read_text(encoding="utf-8")
    rows = []
    for division in sorted(divisions):
        for path in sorted((source / division).glob("*.md"), key=lambda item: item.name.casefold()):
            source_bytes = path.read_bytes()
            markdown = source_bytes.decode("utf-8-sig").replace("\r\n", "\n")
            fields = _frontmatter(markdown, path)
            source_path = path.relative_to(source).as_posix()
            rows.append({
                "id": f"{division}/{path.stem}",
                "name": fields["name"],
                "description": fields["description"],
                "division": division,
                "emoji": fields.get("emoji", ""),
                "vibe": fields.get("vibe", ""),
                "source_path": source_path,
                "source_url": f"{SOURCE_URL}/blob/{source_commit}/{source_path}",
                "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
                "instructions": markdown,
            })
    rows.sort(key=lambda row: (row["division"], row["name"].casefold(), row["id"]))
    identifiers = [row["id"] for row in rows]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate Agency Agents catalog ID")
    payload = base64.b85encode(zlib.compress(
        json.dumps(rows, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        level=9,
    )).decode("ascii")
    chunks = "\n".join(f"    {payload[i:i + 110]!r}" for i in range(0, len(payload), 110))
    module = (
        '"""Generated Agency Agents catalog. Do not edit manually.\n\n'
        f"Source: {SOURCE_URL}/tree/{source_commit}\n"
        'Regenerate with: python -m core.lab_v1.agency_data.generate_catalog --source PATH\n'
        '"""\n\n'
        f"AGENT_COUNT = {len(rows)}\n"
        f"SOURCE_URL = {SOURCE_URL!r}\n"
        f"SOURCE_COMMIT = {source_commit!r}\n"
        f"DIVISIONS = {divisions!r}\n"
        f"LICENSE_TEXT = {license_text!r}\n"
        f"PAYLOAD = (\n{chunks}\n)\n"
    )
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(module)
    return len(rows), source_commit


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    arguments = parser.parse_args()
    count, commit = generate(arguments.source, arguments.output)
    print(f"Bundled {count} Agency Agents profiles from {commit}")


if __name__ == "__main__":
    main()

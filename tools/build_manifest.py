"""Manifesto deterministico para uma lista explicita de artefatos aprovados."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from collections.abc import Sequence
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "zara.build-manifest.v1"
_FORBIDDEN_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "_quarentena",
    "data",
    "memory",
    "node_modules",
    "snapshots",
}
_SECRET_NAME_PARTS = ("credential", "password", "private_key", "secret", "token")
_SECRET_SUFFIXES = (".key", ".p12", ".pem", ".pfx")
_CONFIG_SUFFIXES = {".cfg", ".env", ".ini", ".json", ".toml", ".txt", ".yaml", ".yml"}
_ASSIGNMENT_RE = re.compile(
    rb"(?im)(?:^|[,{])\s*[\"']?(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password|secret)[\"']?\s*[:=]\s*[\"']?([^\s\"',}]{12,})"
)
_SAFE_VALUE_MARKERS = (
    b"${",
    b"<",
    b"changeme",
    b"example",
    b"os.getenv",
    b"placeholder",
    b"process.env",
    b"your_",
)


class ManifestError(ValueError):
    pass


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _normalize_approved_path(raw: str) -> PurePosixPath:
    if not isinstance(raw, str) or not raw.strip():
        raise ManifestError("caminho aprovado vazio")
    normalized = raw.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        path.is_absolute()
        or path.anchor
        or re.match(r"^[A-Za-z]:", normalized)
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ManifestError(f"caminho precisa ser relativo e normalizado: {raw!r}")
    lowered_parts = {part.casefold() for part in path.parts}
    if lowered_parts & _FORBIDDEN_PARTS:
        raise ManifestError(f"caminho proibido no build: {path.as_posix()}")
    name = path.name.casefold()
    if name == ".env" or name.startswith(".env."):
        raise ManifestError(f"arquivo de ambiente proibido: {path.as_posix()}")
    if name.endswith(_SECRET_SUFFIXES) or any(marker in name for marker in _SECRET_NAME_PARTS):
        raise ManifestError(f"nome sensivel proibido: {path.as_posix()}")
    return path


def _read_approved_file(root: Path, relative: PurePosixPath) -> bytes:
    candidate = root.joinpath(*relative.parts)
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ManifestError(f"links simbolicos nao sao aceitos: {relative.as_posix()}")
    if not candidate.exists():
        raise FileNotFoundError(relative.as_posix())
    if not candidate.is_file():
        raise ManifestError(f"somente arquivos explicitos sao aceitos: {relative.as_posix()}")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ManifestError(f"arquivo escapou da raiz: {relative.as_posix()}") from exc
    return candidate.read_bytes()


def _contains_probable_secret(path: PurePosixPath, data: bytes) -> bool:
    if b"-----BEGIN PRIVATE KEY-----" in data or b"-----BEGIN OPENSSH PRIVATE KEY-----" in data:
        return True
    if path.suffix.casefold() not in _CONFIG_SUFFIXES or len(data) > 2_000_000:
        return False
    for match in _ASSIGNMENT_RE.finditer(data):
        value = match.group(1).lower()
        if not any(marker in value for marker in _SAFE_VALUE_MARKERS):
            return True
    return False


def generate_manifest(project_root: Path | str, approved_paths: Sequence[str]) -> dict[str, Any]:
    root = Path(project_root).resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(root)
    normalized = [_normalize_approved_path(path) for path in approved_paths]
    if not normalized:
        raise ManifestError("ao menos um artefato aprovado e obrigatorio")
    keys = [path.as_posix().casefold() for path in normalized]
    if len(keys) != len(set(keys)):
        raise ManifestError("caminho aprovado duplicado")

    entries: list[dict[str, Any]] = []
    for relative in sorted(normalized, key=lambda path: (path.as_posix().casefold(), path.as_posix())):
        data = _read_approved_file(root, relative)
        if _contains_probable_secret(relative, data):
            raise ManifestError(f"conteudo potencialmente sensivel recusado: {relative.as_posix()}")
        entries.append(
            {
                "path": relative.as_posix(),
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
            }
        )
    return {"schema": SCHEMA, "artifacts": entries}


def verify_manifest(project_root: Path | str, manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise ManifestError("schema de manifesto invalido")
    raw_entries = manifest.get("artifacts")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ManifestError("lista de artefatos invalida")

    approved: list[str] = []
    expected: dict[str, tuple[str, int]] = {}
    for entry in raw_entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size"}:
            raise ManifestError("entrada de manifesto invalida")
        relative = _normalize_approved_path(entry["path"])
        digest = entry["sha256"]
        size = entry["size"]
        if (
            not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or isinstance(size, bool)
            or not isinstance(size, int)
            or size < 0
        ):
            raise ManifestError(f"hash ou tamanho invalido: {relative.as_posix()}")
        key = relative.as_posix().casefold()
        if key in expected:
            raise ManifestError("entrada duplicada no manifesto")
        approved.append(relative.as_posix())
        expected[key] = (digest, size)

    missing: list[str] = []
    changed: list[str] = []
    try:
        current = generate_manifest(project_root, approved)
    except FileNotFoundError as exc:
        missing.append(str(exc))
        # Continue item a item so the report includes every missing/changed path.
        current = {"artifacts": []}

    current_by_key = {entry["path"].casefold(): entry for entry in current["artifacts"]}
    root = Path(project_root).resolve(strict=True)
    for raw in approved:
        key = raw.casefold()
        if key in current_by_key:
            entry = current_by_key[key]
            if (entry["sha256"], entry["size"]) != expected[key]:
                changed.append(raw)
            continue
        relative = _normalize_approved_path(raw)
        try:
            data = _read_approved_file(root, relative)
        except FileNotFoundError:
            if raw not in missing:
                missing.append(raw)
            continue
        if _contains_probable_secret(relative, data):
            changed.append(raw)
            continue
        digest = hashlib.sha256(data).hexdigest()
        if (digest, len(data)) != expected[key]:
            changed.append(raw)

    missing.sort(key=str.casefold)
    changed.sort(key=str.casefold)
    return {
        "verdict": "ok" if not missing and not changed else "failed",
        "missing": missing,
        "changed": changed,
        "checked": len(approved),
    }


def write_manifest(path: Path | str, manifest: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = _canonical_json(manifest) + "\n"
    handle, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create", allow_abbrev=False)
    create.add_argument("--root", type=Path, required=True)
    create.add_argument("--allow", action="append", required=True)
    create.add_argument("--output", type=Path, required=True)
    verify = subparsers.add_parser("verify", allow_abbrev=False)
    verify.add_argument("--root", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "create":
            manifest = generate_manifest(args.root, args.allow)
            write_manifest(args.output, manifest)
            report = {"verdict": "created", "artifacts": len(manifest["artifacts"])}
            print(_canonical_json(report))
            return 0
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        report = verify_manifest(args.root, manifest)
        print(_canonical_json(report))
        return 0 if report["verdict"] == "ok" else 1
    except (ManifestError, FileNotFoundError, NotADirectoryError, OSError, json.JSONDecodeError) as exc:
        print(_canonical_json({"verdict": "error", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

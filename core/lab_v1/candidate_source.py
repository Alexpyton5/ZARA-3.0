"""Bounded real-source snapshots for ZARA Lab repair candidates.

This module never writes to the source workspace.  It copies explicitly
authorized Python files into a mission sandbox, applies structured edits there,
and runs focused pytest targets against disposable copies of that sandbox.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
import os
import re
import site
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath


class CandidateSourceError(ValueError):
    """A candidate source request crossed a bounded-workspace rule."""


#: The sandbox network stance, stated once and quoted verbatim by the runner.
#: On Windows every asyncio event loop builds its internal self-pipe with
#: ``socket.socketpair()``, which CPython emulates as an ephemeral loopback
#: bind+connect inside ``socket._fallback_socketpair``.  That is process-local
#: IPC, not reachable network, so exactly that one primitive is allowed and
#: every other socket operation stays denied.
SANDBOX_NETWORK_POLICY = "ASYNC LOCAL: ALLOWED; EXTERNAL NETWORK: DENIED"


@dataclass(frozen=True)
class SnapshotResult:
    source_root: Path
    baseline_root: Path
    manifest_path: Path
    files: int

    def to_dict(self) -> dict:
        return {
            "source_root": str(self.source_root),
            "baseline_root": str(self.baseline_root),
            "manifest_path": str(self.manifest_path),
            "files": self.files,
        }


@dataclass(frozen=True)
class ChangeResult:
    diff: str
    files_changed: int
    source_files_changed: int
    lines_added: int
    lines_deleted: int
    hashes: dict[str, dict[str, str | None]]
    evidence_path: Path
    edits_applied: list[dict] = field(default_factory=list)
    objective_files_changed: int = 0

    def to_dict(self) -> dict:
        return {
            "diff": self.diff,
            "files_changed": self.files_changed,
            "source_files_changed": self.source_files_changed,
            "objective_files_changed": self.objective_files_changed,
            "lines_added": self.lines_added,
            "lines_deleted": self.lines_deleted,
            "hashes": self.hashes,
            "evidence_path": str(self.evidence_path),
            "edits_applied": self.edits_applied,
        }


@dataclass(frozen=True)
class TestResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool
    baseline: bool
    run_root: Path
    counts: dict[str, int]
    test_hashes: dict[str, str]

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "baseline": self.baseline,
            "run_root": str(self.run_root),
            "counts": self.counts,
            "test_hashes": self.test_hashes,
        }


_MAX_EDIT_FILES = 24
_MAX_FILE_BYTES = 512 * 1024
_MAX_SNAPSHOT_FILES = 5000
_MAX_TEST_OUTPUT = 250_000
_NODE_SUFFIX = re.compile(r"^[A-Za-z0-9_.,:/\[\]\-]+$")
_SOURCE_EXTENSIONS = frozenset({".py", ".ts", ".tsx", ".js", ".css", ".json", ".svg", ".html"})
_SOURCE_ROOTS = ("core", "memory", "frontend/src", "assets", "tests")
# Normalise Windows line endings to LF for source/text files so that anchored
# edits and diff generation stay byte-consistent between workspace, baseline and
# candidate copies.  Python source is semantically identical under this rule.
_TEXT_EXTENSIONS = frozenset(_SOURCE_EXTENSIONS | {
    ".md", ".txt", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".sh", ".bat",
    ".ps1", ".scss", ".csv", ".xml", ".sql", ".lock",
})


def _normalize_newlines(data: bytes, relative: str) -> bytes:
    extension = Path(relative).suffix.lower()
    if extension not in _TEXT_EXTENSIONS:
        return data
    if b"\r\n" not in data and b"\r" not in data:
        return data
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
_FORBIDDEN_PARTS = {
    ".git", ".env", "data", "__pycache__", "node_modules", "dist", "build",
    "release", ".pytest_cache", ".ruff_cache", "cache", "generated",
}
_FORBIDDEN_NAMES = ("credential", "secret", "private_key", "api_key", "package-lock", "package.json")


# A real ZARA module can be larger than any single context budget
# (``core/lab_v1/service.py`` alone is over 50 000 characters). Refusing to read
# it killed every mission that needed it. The answer is not a bigger number: the
# file is delivered as a structure index of the WHOLE file plus the full text of
# the regions that matter, with every missing range named. The marker below is
# the machine-checkable proof that a view is partial.
_PARTIAL_VIEW_MARKER = "ZARA_PARTIAL_SOURCE_VIEW"

# A partial view breaks the old patch protocol: the worker was asked to return
# "the complete file" for a file it was never shown in full. A real Run proved
# the failure mode - the worker answered honestly with the truncated excerpt,
# and a less scrupulous worker would have invented the ranges it never read.
# So a partially viewed file can only be changed by anchored edits: exact,
# unique substrings of the CURRENT source. Everything outside the matched span
# is carried over byte for byte, which is what makes silent truncation
# impossible rather than merely discouraged.
#
# Why anchored search/replace and not a unified diff: the standard library can
# PRODUCE a unified diff (``difflib``) but cannot APPLY one. Applying a diff
# needs hunk offsets and fuzz, and fuzz is exactly the "apply it anyway" that
# requirement 4 forbids. An anchor either matches the real bytes exactly once
# or it is rejected. The factual unified diff is still produced afterwards from
# the real before/after bytes, so the evidence is unchanged.
_CONTEXT_LEDGER_NAME = "context-views.json"
_MAX_ANCHORED_EDITS = 32
_MAX_ANCHOR_CHARS = 60_000
_MAX_INDEX_ENTRIES = 400
_MAX_REGION_LINES = 60
_MIN_PARTIAL_BUDGET = 1_200
_RELEVANCE_SHARE = 0.7
_REGION_MARKER_COST = 96
_SIGNATURE_RE = re.compile(
    r"^(?P<indent>[ \t]*)(?:export\s+(?:default\s+)?)?(?:async\s+)?"
    r"(?:(?:def|class|function|interface|enum|struct)\s+[A-Za-z_$][\w$]*"
    r"|(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*(?:async\s*)?(?:function\b|\())"
)


@dataclass(frozen=True)
class SourceRegion:
    start: int
    end: int
    text: str


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _text_digest(text: str) -> str:
    """Identity of decoded source text, so CRLF/LF alone is never drift."""
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()


def is_partial_view(text: str) -> bool:
    """True when this text is a bounded excerpt, not a whole file."""
    return isinstance(text, str) and _PARTIAL_VIEW_MARKER in text


def _python_anchor_lines(text: str) -> list[tuple[int, int]] | None:
    """Definition line numbers of a parseable Python file, with nesting depth."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        return None
    found: list[tuple[int, int]] = []

    def walk(node, depth: int) -> None:
        for child in getattr(node, "body", ()):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                found.append((child.lineno, depth))
                walk(child, depth + 1)

    walk(tree, 0)
    return sorted(set(found))


def structure_index(text: str, relative: str = "") -> list[dict]:
    """Every definition in the file with its real line number.

    The index always describes the WHOLE file, even when the body is cut: a
    worker that can only see part of a file must still be able to name what it
    cannot see, and where it lives.
    """
    lines = text.splitlines()
    anchors = _python_anchor_lines(text) if relative.endswith(".py") else None
    if anchors is None:
        anchors = []
        for number, line in enumerate(lines, start=1):
            match = _SIGNATURE_RE.match(line)
            if match:
                anchors.append((number, len(match.group("indent").expandtabs(4)) // 4))
    return [
        {"line": number, "depth": depth, "signature": lines[number - 1].strip()[:160]}
        for number, depth in anchors
        if 1 <= number <= len(lines)
    ]


def source_regions(text: str, entries: list[dict], *,
                   max_region_lines: int = _MAX_REGION_LINES) -> list[SourceRegion]:
    """Split the file at definition boundaries, then cap each piece by lines."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return []
    starts = sorted({1, *(entry["line"] for entry in entries if 1 <= entry["line"] <= len(lines))})
    regions: list[SourceRegion] = []
    for index, start in enumerate(starts):
        end = (starts[index + 1] - 1) if index + 1 < len(starts) else len(lines)
        for window in range(start, end + 1, max_region_lines):
            stop = min(window + max_region_lines - 1, end)
            regions.append(SourceRegion(window, stop, "".join(lines[window - 1:stop])))
    return regions


def _ranked_regions(regions: list[SourceRegion], focus: str | None) -> list[int]:
    """Rank regions against the mission's own evidence, best first.

    Reuses the project's existing local TF-IDF retrieval (``core.local_rag``)
    instead of inventing a second scorer or adding an embeddings dependency.
    """
    if not regions or not focus or not str(focus).strip():
        return []
    from core.local_rag import Document, build_index, query

    index = build_index([Document(path=str(position), text=region.text)
                         for position, region in enumerate(regions)])
    return [int(hit.path) for hit in query(index, str(focus), top_k=len(regions))]


def _select_regions(regions: list[SourceRegion], focus: str | None, budget: int) -> list[SourceRegion]:
    """Relevant regions first, then guaranteed head/middle/tail coverage."""
    chosen: set[int] = set()
    used = 0

    def take(position: int, cap: int) -> None:
        nonlocal used
        if position in chosen or not 0 <= position < len(regions):
            return
        cost = len(regions[position].text) + _REGION_MARKER_COST
        if used + cost > cap:
            return
        chosen.add(position)
        used += cost

    for position in _ranked_regions(regions, focus):
        take(position, int(budget * _RELEVANCE_SHARE))
    for position in (0, len(regions) // 2, len(regions) - 1):
        take(position, budget)
    for position in range(len(regions)):
        take(position, budget)
    return [regions[position] for position in sorted(chosen)]


def bounded_source_view(relative: str, text: str, budget: int, focus: str | None = None) -> str:
    """A partial file view that says, in its own text, that it is partial."""
    entries = structure_index(text, relative)
    regions = source_regions(text, entries)
    total_lines = len(text.splitlines())
    header = "\n".join([
        f"### {_PARTIAL_VIEW_MARKER} {relative}",
        "### THIS IS A PARTIAL VIEW. IT IS NOT THE COMPLETE FILE.",
        f"### REAL FILE: {total_lines} lines, {len(text)} characters.",
        "### Missing ranges are marked OMITTED with their real line numbers.",
        "### NEVER write this text back as file content, and never assume an OMITTED range is empty.",
        "### If the task needs the whole file and you can only see part of it, say so instead of "
        "inventing the rest.",
        "### STRUCTURE INDEX (every definition in the real file, real line numbers):",
    ]) + "\n"

    index_lines = [f"###   L{entry['line']} {'  ' * entry['depth']}{entry['signature']}\n"
                   for entry in entries[:_MAX_INDEX_ENTRIES]]
    if len(entries) > len(index_lines):
        index_lines.append(f"###   ... {len(entries) - len(index_lines)} further definitions "
                           "exist and are omitted from this index\n")
    index_budget = max(0, min(budget - len(header), budget // 2))
    while index_lines and sum(len(line) for line in index_lines) > index_budget:
        dropped = index_lines.pop()
        if not dropped.startswith("###   ... "):
            index_lines.append(f"###   ... index truncated; the real file has {len(entries)} "
                               "definitions\n")
    index = "".join(index_lines)

    region_budget = max(0, budget - len(header) - len(index) - _REGION_MARKER_COST)
    body: list[str] = ["### SOURCE (real line numbers, file order):\n"]
    cursor = 1
    for region in _select_regions(regions, focus, region_budget):
        if region.start > cursor:
            body.append(f"--- OMITTED lines {cursor}-{region.start - 1} "
                        f"({region.start - cursor} lines) ---\n")
        body.append(f"--- lines {region.start}-{region.end} ---\n")
        body.append(region.text if region.text.endswith("\n") else region.text + "\n")
        cursor = region.end + 1
    if cursor <= total_lines:
        body.append(f"--- OMITTED lines {cursor}-{total_lines} "
                    f"({total_lines - cursor + 1} lines) ---\n")
    return header + index + "".join(body)


def _same_source_text(left: bytes, right: bytes) -> bool:
    """Treat Windows and Unix line endings as the same UTF-8 source text."""
    return left.decode("utf-8").replace("\r\n", "\n") == right.decode("utf-8").replace(
        "\r\n", "\n"
    )


def _normalise_relative(value: str) -> str:
    if not isinstance(value, str) or not value.strip() or "\x00" in value:
        raise CandidateSourceError("PATH_FORBIDDEN: a non-empty relative path is required")
    normal = value.replace("\\", "/")
    path = PurePosixPath(normal)
    if (
        path.is_absolute()
        or normal.startswith("//")
        or any(part in {"", ".", ".."} for part in path.parts)
        or (path.parts and ":" in path.parts[0])
    ):
        raise CandidateSourceError(f"PATH_FORBIDDEN: {value}")
    return path.as_posix()


def _contains_forbidden_part(relative: str) -> bool:
    for part in PurePosixPath(relative).parts:
        lowered = part.lower()
        if (lowered in _FORBIDDEN_PARTS or "hermes" in lowered
                or any(marker in lowered for marker in _FORBIDDEN_NAMES)):
            return True
    return False


def _is_safe_source_path(relative: str) -> bool:
    path = PurePosixPath(relative)
    if path.suffix.lower() not in _SOURCE_EXTENSIONS or _contains_forbidden_part(relative):
        return False
    return any(relative == root or relative.startswith(root + "/") for root in _SOURCE_ROOTS)


def _is_test_path(relative: str) -> bool:
    parts = PurePosixPath(relative).parts
    return bool(parts) and (parts[0].lower() == "tests" or parts[-1].startswith("test_"))


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


class CandidateSource:
    """Own a source candidate whose mutable boundary is an explicit file list.

    ``allowed_paths`` are exact safe source-text files and are the only editable files.
    One absent path is permitted when it is an explicitly named regression test.
    ``support_paths`` may contain files or directories; their safe source files are
    copied for imports but remain immutable.  Hermes-named files are excluded.
    """

    def __init__(
        self,
        workspace: Path,
        sandbox: Path,
        allowed_paths: list[str],
        *,
        support_paths: Iterable[str] = (),
        python_executable: Path | None = None,
        runtime_drift_paths: Iterable[str] = (),
        objective_paths: Iterable[str] = (),
    ) -> None:
        self.workspace = Path(workspace).resolve(strict=True)
        if not self.workspace.is_dir() or self.workspace.is_symlink():
            raise CandidateSourceError("WORKSPACE_INVALID")
        self.sandbox = Path(sandbox).resolve(strict=False)
        if self.sandbox == self.workspace:
            raise CandidateSourceError("SANDBOX_INVALID: workspace itself is forbidden")
        if not allowed_paths or len(allowed_paths) > _MAX_EDIT_FILES:
            raise CandidateSourceError("ALLOWED_PATHS_LIMIT")

        editable: list[str] = []
        for raw in allowed_paths:
            relative = _normalise_relative(raw)
            if not _is_safe_source_path(relative):
                raise CandidateSourceError(f"PATH_FORBIDDEN: {relative}")
            if relative in editable:
                raise CandidateSourceError(f"DUPLICATE_PATH: {relative}")
            editable.append(relative)

        support: list[str] = []
        for raw in support_paths:
            relative = _normalise_relative(raw)
            if _contains_forbidden_part(relative):
                raise CandidateSourceError(f"PATH_FORBIDDEN: {relative}")
            if relative not in support:
                support.append(relative)

        self.allowed_paths = tuple(editable)
        self.support_paths = tuple(support)

        # What this mission is actually ABOUT, decided upstream from mission
        # evidence (``source_work['source_paths']``, chosen by select_source_scope
        # from the owner intent) - never by the worker. It is the only thing that
        # can tell "the objective IS to fix a test file" apart from "the worker
        # edited a test file to look busy". Empty = legacy behaviour.
        objective: list[str] = []
        for raw in objective_paths:
            relative = _normalise_relative(raw)
            if relative not in self.allowed_paths:
                raise CandidateSourceError(f"OBJECTIVE_PATH_NOT_EDITABLE: {relative}")
            if relative not in objective:
                objective.append(relative)
        self.objective_paths = tuple(objective)
        self.objective_test_paths = tuple(p for p in objective if _is_test_path(p))
        self.objective_source_paths = tuple(p for p in objective if not _is_test_path(p))
        if tuple(runtime_drift_paths):
            raise CandidateSourceError("RUNTIME_DRIFT_PATHS_FORBIDDEN")
        self.runtime_drift_paths = frozenset()
        self.source_root = self.sandbox / "source"
        self.baseline_root = self.sandbox / "baseline"
        self.manifest_path = self.sandbox / "manifest.json"
        self.python_executable = (
            Path(python_executable).resolve(strict=False)
            if python_executable is not None
            else self.workspace / ".venv" / "Scripts" / "python.exe"
        )
        self._manifest: dict[str, dict] = {}
        self._prepared = False

    def _workspace_path(self, relative: str, *, may_be_missing: bool = False) -> Path:
        path = self.workspace.joinpath(*PurePosixPath(relative).parts)
        resolved = path.resolve(strict=False)
        if not _inside(resolved, self.workspace):
            raise CandidateSourceError(f"PATH_FORBIDDEN: {relative}")
        self._reject_symlinks(path, self.workspace, allow_missing_leaf=may_be_missing)
        return path

    @staticmethod
    def _reject_symlinks(path: Path, root: Path, *, allow_missing_leaf: bool = False) -> None:
        try:
            relative = path.relative_to(root)
        except ValueError as exc:
            raise CandidateSourceError("PATH_FORBIDDEN") from exc
        current = root
        for index, part in enumerate(relative.parts):
            current = current / part
            if current.is_symlink():
                raise CandidateSourceError(f"SYMLINK_FORBIDDEN: {current}")
            if not current.exists() and not (allow_missing_leaf and index == len(relative.parts) - 1):
                break

    def _add_file(self, files: dict[str, bool], relative: str, editable: bool) -> None:
        if not _is_safe_source_path(relative):
            return
        files[relative] = files.get(relative, False) or editable

    def _add_package_initializers(self, files: dict[str, bool], relative: str) -> None:
        parts = PurePosixPath(relative).parts[:-1]
        for depth in range(1, len(parts) + 1):
            init_rel = PurePosixPath(*parts[:depth], "__init__.py").as_posix()
            init_path = self._workspace_path(init_rel, may_be_missing=True)
            if init_path.is_file():
                self._add_file(files, init_rel, False)

    def prepare(self) -> SnapshotResult:
        if self._prepared or self.source_root.exists() or self.baseline_root.exists():
            raise CandidateSourceError("ALREADY_PREPARED")
        self.sandbox.mkdir(parents=True, exist_ok=True)
        if self.sandbox.is_symlink():
            raise CandidateSourceError("SYMLINK_FORBIDDEN: sandbox")
        self.source_root.mkdir()
        self.baseline_root.mkdir()

        files: dict[str, bool] = {}
        for support in self.support_paths:
            path = self._workspace_path(support)
            if path.is_file():
                relative = path.relative_to(self.workspace).as_posix()
                self._add_file(files, relative, False)
            elif path.is_dir():
                for child in sorted(path.rglob("*")):
                    if not child.is_file():
                        continue
                    relative = child.relative_to(self.workspace).as_posix()
                    if _contains_forbidden_part(relative):
                        continue
                    self._reject_symlinks(child, self.workspace)
                    self._add_file(files, relative, False)
                    if len(files) > _MAX_SNAPSHOT_FILES:
                        raise CandidateSourceError("SNAPSHOT_FILE_LIMIT")
            else:
                raise CandidateSourceError(f"SUPPORT_PATH_MISSING: {support}")

        for relative in self.allowed_paths:
            path = self._workspace_path(relative, may_be_missing=True)
            if path.exists() and not path.is_file():
                raise CandidateSourceError(f"FILE_REQUIRED: {relative}")
            if not path.exists() and not _is_test_path(relative):
                raise CandidateSourceError(f"SOURCE_FILE_MISSING: {relative}")
            self._add_file(files, relative, True)
            self._add_package_initializers(files, relative)

        if any(_is_test_path(path) for path in self.allowed_paths):
            conftest = self._workspace_path("tests/conftest.py", may_be_missing=True)
            if conftest.is_file():
                self._add_file(files, "tests/conftest.py", False)

        entries: list[dict] = []
        for relative, editable in sorted(files.items()):
            original = self._workspace_path(relative, may_be_missing=True)
            exists = original.is_file()
            data = _normalize_newlines(original.read_bytes(), relative) if exists else None
            entry = {
                "path": relative,
                "original_path": str(original),
                "before_sha256": _digest(data) if data is not None else None,
                "bytes": len(data) if data is not None else 0,
                "exists": exists,
                "editable": editable,
            }
            entries.append(entry)
            self._manifest[relative] = entry
            if data is None:
                continue
            for root in (self.source_root, self.baseline_root):
                destination = root.joinpath(*PurePosixPath(relative).parts)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)

        document = {
            "version": 1,
            "workspace": str(self.workspace),
            "source_root": str(self.source_root),
            "allowed_paths": list(self.allowed_paths),
            "support_paths": list(self.support_paths),
            "files": entries,
        }
        with self.manifest_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(document, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        self._prepared = True
        return SnapshotResult(self.source_root, self.baseline_root, self.manifest_path, len(entries))

    def resume(self) -> SnapshotResult:
        """Securely reopen a snapshot created by :meth:`prepare`.

        The manifest is bound to this constructor's workspace and authorization
        lists.  The immutable baseline and support files must still match the
        production snapshot; only explicitly editable candidate files may differ.
        """
        if self._prepared:
            return SnapshotResult(
                self.source_root, self.baseline_root, self.manifest_path, len(self._manifest)
            )
        if (
            not self.manifest_path.is_file()
            or not self.source_root.is_dir()
            or not self.baseline_root.is_dir()
        ):
            raise CandidateSourceError("SNAPSHOT_MISSING")
        self._reject_symlinks(self.manifest_path, self.sandbox)
        self._reject_symlinks(self.source_root, self.sandbox)
        self._reject_symlinks(self.baseline_root, self.sandbox)
        try:
            document = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CandidateSourceError("MANIFEST_INVALID") from exc
        if (
            not isinstance(document, dict)
            or document.get("version") != 1
            or document.get("workspace") != str(self.workspace)
            or document.get("source_root") != str(self.source_root)
            or document.get("allowed_paths") != list(self.allowed_paths)
            or document.get("support_paths") != list(self.support_paths)
            or not isinstance(document.get("files"), list)
        ):
            raise CandidateSourceError("MANIFEST_BINDING_MISMATCH")

        manifest: dict[str, dict] = {}
        required_keys = {
            "path",
            "original_path",
            "before_sha256",
            "bytes",
            "exists",
            "editable",
        }
        for entry in document["files"]:
            if not isinstance(entry, dict) or set(entry) != required_keys:
                raise CandidateSourceError("MANIFEST_INVALID")
            relative = _normalise_relative(entry["path"])
            original = self._workspace_path(relative, may_be_missing=True)
            expected_editable = relative in self.allowed_paths
            if (
                relative in manifest
                or _contains_forbidden_part(relative)
                or entry["original_path"] != str(original)
                or entry["editable"] is not expected_editable
                or type(entry["exists"]) is not bool
                or type(entry["bytes"]) is not int
                or entry["bytes"] < 0
                or (
                    entry["before_sha256"] is not None
                    and not re.fullmatch(r"[0-9a-f]{64}", entry["before_sha256"])
                )
            ):
                raise CandidateSourceError("MANIFEST_INVALID")
            if entry["exists"] is not (entry["before_sha256"] is not None):
                raise CandidateSourceError("MANIFEST_INVALID")
            manifest[relative] = entry
        if set(self.allowed_paths) - set(manifest):
            raise CandidateSourceError("MANIFEST_BINDING_MISMATCH")

        self._manifest = manifest
        self._prepared = True
        try:
            self._verify_baseline()
            present_source = {
                path.relative_to(self.source_root).as_posix()
                for path in self.source_root.rglob("*")
                if path.is_file() and _is_safe_source_path(path.relative_to(self.source_root).as_posix())
            }
            expected_source = {
                relative
                for relative in manifest
                if self.source_root.joinpath(*PurePosixPath(relative).parts).is_file()
            }
            if present_source != expected_source:
                raise CandidateSourceError("CANDIDATE_FILE_SET_CHANGED")
            for relative, entry in manifest.items():
                original = self._workspace_path(relative, may_be_missing=True)
                if entry["exists"]:
                    if (relative not in self.runtime_drift_paths
                            and (not original.is_file() or _digest(_normalize_newlines(
                                original.read_bytes(), relative
                            )) != entry["before_sha256"])):
                        raise CandidateSourceError(f"SOURCE_WORKSPACE_DRIFT: {relative}")
                elif original.exists():
                    raise CandidateSourceError(f"SOURCE_WORKSPACE_DRIFT: {relative}")
                candidate = self._candidate_bytes(relative)
                if not entry["editable"]:
                    if candidate is None or _digest(candidate) != entry["before_sha256"]:
                        raise CandidateSourceError(f"SUPPORT_FILE_CHANGED: {relative}")
        except Exception:
            self._manifest = {}
            self._prepared = False
            raise
        return SnapshotResult(
            self.source_root, self.baseline_root, self.manifest_path, len(self._manifest)
        )

    def _require_prepared(self) -> None:
        if not self._prepared:
            raise CandidateSourceError("PREPARE_REQUIRED")

    def _verify_baseline(self) -> None:
        for relative, entry in self._manifest.items():
            expected = entry["before_sha256"]
            path = self.baseline_root.joinpath(*PurePosixPath(relative).parts)
            if expected is None:
                if path.exists():
                    raise CandidateSourceError("BASELINE_TAMPERED")
                continue
            self._reject_symlinks(path, self.baseline_root)
            if not path.is_file() or _digest(path.read_bytes()) != expected:
                raise CandidateSourceError("BASELINE_TAMPERED")

    def read_context(
        self, paths: Iterable[str] | None = None, *, max_chars: int = 80_000,
        on_overflow: str = "error", focus: str | None = None,
    ) -> dict[str, str]:
        """Snapshot text for a model, bounded by ``max_chars``.

        ``on_overflow="error"`` is the historical contract: anything past the
        budget raises ``CONTEXT_LIMIT``. ``on_overflow="outline"`` instead keeps
        the mission alive by delivering oversized files as an explicitly marked
        partial view (see :func:`bounded_source_view`); ``focus`` is real mission
        evidence used to pick which regions are worth the budget.
        """
        self._require_prepared()
        if not 1 <= max_chars <= 500_000:
            raise CandidateSourceError("CONTEXT_LIMIT")
        if on_overflow not in ("error", "outline"):
            raise CandidateSourceError(f"CONTEXT_OVERFLOW_MODE: {on_overflow}")
        selected = list(paths) if paths is not None else list(self.allowed_paths)
        texts: list[tuple[str, str]] = []
        used = 0
        for raw in selected:
            relative = _normalise_relative(raw)
            if relative not in self._manifest:
                raise CandidateSourceError(f"CONTEXT_PATH not snapshotted: {relative}")
            path = self.source_root.joinpath(*PurePosixPath(relative).parts)
            if not path.is_file():
                continue
            self._reject_symlinks(path, self.source_root)
            text = path.read_text(encoding="utf-8")
            used += len(text)
            if used > max_chars and on_overflow == "error":
                raise CandidateSourceError("CONTEXT_LIMIT")
            texts.append((relative, text))
        delivered = dict(texts) if used <= max_chars else self._budgeted_context(texts, max_chars, focus)
        self._record_context_views(texts, delivered)
        return delivered

    # -- what the worker was actually shown ---------------------------------
    #
    # The draft step and the apply step are different dispatches, and may even
    # be different processes after a crash. "Was this file delivered whole?"
    # therefore cannot live in memory: it is written next to the snapshot and
    # read back when the edits arrive.

    def _ledger_path(self) -> Path:
        return self.sandbox / _CONTEXT_LEDGER_NAME

    def context_views(self) -> dict[str, dict]:
        """Per path: the digest the worker planned against, and whether the
        view it received was partial. Empty before the first ``read_context``."""
        path = self._ledger_path()
        if not path.is_file():
            return {}
        self._reject_symlinks(path, self.sandbox)
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise CandidateSourceError("CONTEXT_LEDGER_INVALID") from exc
        views = document.get("views") if isinstance(document, dict) else None
        if document.get("version") != 1 or not isinstance(views, dict):
            raise CandidateSourceError("CONTEXT_LEDGER_INVALID")
        for relative, entry in views.items():
            if (not isinstance(relative, str) or not isinstance(entry, dict)
                    or not re.fullmatch(r"[0-9a-f]{64}", str(entry.get("sha256")))
                    or type(entry.get("partial")) is not bool):
                raise CandidateSourceError("CONTEXT_LEDGER_INVALID")
        return views

    def _record_context_views(self, texts: list[tuple[str, str]], delivered: dict[str, str]) -> None:
        views = self.context_views()
        for relative, text in texts:
            view = delivered.get(relative)
            if view is None:
                continue
            views[relative] = {
                "sha256": _text_digest(text),
                "partial": is_partial_view(view),
                "real_chars": len(text),
                "delivered_chars": len(view),
            }
        if not views:
            return
        self.sandbox.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"version": 1, "views": views}, ensure_ascii=False,
                             indent=2, sort_keys=True) + "\n"
        target = self._ledger_path()
        descriptor, temporary_name = tempfile.mkstemp(prefix=".views-", dir=self.sandbox)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, target)
        finally:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass

    def _current_text(self, relative: str) -> str | None:
        path = self.source_root.joinpath(*PurePosixPath(relative).parts)
        if not path.is_file():
            return None
        self._reject_symlinks(path, self.source_root)
        return path.read_text(encoding="utf-8")

    def _reject_planning_drift(self, relative: str, view: dict | None) -> None:
        """The worker planned against a specific byte state. If the file moved
        after that, the plan is stale: ask for fresh context, never apply."""
        if not view:
            return
        current = self._current_text(relative)
        observed = _text_digest(current) if current is not None else None
        if observed != view["sha256"]:
            raise CandidateSourceError(
                f"SOURCE_DRIFT: {relative} changed after the worker read it "
                f"(planned {view['sha256'][:12]}, current {str(observed)[:12]}). "
                "Request fresh context and replan; this edit is not applied."
            )

    def _anchored_text(self, relative: str, operations: object) -> tuple[str, list[dict]]:
        """Apply exact, unique anchors to the current source text.

        Ambiguous or absent anchors raise instead of guessing an occurrence, and
        every character outside a matched span is carried over untouched.
        """
        current = self._current_text(relative)
        if current is None:
            raise CandidateSourceError(
                f"ANCHOR_FILE_MISSING: {relative} does not exist in the candidate; "
                "an anchored edit needs real text to anchor to"
            )
        if not isinstance(operations, list) or not 1 <= len(operations) <= _MAX_ANCHORED_EDITS:
            raise CandidateSourceError(f"ANCHORED_EDIT_LIMIT: {relative}")
        text = current
        applied: list[dict] = []
        for position, operation in enumerate(operations):
            label = f"{relative}#{position}"
            if not isinstance(operation, dict) or set(operation) != {"find", "replace"}:
                raise CandidateSourceError(
                    f"ANCHORED_EDIT_SCHEMA: {label} needs exactly the keys find and replace"
                )
            find, replace = operation["find"], operation["replace"]
            if not isinstance(find, str) or not isinstance(replace, str):
                raise CandidateSourceError(f"ANCHORED_EDIT_SCHEMA: {label}")
            if not find.strip():
                raise CandidateSourceError(
                    f"ANCHOR_EMPTY: {label} - an anchor must be real source text"
                )
            if len(find) > _MAX_ANCHOR_CHARS or len(replace) > _MAX_ANCHOR_CHARS:
                raise CandidateSourceError(f"ANCHOR_SIZE_LIMIT: {label}")
            if _PARTIAL_VIEW_MARKER in find or _PARTIAL_VIEW_MARKER in replace:
                raise CandidateSourceError(f"PARTIAL_VIEW_CONTENT_FORBIDDEN: {label}")
            occurrences = text.count(find)
            if occurrences == 0:
                raise CandidateSourceError(
                    f"ANCHOR_NOT_FOUND: {label} - the anchor is not in the current source. "
                    "Request fresh context and replan; nothing was applied."
                )
            if occurrences > 1:
                raise CandidateSourceError(
                    f"ANCHOR_AMBIGUOUS: {label} - {occurrences} occurrences. "
                    "Extend the anchor with surrounding lines until it is unique; "
                    "an occurrence is never guessed."
                )
            start = text.index(find)
            end = start + len(find)
            head, tail = text[:start], text[end:]
            text = head + replace + tail
            # Hard postcondition: only the matched span moved.
            if not (text.startswith(head) and text.endswith(tail)
                    and len(text) == len(head) + len(replace) + len(tail)):
                raise CandidateSourceError(f"ANCHORED_EDIT_UNSAFE: {label}")
            applied.append({
                "index": position,
                "start": start,
                "end": end,
                "find_chars": len(find),
                "replace_chars": len(replace),
                "find_sha256": _text_digest(find),
                "replace_sha256": _text_digest(replace),
                "preserved_prefix_chars": len(head),
                "preserved_suffix_chars": len(tail),
            })
        if relative.endswith(".py"):
            # A full rewrite is syntax-gated upstream by the patch schema; an
            # anchored result is assembled here, so it is gated here.
            try:
                compile(text, relative, "exec")
            except (SyntaxError, ValueError) as exc:
                raise CandidateSourceError(
                    f"ANCHORED_EDIT_SYNTAX: {relative}: {exc}"
                ) from exc
        return text, applied

    def _budgeted_context(
        self, texts: list[tuple[str, str]], max_chars: int, focus: str | None
    ) -> dict[str, str]:
        """Spend the budget smallest file first, so small files stay complete."""
        order = [relative for relative, _text in texts]
        result: dict[str, str] = {}
        remaining = max_chars
        pending = sorted(texts, key=lambda item: len(item[1]))
        for position, (relative, text) in enumerate(pending):
            share = max(_MIN_PARTIAL_BUDGET, remaining // (len(pending) - position))
            if len(text) <= share:
                result[relative] = text
            else:
                result[relative] = bounded_source_view(relative, text, share, focus)
            remaining -= len(result[relative])
        return {relative: result[relative] for relative in order if relative in result}

    def _candidate_bytes(self, relative: str) -> bytes | None:
        path = self.source_root.joinpath(*PurePosixPath(relative).parts)
        if not path.exists():
            return None
        self._reject_symlinks(path, self.source_root)
        if not path.is_file():
            raise CandidateSourceError(f"FILE_REQUIRED: {relative}")
        return path.read_bytes()

    def _changed_entries(self) -> list[tuple[str, bytes, bytes]]:
        changed: list[tuple[str, bytes, bytes]] = []
        for relative in self.allowed_paths:
            before_path = self.baseline_root.joinpath(*PurePosixPath(relative).parts)
            before = before_path.read_bytes() if before_path.is_file() else b""
            after = self._candidate_bytes(relative)
            after_bytes = after if after is not None else b""
            if not _same_source_text(before, after_bytes):
                changed.append((relative, before, after_bytes))
        return changed

    def _require_real_work(self, hypothetical: list[tuple[str, bytes, bytes]]) -> None:
        """Refuse a candidate that does not do the mission's actual work.

        The original rule was "at least one non-test file must change", written to
        catch the worker that edits a test to look busy while the reported defect
        lives in production code. That rule has one blind spot: a mission whose
        objective IS a test file (a flaky test, a wrong assertion). There, editing
        only that test is the correct fix, and the guard refused it - while the
        patch verifier simultaneously demanded the regression test be edited. The
        two rules together made such a mission unwinnable (LAB-14, 2026-09-10).

        The distinction is made with evidence the engine already owns and the
        worker cannot forge: ``objective_paths`` is the mission scope selected from
        the owner's own words, never from the draft. The rule becomes:

        * some non-test file changed -> accepted, exactly as before;
        * otherwise, accepted only if one of the changed files is a file the
          MISSION is about - i.e. a test file the owner's scope itself named.

        A production-only objective therefore behaves identically to the old rule:
        no test file can ever be an objective path, so a test-only candidate is
        still refused. What changes is only the case the owner actually asked for,
        where the named target is a test. Editing some OTHER test (typically just
        the mandatory regression test) never satisfies it, so the worker cannot
        use this to dodge the module it was sent to fix.
        """
        changed_production = [
            relative for relative, _before, _after in hypothetical if not _is_test_path(relative)
        ]
        if changed_production:
            return
        changed_objective = [
            relative for relative, _before, _after in hypothetical
            if relative in self.objective_paths
        ]
        if not self.objective_test_paths:
            # The mission is about production code (or declares no objective at
            # all): a candidate that touches no production file is the old
            # test-only dodge and is refused before the first write.
            raise CandidateSourceError("SOURCE_CHANGE_REQUIRED: test-only or no-op edit")
        if not changed_objective:
            raise CandidateSourceError(
                "SOURCE_CHANGE_REQUIRED: test-only or no-op edit; this mission is about "
                + ", ".join(self.objective_paths)
                + ", and none of those files changed"
            )

    def apply_edits(self, edits: list[dict]) -> ChangeResult:
        """Apply a patch proposal to the candidate copy.

        Two shapes are accepted per file, and which one is legal is decided by
        what the worker was actually shown (see :meth:`context_views`):

        * ``{"path": ..., "content": "<the complete file>"}`` - only when the
          file was delivered whole.
        * ``{"path": ..., "anchored_edits": [{"find": ..., "replace": ...}]}`` -
          always legal, and the ONLY legal shape after a partial view.
        """
        self._require_prepared()
        self._verify_baseline()
        if not isinstance(edits, list) or not 1 <= len(edits) <= _MAX_EDIT_FILES:
            raise CandidateSourceError("EDIT_LIMIT")

        views = self.context_views()
        pending: dict[str, bytes] = {}
        applied_records: list[dict] = []
        for edit in edits:
            if not isinstance(edit, dict) or not isinstance(edit.get("path"), str):
                raise CandidateSourceError("EDIT_SCHEMA")
            has_content = "content" in edit
            has_anchors = "anchored_edits" in edit
            if has_content == has_anchors:
                raise CandidateSourceError(
                    "EDIT_SCHEMA: exactly one of content or anchored_edits is required"
                )
            content = edit.get("content")
            if has_content and not isinstance(content, str):
                raise CandidateSourceError("EDIT_SCHEMA")
            relative = _normalise_relative(edit["path"])
            if has_content and _PARTIAL_VIEW_MARKER in content:
                # A worker handed a partial view tried to write the excerpt back
                # as the whole file. The warning in the view is advice; this is
                # the enforcement that stops the truncation from landing.
                raise CandidateSourceError(f"PARTIAL_VIEW_CONTENT_FORBIDDEN: {relative}")
            if relative not in self.allowed_paths:
                raise CandidateSourceError(f"PATH not editable: {relative}")
            if relative in pending:
                raise CandidateSourceError(f"DUPLICATE_EDIT: {relative}")
            view = views.get(relative)
            if has_content:
                if view is not None and view["partial"]:
                    # Same lock as the marker check above, reached by the other
                    # road: the excerpt was paraphrased instead of pasted, so
                    # the marker is gone but the unseen ranges are still unseen.
                    raise CandidateSourceError(
                        f"PARTIAL_VIEW_CONTENT_FORBIDDEN: {relative} was delivered as a partial "
                        f"view ({view['delivered_chars']} of {view['real_chars']} characters). "
                        "A full-file rewrite cannot be honest about ranges you never read: "
                        "send anchored_edits instead."
                    )
                text = content
                record = {"path": relative, "mode": "full_rewrite", "edits": []}
            else:
                self._reject_planning_drift(relative, view)
                text, operations = self._anchored_text(relative, edit["anchored_edits"])
                record = {"path": relative, "mode": "anchored", "edits": operations}
            encoded = text.encode("utf-8")
            if len(encoded) > _MAX_FILE_BYTES:
                raise CandidateSourceError(f"EDIT_SIZE_LIMIT: {relative}")
            target = self.source_root.joinpath(*PurePosixPath(relative).parts)
            self._reject_symlinks(target, self.source_root, allow_missing_leaf=True)
            pending[relative] = encoded
            applied_records.append(record)

        # Evaluate the complete candidate before performing the first write.
        hypothetical: list[tuple[str, bytes, bytes]] = []
        for relative in self.allowed_paths:
            baseline_path = self.baseline_root.joinpath(*PurePosixPath(relative).parts)
            before = baseline_path.read_bytes() if baseline_path.is_file() else b""
            current = self._candidate_bytes(relative)
            after = pending.get(relative, current if current is not None else b"")
            if not _same_source_text(before, after):
                hypothetical.append((relative, before, after))
        self._require_real_work(hypothetical)

        for relative, data in pending.items():
            target = self.source_root.joinpath(*PurePosixPath(relative).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            self._reject_symlinks(target.parent, self.source_root)
            descriptor, temporary_name = tempfile.mkstemp(prefix=".candidate-", dir=target.parent)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary_name, target)
            finally:
                try:
                    os.unlink(temporary_name)
                except FileNotFoundError:
                    pass

        changed = self._changed_entries()
        diff_parts: list[str] = []
        hashes: dict[str, dict[str, str | None]] = {}
        for relative, before, after in changed:
            before_text = before.decode("utf-8")
            after_text = after.decode("utf-8")
            diff_parts.extend(
                difflib.unified_diff(
                    before_text.splitlines(keepends=True),
                    after_text.splitlines(keepends=True),
                    fromfile=f"a/{relative}",
                    tofile=f"b/{relative}",
                )
            )
            hashes[relative] = {
                "before_sha256": _digest(before) if self._manifest[relative]["exists"] else None,
                "after_sha256": _digest(after),
            }
        unified = "".join(diff_parts)
        lines_added = sum(
            1 for line in unified.splitlines() if line.startswith("+") and not line.startswith("+++")
        )
        lines_deleted = sum(
            1 for line in unified.splitlines() if line.startswith("-") and not line.startswith("---")
        )
        source_changed = sum(1 for relative, _before, _after in changed if not _is_test_path(relative))
        objective_changed = sum(
            1 for relative, _before, _after in changed if relative in self.objective_paths
        )
        evidence = {
            "files_changed": len(changed),
            "source_files_changed": source_changed,
            "objective_files_changed": objective_changed,
            "lines_added": lines_added,
            "lines_deleted": lines_deleted,
            "hashes": hashes,
            "diff": unified,
            "edits_applied": applied_records,
        }
        evidence_dir = self.sandbox / "evidence"
        evidence_dir.mkdir(exist_ok=True)
        evidence_path = evidence_dir / "changes.json"
        evidence_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return ChangeResult(
            unified,
            len(changed),
            source_changed,
            lines_added,
            lines_deleted,
            hashes,
            evidence_path,
            applied_records,
            objective_changed,
        )

    def _validated_test_nodeids(self, test_paths: Iterable[str]) -> list[str]:
        nodeids: list[str] = []
        for raw in test_paths:
            if not isinstance(raw, str):
                raise CandidateSourceError("TEST_NOT_AUTHORIZED")
            path_part, separator, suffix = raw.partition("::")
            relative = _normalise_relative(path_part)
            if (
                relative not in self.allowed_paths
                or not _is_test_path(relative)
                or not relative.endswith(".py")
            ):
                raise CandidateSourceError(f"TEST_NOT_AUTHORIZED: {relative}")
            if separator and (not suffix or not _NODE_SUFFIX.fullmatch(suffix)):
                raise CandidateSourceError("TEST_NODEID_FORBIDDEN")
            if not self.source_root.joinpath(*PurePosixPath(relative).parts).is_file():
                raise CandidateSourceError(f"TEST_MISSING: {relative}")
            nodeids.append(relative + ("::" + suffix if separator else ""))
        if not nodeids or len(nodeids) > 8:
            raise CandidateSourceError("TEST_LIMIT")
        return nodeids

    _RUNNER = r"""
import json, os, sys
from pathlib import Path

run_root = Path(sys.argv[1]).resolve()
workspace = Path(sys.argv[2]).resolve()
environment_root = Path(sys.argv[3]).resolve()
runtime_root = Path(sys.argv[4]).resolve()
receipt_path = Path(sys.argv[5]).resolve()
nodeids = sys.argv[6:]

def inside(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False

clean = []
for item in sys.path:
    try:
        resolved = Path(item or os.curdir).resolve()
    except Exception:
        clean.append(item)
        continue
    if inside(resolved, workspace) and not inside(resolved, environment_root):
        continue
    clean.append(item)
sys.path[:] = [str(run_root), *clean]
sys.dont_write_bytecode = True
os.chdir(run_root)
import pytest

write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
allowed_write_roots = (run_root, runtime_root)

def resolved_path(value):
    if not isinstance(value, (str, bytes, os.PathLike)):
        return None
    try:
        return Path(value).resolve()
    except Exception:
        return None

def require_sandbox_path(value, message):
    if isinstance(value, (str, bytes, os.PathLike)):
        device = os.fsdecode(value).lower().rstrip("\\/")
        if device in {"nul", r"\\.\nul", os.devnull.lower()}:
            return
    path = resolved_path(value)
    if path is not None and not any(inside(path, root) for root in allowed_write_roots):
        raise PermissionError(f"{message}: {path}")

# SANDBOX NETWORK POLICY: ASYNC LOCAL: ALLOWED; EXTERNAL NETWORK: DENIED.
# asyncio on Windows cannot build an event loop without socket.socketpair(),
# which CPython emulates (socket._fallback_socketpair) as an ephemeral loopback
# bind + connect to itself.  That pair never leaves the process, so it is the
# only socket primitive allowed here.  Everything else - outbound TCP, UDP,
# public/0.0.0.0 binds, DNS resolution - stays denied.
import socket as _socket
import threading as _threading

_SELF_PIPE_CODES = frozenset(
    function.__code__
    for function in (
        getattr(_socket, "_fallback_socketpair", None),
        getattr(_socket, "socketpair", None),
    )
    if getattr(function, "__code__", None) is not None
)
_SELF_PIPE_HOSTS = frozenset({"127.0.0.1", "::1"})
_SELF_PIPE_FAMILIES = frozenset({int(_socket.AF_INET), int(_socket.AF_INET6)})
_SELF_PIPE_TYPE = int(_socket.SOCK_STREAM)
_SELF_PIPE_STATE = _threading.local()

def calling_code():
    try:
        return sys._getframe(2).f_code
    except (ValueError, AttributeError):
        return None

# The kernel's own address for a socket, unspoofable by a subclass. Called
# through the unbound C method on purpose: a candidate could hand socketpair a
# socket subclass that lies in getsockname(), and that lie is what would choose
# the connect target.
def true_socket_name(sock):
    try:
        return _socket.socket.getsockname(sock)
    except (OSError, TypeError, AttributeError, ValueError):
        return None

def socket_shape(sock):
    try:
        return int(getattr(sock, "family")), int(getattr(sock, "type"))
    except (AttributeError, TypeError, ValueError):
        return None, None

# True only for the loopback socketpair CPython uses as the event-loop
# self-pipe. Four independent locks, all of which must hold:
#   1. Code-object identity of the caller. Not its name and not its file: a
#      look-alike _fallback_socketpair written by the candidate is a different
#      code object and gets nothing.
#   2. Loopback host and stream family, so the shape is checked even if the
#      stdlib is ever rewritten.
#   3. bind only with port 0, so no fixed or public listener can be opened.
#   4. connect only to the address the same call just bound, read back from the
#      kernel. Without this, a caller that owns the function's globals could
#      still aim the connect at some other local service's port.
def is_event_loop_self_pipe(event, args, caller):
    if event not in {"socket.bind", "socket.connect"} or len(args) < 2:
        return False
    if caller is None or caller not in _SELF_PIPE_CODES:
        return False
    address = args[1]
    if type(address) is not tuple or len(address) != 2:
        return False
    host, port = address
    if host not in _SELF_PIPE_HOSTS or type(port) is not int:
        return False
    family, kind = socket_shape(args[0])
    if family not in _SELF_PIPE_FAMILIES or kind != _SELF_PIPE_TYPE:
        return False
    if event == "socket.bind":
        if port != 0:
            return False
        # Remember the listener; the matching connect is validated against it.
        _SELF_PIPE_STATE.listener = args[0]
        return True
    listener = getattr(_SELF_PIPE_STATE, "listener", None)
    _SELF_PIPE_STATE.listener = None
    if listener is None or listener is args[0]:
        return False
    bound = true_socket_name(listener)
    if type(bound) is not tuple or len(bound) < 2:
        return False
    return (bound[0], bound[1]) == (host, port) and 0 < port <= 65535

def audit(event, args):
    if event == "open":
        path = resolved_path(args[0]) if args else None
        mode = args[1] if len(args) > 1 else None
        flags = args[2] if len(args) > 2 else 0
        writing = (isinstance(mode, str) and any(letter in mode for letter in "wax+")) or (
            isinstance(flags, int) and bool(flags & write_flags)
        )
        if writing:
            require_sandbox_path(args[0], "SANDBOX_WRITE_FORBIDDEN")
        elif path is not None and inside(path, workspace) and not inside(path, run_root) and not inside(path, environment_root):
            raise PermissionError(f"PRODUCTION_READ_FORBIDDEN: {path}")
        return
    mutation_positions = {
        "os.remove": (0,), "os.rmdir": (0,), "os.mkdir": (0,), "os.rename": (0, 1),
        "os.replace": (0, 1), "os.chmod": (0,), "os.truncate": (0,), "os.utime": (0,),
        "os.link": (0, 1), "os.symlink": (0, 1),
    }
    if event in mutation_positions:
        for position in mutation_positions[event]:
            if position < len(args):
                require_sandbox_path(args[position], "SANDBOX_MUTATION_FORBIDDEN")
        return
    if event in {"os.chdir", "os.fchdir"}:
        require_sandbox_path(args[0], "SANDBOX_CHDIR_FORBIDDEN")
        return
    if event in {"os.listdir", "os.scandir"} and args:
        path = resolved_path(args[0])
        if path is not None and inside(path, workspace) and not inside(path, run_root) and not inside(path, environment_root):
            raise PermissionError(f"PRODUCTION_ENUMERATION_FORBIDDEN: {path}")
        return
    if event == "subprocess.Popen" or event == "os.system" or event == "os.startfile" or event.startswith("os.spawn") or event.startswith("os.exec"):
        raise PermissionError("PROCESS_EXECUTION_FORBIDDEN")
    if event.startswith("socket.") and event not in {"socket.__new__"}:
        if is_event_loop_self_pipe(event, args, calling_code()):
            return  # ASYNC LOCAL: ALLOWED
        raise PermissionError(f"NETWORK_FORBIDDEN: EXTERNAL NETWORK: DENIED ({event})")
    if event.startswith("winreg."):
        raise PermissionError("REGISTRY_FORBIDDEN")

sys.addaudithook(audit)
print("[SANDBOX_POLICY] ASYNC LOCAL: ALLOWED; EXTERNAL NETWORK: DENIED", file=sys.stderr)

class ReceiptPlugin:
    def __init__(self):
        self.counts = {"collected": 0, "passed": 0, "failed": 0, "errors": 0,
                       "skipped": 0, "xfailed": 0, "xpassed": 0}
    def pytest_collection_finish(self, session):
        self.counts["collected"] = len(session.items)
    def pytest_runtest_logreport(self, report):
        was_xfail = hasattr(report, "wasxfail")
        if report.when == "call":
            if was_xfail and report.skipped:
                self.counts["xfailed"] += 1
            elif was_xfail and report.passed:
                self.counts["xpassed"] += 1
            elif report.passed:
                self.counts["passed"] += 1
            elif report.failed:
                self.counts["failed"] += 1
            elif report.skipped:
                self.counts["skipped"] += 1
        elif report.failed:
            self.counts["errors"] += 1
        elif report.skipped and not was_xfail:
            self.counts["skipped"] += 1

plugin = ReceiptPlugin()
status = int(pytest.main(["-q", "--tb=short", "--disable-warnings", "-c", str(run_root / ".candidate-pytest.ini"), "--rootdir", str(run_root), *nodeids], plugins=[plugin]))
receipt_path.write_text(json.dumps({"pytest_exit_code": status, "counts": plugin.counts}), encoding="utf-8")
leaks = []
for name, module in tuple(sys.modules.items()):
    filename = getattr(module, "__file__", None)
    if not filename:
        continue
    try:
        resolved = Path(filename).resolve()
    except Exception:
        continue
    if inside(resolved, workspace) and not inside(resolved, run_root) and not inside(resolved, environment_root):
        leaks.append(f"{name}={resolved}")
if leaks:
    print("PRODUCTION_IMPORT_FORBIDDEN: " + "; ".join(sorted(leaks)[:20]), file=sys.stderr)
    status = 86
raise SystemExit(status)
"""

    def run_pytest(
        self,
        test_paths: Iterable[str],
        *,
        timeout_seconds: float = 30,
        baseline: bool = False,
    ) -> TestResult:
        self._require_prepared()
        self._verify_baseline()
        if not 1 <= timeout_seconds <= 120:
            raise CandidateSourceError("TIMEOUT_LIMIT")
        nodeids = self._validated_test_nodeids(test_paths)
        executable = self.python_executable.resolve(strict=False)
        if not executable.is_file():
            raise CandidateSourceError(f"VENV_PYTHON_MISSING: {executable}")

        runs = self.sandbox / "runs"
        runs.mkdir(exist_ok=True)
        run_parent = Path(tempfile.mkdtemp(prefix="baseline-" if baseline else "candidate-", dir=runs))
        run_root = run_parent / "source"
        shutil.copytree(self.baseline_root if baseline else self.source_root, run_root)
        if baseline:
            # Regression tests are always the candidate versions.  Only source
            # modules come from the immutable before snapshot.
            for nodeid in nodeids:
                relative = nodeid.partition("::")[0]
                source = self.source_root.joinpath(*PurePosixPath(relative).parts)
                target = run_root.joinpath(*PurePosixPath(relative).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        (run_root / ".candidate-pytest.ini").write_text(
            "[pytest]\naddopts =\n", encoding="utf-8"
        )

        environment_root = executable.parent.parent
        command = [
            str(executable),
            # Isolated mode: the host's PYTHON* variables and user site cannot
            # reach the candidate run. Dependencies come from the interpreter's
            # own environment, and the runner disables bytecode writing itself.
            "-I",
            "-c",
            self._RUNNER,
            str(run_root),
            str(self.workspace),
            str(environment_root),
            str(self.sandbox),
            str(run_parent / "pytest-receipt.json"),
            *nodeids,
        ]
        runtime_home = self.sandbox / "runtime-home"
        runtime_temp = self.sandbox / "runtime-tmp"
        runtime_home.mkdir(exist_ok=True)
        runtime_temp.mkdir(exist_ok=True)
        safe_environment_names = (
            "SYSTEMROOT",
            "WINDIR",
            "PATH",
            "PATHEXT",
            "COMSPEC",
            "NUMBER_OF_PROCESSORS",
            "PROCESSOR_ARCHITECTURE",
        )
        environment = {
            key: os.environ[key] for key in safe_environment_names if key in os.environ
        }
        dependency_paths = [path for path in (site.getsitepackages() + [site.getusersitepackages()])
                            if Path(path).is_dir()]
        environment.update(
            {
                "ZARA_TEST_MODE": "1",
                "ZARA_TEST_TRIGGER": "lab-candidate",
                "ZARA3_HOME": str(runtime_home / "zara-data"),
                "PYTHONDONTWRITEBYTECODE": "1",
                "HOME": str(runtime_home),
                "USERPROFILE": str(runtime_home),
                "LOCALAPPDATA": str(runtime_home / "local"),
                "APPDATA": str(runtime_home / "roaming"),
                "TEMP": str(runtime_temp),
                "TMP": str(runtime_temp),
                "PYTHONPATH": os.pathsep.join(dependency_paths),
            }
        )
        production_before = {
            relative: entry["before_sha256"]
            for relative, entry in self._manifest.items()
            if entry["exists"] and relative not in self.runtime_drift_paths
        }
        try:
            completed = subprocess.run(
                command,
                cwd=run_root,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                shell=False,
                check=False,
            )
            exit_code = completed.returncode
            stdout = completed.stdout[-_MAX_TEST_OUTPUT:]
            stderr = completed.stderr[-_MAX_TEST_OUTPUT:]
            timed_out = False
        except subprocess.TimeoutExpired as exc:
            exit_code = 124
            stdout = (exc.stdout or "")[-_MAX_TEST_OUTPUT:]
            stderr = (exc.stderr or "")[-_MAX_TEST_OUTPUT:]
            timed_out = True

        receipt_path = run_parent / "pytest-receipt.json"
        try:
            machine_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            counts = machine_receipt["counts"]
            expected_keys = {"collected", "passed", "failed", "errors", "skipped", "xfailed", "xpassed"}
            if (machine_receipt.get("pytest_exit_code") != exit_code or set(counts) != expected_keys
                    or any(type(value) is not int or value < 0 for value in counts.values())):
                raise ValueError
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
            counts = {"collected": 0, "passed": 0, "failed": 0, "errors": 1,
                      "skipped": 0, "xfailed": 0, "xpassed": 0}

        test_hashes = {}
        for nodeid in nodeids:
            relative = nodeid.partition("::")[0]
            test_path = self.source_root.joinpath(*PurePosixPath(relative).parts)
            test_hashes[relative] = _digest(test_path.read_bytes())

        for relative, expected in production_before.items():
            original = self._workspace_path(relative)
            if (not original.is_file() or _digest(_normalize_newlines(
                    original.read_bytes(), relative
            )) != expected):
                raise CandidateSourceError(f"PRODUCTION_WRITE_DETECTED: {relative}")
        return TestResult(command, exit_code, stdout, stderr, timed_out, baseline, run_root,
                          counts, test_hashes)

    def run_pytest_baseline(
        self, test_paths: Iterable[str], *, timeout_seconds: float = 30
    ) -> TestResult:
        return self.run_pytest(test_paths, timeout_seconds=timeout_seconds, baseline=True)


__all__ = [
    "SANDBOX_NETWORK_POLICY",
    "CandidateSource",
    "CandidateSourceError",
    "ChangeResult",
    "SnapshotResult",
    "SourceRegion",
    "TestResult",
    "bounded_source_view",
    "is_partial_view",
    "source_regions",
    "structure_index",
]

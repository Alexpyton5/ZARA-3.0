"""Safe autonomous research and skill-candidate pipeline.

The module deliberately separates discovery from execution. It can fetch bounded
public documents, produce a cited research record, create a metadata-only skill
candidate, record test receipts, activate only an approved candidate, and roll
back an activation atomically. It never imports or executes a discovered
entrypoint and never treats a web page as an instruction.
"""
from __future__ import annotations

import hashlib
import ipaddress
import json
import os
import re
import socket
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from core.paths import user_data_dir
from .skill_registry import SkillRegistry, validate_manifest

_MAX_FETCH_BYTES = 256 * 1024
_MAX_TEXT_CHARS = 12_000
_SECRET_RE = re.compile(r"(?:api[_-]?key|password|passwd|secret|token|bearer)\s*[:=]", re.I)


class ResearchPipelineError(ValueError):
    pass


class ActivationDenied(ResearchPipelineError):
    pass


class RollbackUnavailable(ResearchPipelineError):
    pass


@dataclass(frozen=True)
class ResearchFinding:
    source: str
    title: str
    excerpt: str
    sha256: str
    observed_at: float


@dataclass(frozen=True)
class SkillCandidate:
    skill_id: str
    version: str
    status: str
    description: str
    permissions: tuple[str, ...]
    source_refs: tuple[str, ...]
    findings_sha256: tuple[str, ...]
    candidate_path: str
    created_at: float


def _safe_text(value: Any, field: str, limit: int = _MAX_TEXT_CHARS) -> str:
    text = str(value or "").strip()
    if not text or len(text) > limit or _SECRET_RE.search(text):
        raise ResearchPipelineError(f"{field} inválido ou potencialmente sensível")
    return text


def _safe_identifier(value: Any, field: str, limit: int = 128) -> str:
    text = str(value or "").strip()
    if not text or len(text) > limit or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", text):
        raise ResearchPipelineError(f"{field} inválido")
    return text


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _assert_public_url(url: str) -> None:
    """Reject local/private targets before a research request leaves the app."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ResearchPipelineError("fonte deve ser uma URL HTTP(S) pública")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ResearchPipelineError("fonte local não permitida")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, parsed.port, type=socket.SOCK_STREAM)}
    except OSError as exc:
        raise ResearchPipelineError("host da fonte não pôde ser verificado") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ResearchPipelineError("fonte em rede privada ou reservada não permitida")


class AutonomousResearchSkillPipeline:
    """Persistent, fail-closed coordinator for research-derived skills."""

    def __init__(
        self,
        root: Path | str | None = None,
        *,
        fetcher: Callable[[str], bytes] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.root = Path(root) if root is not None else user_data_dir() / "lab" / "research_skills"
        self.root.mkdir(parents=True, exist_ok=True)
        self.fetcher = fetcher or self._fetch
        self.clock = clock
        self.registry = SkillRegistry()
        self._load_registry()

    @staticmethod
    def _fetch(url: str) -> bytes:
        parsed = urllib.parse.urlparse(url)
        _assert_public_url(url)
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "ZARA-ResearchSkillPipeline/1.0", "Accept": "text/plain,text/html"},
        )
        with urllib.request.urlopen(request, timeout=12) as response:
            final = urllib.parse.urlparse(response.geturl())
            _assert_public_url(response.geturl())
            data = response.read(_MAX_FETCH_BYTES + 1)
        if len(data) > _MAX_FETCH_BYTES:
            raise ResearchPipelineError("fonte excede o limite de leitura")
        return data

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    def _load_registry(self) -> None:
        for path in sorted(self.root.glob("candidates/*/manifest.json")):
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
                self.registry.register_skill(manifest)
            except Exception:
                # A corrupt candidate is visible to diagnostics but cannot enter
                # the live registry or stop the rest of the Lab.
                continue

    def _journal(self, event: str, payload: dict[str, Any]) -> None:
        record = {"event": event, "recorded_at": self.clock(), **payload}
        name = f"{int(record['recorded_at'] * 1000)}-{event}.json"
        self._write_json(self.root / "journal" / name, record)

    def research(self, topic: str, sources: Iterable[str]) -> dict[str, Any]:
        topic = _safe_text(topic, "topic", 500)
        findings: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        for source in list(sources)[:8]:
            try:
                url = _safe_text(source, "source", 2000)
                raw = self.fetcher(url)
                if not isinstance(raw, bytes):
                    raise ResearchPipelineError("fetcher deve retornar bytes")
                text = raw.decode("utf-8", errors="replace")
                if _SECRET_RE.search(text):
                    raise ResearchPipelineError("conteúdo com padrão sensível rejeitado")
                excerpt = " ".join(text.split())[:_MAX_TEXT_CHARS]
                if not excerpt:
                    raise ResearchPipelineError("fonte vazia")
                findings.append(asdict(ResearchFinding(
                    source=url,
                    title=urllib.parse.urlparse(url).netloc,
                    excerpt=excerpt,
                    sha256=_sha256(raw),
                    observed_at=self.clock(),
                )))
            except Exception as exc:
                failures.append({"source": str(source)[:200], "error": type(exc).__name__})
        record = {"topic": topic, "findings": findings, "failures": failures, "created_at": self.clock()}
        record["research_id"] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:24]
        self._write_json(self.root / "research" / f"{record['research_id']}.json", record)
        return record

    def create_candidate(
        self,
        *,
        skill_id: str,
        version: str,
        description: str,
        permissions: Iterable[str],
        research: dict[str, Any],
    ) -> dict[str, Any]:
        if not research.get("findings"):
            raise ResearchPipelineError("não há evidência de pesquisa suficiente")
        skill_id = _safe_text(skill_id, "skill_id", 128)
        description = _safe_text(description, "description", 1000)
        refs = tuple(_safe_text(item.get("source"), "source", 2000) for item in research["findings"])
        hashes = tuple(_safe_text(item.get("sha256"), "sha256", 100) for item in research["findings"])
        manifest = validate_manifest({
            "skill_id": skill_id,
            "version": version,
            "status": "DRAFT",
            "permissions": list(permissions),
            "checksum": "sha256:" + "0" * 64,
            "name": skill_id,
            "description": description,
            "entrypoint": "NOT_EXECUTABLE_UNTIL_EXPLICIT_IMPLEMENTATION",
            "author": "ZARA Research Pipeline",
            "metadata": {"source_refs": list(refs), "findings_sha256": list(hashes), "research_id": research.get("research_id")},
        })
        candidate = SkillCandidate(skill_id, manifest["version"], "DRAFT", description, tuple(manifest["permissions"]), refs, hashes, "", self.clock())
        candidate_dir = self.root / "candidates" / skill_id / version
        candidate_path = candidate_dir / "manifest.json"
        manifest["created_at"] = str(candidate.created_at)
        self.registry.register_skill(manifest)
        self._write_json(candidate_path, manifest)
        self._write_json(candidate_dir / "research.json", research)
        return manifest

    def record_test(self, skill_id: str, version: str, test_id: str, *, passed: bool, summary: str) -> dict[str, Any]:
        if not isinstance(passed, bool):
            raise ResearchPipelineError("passed deve ser booleano")
        skill_id = _safe_identifier(skill_id, "skill_id")
        version = _safe_identifier(version, "version", 64)
        receipt = {"skill_id": skill_id, "version": version, "test_id": _safe_text(test_id, "test_id", 120), "passed": passed, "summary": _safe_text(summary, "summary", 1000), "recorded_at": self.clock()}
        test_path = self.root / "candidates" / skill_id / version / ("test-" + receipt["test_id"] + ".json")
        self._write_json(test_path, receipt)
        return receipt

    def activate(self, skill_id: str, version: str, *, owner_approved: bool) -> dict[str, Any]:
        if owner_approved is not True:
            raise ActivationDenied("ativação exige aprovação explícita do owner")
        skill_id = _safe_identifier(skill_id, "skill_id")
        version = _safe_identifier(version, "version", 64)
        manifest_path = self.root / "candidates" / skill_id / version / "manifest.json"
        if not manifest_path.is_file():
            raise ActivationDenied("candidato não encontrado")
        tests = list(manifest_path.parent.glob("test-*.json"))
        receipts = [json.loads(path.read_text(encoding="utf-8")) for path in tests]
        if not receipts or not any(item.get("passed") is True for item in receipts):
            raise ActivationDenied("não há teste aprovado para este candidato")
        pointer = self.root / "active" / f"{skill_id}.json"
        previous = json.loads(pointer.read_text(encoding="utf-8")) if pointer.is_file() else None
        if previous is not None:
            self._write_json(self.root / "rollback" / skill_id / f"{previous['version']}.json", previous)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("skill_id") != skill_id or manifest.get("version") != version:
            raise ActivationDenied("manifesto não corresponde ao candidato solicitado")
        manifest["status"] = "ACTIVE"
        self._write_json(pointer, manifest)
        self._write_json(manifest_path, manifest)
        self.registry.update_skill(manifest)
        self._journal("activate", {"skill_id": skill_id, "version": version, "previous": previous})
        return {"success": True, "skill_id": skill_id, "version": version, "previous": previous, "state": "ACTIVE"}

    def rollback(self, skill_id: str, *, to_version: str | None = None) -> dict[str, Any]:
        skill_id = _safe_identifier(skill_id, "skill_id")
        if to_version is not None:
            to_version = _safe_identifier(to_version, "to_version", 64)
        pointer = self.root / "active" / f"{skill_id}.json"
        if not pointer.is_file():
            raise RollbackUnavailable("não existe versão ativa para rollback")
        current = json.loads(pointer.read_text(encoding="utf-8"))
        candidates = sorted((self.root / "rollback" / skill_id).glob("*.json"), reverse=True)
        if to_version:
            candidates = [path for path in candidates if path.stem == to_version]
        if not candidates:
            raise RollbackUnavailable("nenhuma versão anterior conhecida")
        target = json.loads(candidates[0].read_text(encoding="utf-8"))
        if target.get("skill_id") != skill_id:
            raise RollbackUnavailable("registro de rollback não corresponde à Skill")
        target["status"] = "ACTIVE"
        self._write_json(pointer, target)
        self.registry.update_skill(target)
        self._journal("rollback", {"skill_id": skill_id, "from_version": current.get("version"), "to_version": target.get("version")})
        return {"success": True, "skill_id": skill_id, "from_version": current.get("version"), "to_version": target.get("version"), "state": "ROLLED_BACK"}

    def snapshot(self) -> dict[str, Any]:
        active = []
        candidates = []
        for path in sorted((self.root / "active").glob("*.json")):
            try:
                active.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                continue
        for path in sorted(self.root.glob("candidates/*/*/manifest.json")):
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
                tests = [json.loads(item.read_text(encoding="utf-8")) for item in path.parent.glob("test-*.json")]
                candidates.append({"skill_id": manifest.get("skill_id"), "version": manifest.get("version"), "status": manifest.get("status", "DRAFT"), "description": manifest.get("description", ""), "tests": tests, "path": str(path)})
            except (OSError, ValueError):
                continue
        return {"root": str(self.root), "active": active, "candidates": candidates, "candidate_count": len(candidates)}


__all__ = ["AutonomousResearchSkillPipeline", "ResearchPipelineError", "ActivationDenied", "RollbackUnavailable"]

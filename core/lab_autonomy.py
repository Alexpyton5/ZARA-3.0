"""ZARA Lab autonomous mode — the council works on its own.

When enabled, a background loop runs mission cycles without Alex giving
orders: the reader scans the ZARA codebase, the CEO prioritizes findings,
the council debates them out loud, the engineer drafts patches and the
reviewer reviews. Every step is logged to the mission room feed and shows
up live in the Lab panel.

Hard guarantees:
- R$0: only the already-configured local engines are used (orchestrator /
  local worker CLIs). No new paid services, no new accounts.
- Approval gate: autonomous mode debates and DRAFTS. Nothing is promoted
  to production without Alex's explicit approval.
- Worker execution stays locked: patches are DRAFT records only; no
  production writes happen in autonomous mode.
- Idempotent: starting twice resumes the open cycle; cycles never
  duplicate (M020 rule).
- Stoppable and non-blocking: stop() halts between phases, and the loop
  never occupies the backend dispatch loop.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from core.lab_mission import MISSION_ID
from core.paths import data_dir

CONFIG_FILENAME = "lab-autonomy.json"
DEFAULT_COOLDOWN_MINUTES = 60
MAX_FINDINGS = 5
MAX_DEBATE_TOPICS = 3
WORKER_TIMEOUT_S = 180
ORCHESTRATOR_TIMEOUT_S = 120
SCAN_TIMEOUT_S = 60


class LabAutonomy:
    """Background autonomous council loop owned by a LabCoordinator."""

    def __init__(self, coordinator: Any) -> None:
        self.coordinator = coordinator
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._phase = "idle"
        self._cycle_id: str | None = None
        self._started_at: float | None = None
        self._last_summary = ""

    # ------------------------------------------------------------------ #
    # Config
    # ------------------------------------------------------------------ #
    @property
    def _config_path(self) -> Path:
        return data_dir() / CONFIG_FILENAME

    def _read_config(self) -> dict[str, Any]:
        try:
            raw = json.loads(self._config_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def _write_config(self, config: dict[str, Any]) -> None:
        try:
            self._config_path.write_text(
                json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError:
            pass

    def is_enabled(self) -> bool:
        # Autonomous mode defaults ON: Alex explicitly asked the council to
        # work on its own when the app opens. Toggle stays in the UI.
        return bool(self._read_config().get("enabled", True))

    def set_enabled(self, enabled: bool) -> None:
        config = self._read_config()
        config["enabled"] = bool(enabled)
        self._write_config(config)

    def cooldown_minutes(self) -> int:
        try:
            return max(5, int(self._read_config().get("cooldown_minutes", DEFAULT_COOLDOWN_MINUTES)))
        except (TypeError, ValueError):
            return DEFAULT_COOLDOWN_MINUTES

    # ------------------------------------------------------------------ #
    # Control
    # ------------------------------------------------------------------ #
    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.is_enabled(),
            "running": self._task is not None and not self._task.done(),
            "phase": self._phase,
            "cycle_id": self._cycle_id,
            "started_at": self._started_at,
            "last_summary": self._last_summary,
            "cooldown_minutes": self.cooldown_minutes(),
        }

    async def start(self, objective: str = "Ciclo autônomo do conselho") -> dict[str, Any]:
        """Idempotent start. A second call resumes instead of duplicating."""
        self.set_enabled(True)
        self._stop.clear()
        if self._task is not None and not self._task.done():
            return self.status()
        self._task = asyncio.create_task(self._loop(objective), name="zara-lab-autonomy")
        return self.status()

    async def stop(self) -> dict[str, Any]:
        self.set_enabled(False)
        self._stop.set()
        task, self._task = self._task, None
        if task is not None and not task.done():
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=5)
            except (TimeoutError, asyncio.CancelledError):
                pass
        self._phase = "idle"
        return self.status()

    async def ensure_autostart(self) -> None:
        """Called once at backend boot. Never blocks startup."""
        try:
            if self.is_enabled() and (self._task is None or self._task.done()):
                self._stop.clear()
                self._task = asyncio.create_task(
                    self._loop("Ciclo autônomo do conselho"), name="zara-lab-autonomy"
                )
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Main loop
    # ------------------------------------------------------------------ #
    async def _loop(self, objective: str) -> None:
        try:
            while not self._stop.is_set():
                await self._run_cycle(objective)
                if self._stop.is_set():
                    break
                try:
                    await asyncio.wait_for(
                        self._stop.wait(), timeout=self.cooldown_minutes() * 60
                    )
                    break  # stop() was called during cooldown
                except TimeoutError:
                    continue  # cooldown elapsed: next autonomous cycle
        finally:
            self._phase = "idle"

    async def _run_cycle(self, objective: str) -> None:
        coord = self.coordinator
        cycle = await coord.mission_resume_cycle(objective)
        self._cycle_id = cycle["id"]
        self._started_at = time.time()
        room = coord.mission.ensure_room()
        await self._feed(room["id"], "ceo", "AUTONOMY_CYCLE_START",
                         f"{self._cycle_id}: {objective}")

        findings = await self._phase_scan(room["id"])
        if self._stop.is_set():
            return
        prioritized = await self._phase_prioritize(room["id"], findings)
        if self._stop.is_set():
            return
        await self._phase_debate(room["id"], prioritized)
        if self._stop.is_set():
            return
        await self._phase_draft(room["id"], prioritized)

        summary = (f"ciclo {self._cycle_id}: {len(findings)} achado(s), "
                   f"{len(prioritized)} priorizado(s)")
        await coord.mission_complete_cycle(self._cycle_id, summary)
        await self._feed(room["id"], "ceo", "AUTONOMY_CYCLE_DONE", summary)
        self._last_summary = summary

    async def _feed(self, room_id: str, actor: str, event: str, detail: str) -> None:
        try:
            await asyncio.to_thread(
                self.coordinator.mission.log_feed, room_id, actor, event, detail
            )
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Phase 1 — SCAN: reader reads the ZARA codebase
    # ------------------------------------------------------------------ #
    def _repo_digest(self) -> dict[str, Any]:
        root = Path(__file__).resolve().parents[1]
        py_files: list[str] = []
        ts_files: list[str] = []
        total_lines = 0
        scanned = 0
        biggest_py = ""
        biggest_lines = 0
        for base, subdirs, files in os.walk(root):
            subdirs[:] = [d for d in subdirs
                          if not d.startswith(".") and d != "node_modules"]
            for name in files:
                if scanned >= 3000:
                    break
                rel = str(Path(base, name).relative_to(root))
                if name.endswith(".py") and "/core/" in f"/{rel}":
                    py_files.append(rel)
                elif name.endswith((".ts", ".tsx")) and "/frontend/src/" in f"/{rel}":
                    ts_files.append(rel)
                else:
                    continue
                scanned += 1
                try:
                    with open(Path(base, name), encoding="utf-8", errors="ignore") as fh:
                        lines = sum(1 for _ in fh)
                    total_lines += lines
                    if name.endswith(".py") and lines > biggest_lines:
                        biggest_lines = lines
                        biggest_py = rel
                except OSError:
                    pass
        return {
            "root": str(root),
            "py_files": len(py_files),
            "ts_files": len(ts_files),
            "total_lines": total_lines,
            "biggest_py": biggest_py,
            "sample": (py_files[:40] + ts_files[:20]),
            "ruff": self._ruff_findings(root),
        }

    def _ruff_findings(self, root: Path) -> list[str]:
        ruff = shutil.which("ruff")
        if not ruff:
            return []
        try:
            proc = subprocess.run(
                [ruff, "check", "--output-format", "concise", "core/"],
                cwd=root, capture_output=True, text=True, timeout=SCAN_TIMEOUT_S,
            )
            lines = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
            return lines[:25]
        except (OSError, subprocess.SubprocessError):
            return []

    async def _ask_reader(self, prompt: str) -> str:
        coord = self.coordinator
        runtime = getattr(coord, "worker_runtime", None)
        if runtime is not None:
            try:
                result = await asyncio.wait_for(
                    runtime.chat("openclaw", prompt), timeout=WORKER_TIMEOUT_S
                )
                text = str(result.get("response") or "").strip()
                if text:
                    return text
            except Exception:
                pass
        orchestrator = getattr(coord, "orchestrator", None)
        if orchestrator is not None:
            try:
                text = str(await asyncio.wait_for(
                    orchestrator.process_message(prompt, engine="auto"),
                    timeout=ORCHESTRATOR_TIMEOUT_S,
                )).strip()
                if text:
                    return text
            except Exception:
                pass
        return ""

    @staticmethod
    def _parse_findings(text: str) -> list[dict[str, str]]:
        findings: list[dict[str, str]] = []
        chunks = re.split(r"(?m)^\s*\d+[.)]\s+", text)
        for chunk in chunks[1:]:
            title = chunk.strip().splitlines()[0].strip()[:120]
            m_file = re.search(r"(?im)^\s*ARQUIVO\s*:\s*(.+)$", chunk)
            m_why = re.search(r"(?im)^\s*MOTIVO\s*:\s*(.+)$", chunk)
            location = m_file.group(1).strip() if m_file else ""
            why = m_why.group(1).strip() if m_why else chunk.strip()[:300]
            if title:
                findings.append({"title": title, "location": location, "summary": why})
        return findings[:MAX_FINDINGS]

    @staticmethod
    def _code_url(location: str) -> str:
        """Traceable location for a code finding (M040 rule)."""
        loc = (location or "").strip().lstrip("/").replace("\\", "/")
        if not loc or loc == "static-scan":
            return "file://zara-source/static-scan"
        return f"file://zara-source/{loc}"

    async def _phase_scan(self, room_id: str) -> list[dict[str, Any]]:
        self._phase = "scan"
        coord = self.coordinator
        await self._feed(room_id, "reader", "AUTONOMY_SCAN_START",
                         "leitor varrendo o código-fonte da ZARA")
        digest = await asyncio.to_thread(self._repo_digest)
        ruff_block = "\n".join(digest["ruff"]) if digest["ruff"] else "(ruff indisponível)"
        prompt = (
            "Você é o Leitor do conselho do ZARA Lab. Analise este resumo do "
            "código-fonte da ZARA e liste até 5 áreas que podem ser melhoradas "
            "(bugs, duplicação, performance, clareza, segurança local).\n\n"
            f"Arquivos Python: {digest['py_files']}, TS/TSX: {digest['ts_files']}, "
            f"linhas: {digest['total_lines']}.\n"
            f"Amostra de arquivos: {', '.join(digest['sample'][:20])}\n"
            f"Achados do ruff:\n{ruff_block}\n\n"
            "Responda SOMENTE com lista numerada neste formato exato:\n"
            "1. TÍTULO CURTO\n   ARQUIVO: caminho/do/arquivo\n   MOTIVO: por que melhorar (1 frase)"
        )
        raw = await self._ask_reader(prompt)
        parsed = self._parse_findings(raw) if raw else []
        findings: list[dict[str, Any]] = []
        if parsed:
            for item in parsed:
                location = item["location"] or "código-fonte da ZARA"
                finding = await asyncio.to_thread(
                    coord.research.submit_finding, MISSION_ID, "reader",
                    "ZARA codebase scan", self._code_url(location),
                    f"{item['title']} — {item['summary']}", coord.mission,
                )
                findings.append(finding)
        else:
            # Graceful degradation: static scan always yields a traceable finding.
            detail = (f"varredura estática: {digest['py_files']} .py + "
                      f"{digest['ts_files']} .ts/.tsx, {digest['total_lines']} linhas; "
                      f"{len(digest['ruff'])} alerta(s) do ruff")
            first_file = ""
            if digest["ruff"]:
                detail += f". Top: {digest['ruff'][0]}"
                match = re.match(r"([^:]+):\d+:\d+:", digest["ruff"][0])
                if match:
                    first_file = match.group(1).strip()
            if not first_file and digest.get("biggest_py"):
                # No lint alerts: the biggest core file is a review candidate.
                first_file = digest["biggest_py"]
                detail += f". Maior arquivo do core: {first_file}"
            finding = await asyncio.to_thread(
                coord.research.submit_finding, MISSION_ID, "reader",
                "ZARA codebase scan", self._code_url(first_file),
                f"Leitura estática do código da ZARA — {detail}", coord.mission,
            )
            findings.append(finding)
        await self._feed(room_id, "reader", "AUTONOMY_SCAN_DONE",
                         f"{len(findings)} achado(s) registrado(s)")
        return findings

    # ------------------------------------------------------------------ #
    # Phase 2 — PRIORITIZE: CEO ranks findings, creates proposals
    # ------------------------------------------------------------------ #
    async def _phase_prioritize(self, room_id: str,
                                findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self._phase = "prioritize"
        coord = self.coordinator
        pending = [f for f in findings if f.get("ceo_decision") == "PENDING"]
        if not pending:
            return []
        await self._feed(room_id, "ceo", "AUTONOMY_PRIORITIZE_START",
                         f"CEO priorizando {len(pending)} achado(s)")
        prioritized: list[dict[str, Any]] = []
        for finding in pending[:MAX_DEBATE_TOPICS]:
            if self._stop.is_set():
                break
            try:
                proposal = await coord.create_proposal(
                    title=str(finding.get("summary") or "Melhoria do código")[:120],
                    summary=(f"Achado do leitor: {finding.get('summary')}\n"
                             f"Fonte: {finding.get('source_name')} — {finding.get('url')}"),
                    risk="MEDIUM",
                    owner="opencode",
                )
                # Approval gate: proposals start in DISCUSSION, Alex decides.
                done = await asyncio.to_thread(
                    coord.research.ceo_prioritize, finding["id"], "PRIORITIZED",
                    "priorizado no ciclo autônomo; aguarda aprovação do Alex",
                    proposal["id"], coord.mission,
                )
                prioritized.append(done)
            except Exception as exc:
                await self._feed(room_id, "ceo", "AUTONOMY_PRIORITIZE_SKIP",
                                 f"{finding.get('id')}: {type(exc).__name__}")
        await self._feed(room_id, "ceo", "AUTONOMY_PRIORITIZE_DONE",
                         f"{len(prioritized)} proposta(s) em DISCUSSION")
        return prioritized

    # ------------------------------------------------------------------ #
    # Phase 3 — DEBATE: council talks to itself, out loud
    # ------------------------------------------------------------------ #
    async def _council_turn(self, target: str, content: str) -> None:
        try:
            await self.coordinator.send_message("ceo", target, content)
        except Exception as exc:
            room = self.coordinator.mission.ensure_room()
            await self._feed(room["id"], "ceo", "AUTONOMY_TURN_SKIPPED",
                             f"@{target}: {type(exc).__name__}")

    async def _phase_debate(self, room_id: str,
                            prioritized: list[dict[str, Any]]) -> None:
        self._phase = "debate"
        if not prioritized:
            return
        await self._feed(room_id, "ceo", "AUTONOMY_DEBATE_START",
                         f"conselho debatendo {len(prioritized)} tema(s)")
        for finding in prioritized:
            if self._stop.is_set():
                break
            topic = str(finding.get("summary") or "")[:400]
            await self._council_turn(
                "opencode",
                "Como engenheiro do conselho, analise este achado do leitor e "
                f"sugira uma abordagem técnica concreta (sem executar nada): {topic}",
            )
            if self._stop.is_set():
                break
            await self._council_turn(
                "zara",
                "Como revisora do conselho, critique a abordagem do engenheiro: "
                "riscos, alternativas e o que precisa da aprovação do Alex. "
                f"Tema: {topic}",
            )
        await self._feed(room_id, "ceo", "AUTONOMY_DEBATE_DONE",
                         "debate do conselho concluído")

    # ------------------------------------------------------------------ #
    # Phase 4 — DRAFT: engineer scopes a patch (no production writes)
    # ------------------------------------------------------------------ #
    async def _phase_draft(self, room_id: str,
                           prioritized: list[dict[str, Any]]) -> None:
        self._phase = "draft"
        if not prioritized:
            return
        coord = self.coordinator
        top = prioritized[0]
        url = str(top.get("url") or "")
        files = [url.replace("file://zara-source/", "")] if url.startswith(
            "file://zara-source/") and not url.endswith("/static-scan") else []
        try:
            patch = await asyncio.to_thread(
                coord.patches.create_patch, MISSION_ID,
                f"[autônomo] {str(top.get('summary') or '')[:100]}",
                files, "", coord.mission,
            )
            await self._feed(
                room_id, "engineer", "AUTONOMY_DRAFT_CREATED",
                f"{patch['id']}: rascunho delimitado, sem escrita em produção; "
                "promoção exige aprovação do Alex",
            )
        except Exception as exc:
            await self._feed(room_id, "engineer", "AUTONOMY_DRAFT_SKIPPED",
                             type(exc).__name__)
        self._phase = "complete"

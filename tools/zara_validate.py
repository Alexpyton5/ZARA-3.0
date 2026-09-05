"""ZaraValidationEngine — validação local determinística, sem LLM, sem tokens.

Uso:
    .venv\\Scripts\\python.exe tools\\zara_validate.py                 # incremental (so o que mudou)
    .venv\\Scripts\\python.exe tools\\zara_validate.py --full          # SAFE+SANDBOX completo
    .venv\\Scripts\\python.exe tools\\zara_validate.py --update-baseline

Nunca roda testes marcados @pytest.mark.live (bloqueado por padrão em
tests/conftest.py, precisa de ALLOW_LIVE_TESTS=1 explícito, que este script
nunca define sozinho).

Antes de qualquer agente (humano ou IA) rodar pytest por conta própria,
consulte primeiro `.zara-tests/latest.json` — se o commit é o mesmo e os
arquivos relevantes não mudaram, o resultado já está aí, gravado, sem gastar
tempo nem tokens rerodando.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZARA_TESTS_DIR = ROOT / ".zara-tests"
RUNS_DIR = ZARA_TESTS_DIR / "runs"
BASELINE_PATH = ZARA_TESTS_DIR / "baseline.json"
LATEST_PATH = ZARA_TESTS_DIR / "latest.json"
HISTORY_PATH = ZARA_TESTS_DIR / "history.json"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

# Cooldown: se a última FULL suite rodou há menos de 30 min e nada relevante
# mudou, não roda de novo -- ver `_should_skip_for_cooldown`.
COOLDOWN_SECONDS = 30 * 60


def _run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip()


def _current_commit() -> str:
    return _run_git("rev-parse", "HEAD") or "unknown"


def _changed_files() -> list[str]:
    """Arquivos diferentes do HEAD (staged + unstaged), caminho relativo ao repo."""
    staged = _run_git("diff", "--name-only", "--cached")
    unstaged = _run_git("diff", "--name-only")
    files = set(f for f in (staged + "\n" + unstaged).splitlines() if f.strip())
    return sorted(files)


def _map_changed_files_to_tests(changed: list[str]) -> list[str]:
    """Heurística simples: core/foo.py -> tests que importam core.foo ou citam foo."""
    if not changed:
        return []
    tests_dir = ROOT / "tests"
    all_tests = sorted(p for p in tests_dir.glob("test_*.py"))
    hits: set[str] = set()

    modules = set()
    for f in changed:
        p = Path(f)
        if p.suffix != ".py":
            continue
        stem = p.stem
        modules.add(stem)
        # tests/test_<stem>.py e variações test_<stem>_*.py
        direct = tests_dir / f"test_{stem}.py"
        if direct.exists():
            hits.add(str(direct.relative_to(ROOT)))

    if not modules:
        return []

    for test_file in all_tests:
        try:
            content = test_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for mod in modules:
            if mod in content:
                hits.add(str(test_file.relative_to(ROOT)))
                break

    return sorted(hits)


def _should_skip_for_cooldown(force: bool) -> tuple[bool, str]:
    if force or not LATEST_PATH.exists():
        return False, ""
    try:
        latest = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return False, ""
    if latest.get("mode") != "full":
        return False, ""
    age = time.time() - latest.get("epoch", 0)
    if age > COOLDOWN_SECONDS:
        return False, ""
    if latest.get("commit") != _current_commit():
        return False, ""
    if _changed_files():
        return False, ""
    return True, (
        f"Última FULL suite rodou há {int(age)}s (< {COOLDOWN_SECONDS}s), "
        "mesmo commit, nenhum arquivo alterado. SKIP."
    )


def _run_pytest(targets: list[str] | None, marker_expr: str) -> dict:
    args = [str(PYTHON), "-m", "pytest", "-q", "--tb=short", "-m", marker_expr]
    if targets:
        args.extend(targets)

    start = time.time()
    proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    duration = time.time() - start

    output = proc.stdout + "\n" + proc.stderr
    passed = failed = skipped = 0
    failed_tests: list[str] = []
    for line in output.splitlines():
        if line.startswith("FAILED "):
            failed_tests.append(line[len("FAILED "):].split(" - ")[0].strip())
    summary_line = ""
    for line in reversed(output.splitlines()):
        if " passed" in line or " failed" in line or " error" in line:
            summary_line = line.strip()
            break
    import re

    def _extract(word: str) -> int:
        m = re.search(rf"(\d+) {word}", summary_line)
        return int(m.group(1)) if m else 0

    passed = _extract("passed")
    failed = _extract("failed")
    skipped = _extract("skipped")

    return {
        "returncode": proc.returncode,
        "duration_seconds": round(duration, 2),
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "failed_tests": failed_tests,
        "summary_line": summary_line,
        "targets": targets or ["<marker filtered>"],
        "marker_expr": marker_expr,
    }


def _classify_against_baseline(failed_tests: list[str], baseline: dict) -> dict:
    known = set(baseline.get("known_failures", []))
    current = set(failed_tests)
    return {
        "new_failures": sorted(current - known),
        "known_failures_still_failing": sorted(current & known),
        "fixed": sorted(known - current),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true", help="Roda SAFE+SANDBOX completo")
    parser.add_argument("--force", action="store_true", help="Ignora cooldown")
    parser.add_argument(
        "--update-baseline", action="store_true",
        help="Regrava .zara-tests/baseline.json com as falhas atuais (após revisão humana)",
    )
    args = parser.parse_args()

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    baseline = {}
    if BASELINE_PATH.exists():
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))

    skip, reason = _should_skip_for_cooldown(force=args.force or args.full)
    if skip:
        print(f"[zara_validate] {reason}")
        return 0

    commit = _current_commit()
    changed = _changed_files()

    if args.full:
        mode = "full"
        result = _run_pytest(targets=None, marker_expr="not live")
    else:
        targets = _map_changed_files_to_tests(changed)
        if not targets:
            print("[zara_validate] Nenhum arquivo relevante mudou e nenhum teste incremental identificado. "
                  "Rode com --full para uma validação completa.")
            mode = "incremental-empty"
            result = {"passed": 0, "failed": 0, "skipped": 0, "failed_tests": [],
                      "summary_line": "(nada a rodar)", "targets": [], "duration_seconds": 0.0,
                      "returncode": 0, "marker_expr": "safe or sandbox"}
        else:
            mode = "incremental"
            result = _run_pytest(targets=targets, marker_expr="not live")

    classification = _classify_against_baseline(result["failed_tests"], baseline)

    run_id = time.strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = RUNS_DIR / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    record = {
        "run_id": run_id,
        "epoch": time.time(),
        "commit": commit,
        "mode": mode,
        "changed_files": changed,
        "result": result,
        "classification": classification,
    }
    (run_dir / "summary.json").write_text(json.dumps(record, indent=2), encoding="utf-8")

    md = [
        f"# Validação {run_id}",
        "",
        f"- commit: `{commit}`",
        f"- modo: {mode}",
        f"- alvo: {', '.join(result['targets']) if result['targets'] else '(nenhum)'}",
        f"- resultado: {result['summary_line'] or '(sem execução)'}",
        f"- duração: {result['duration_seconds']}s",
        "",
        "## Comparação com baseline",
        f"- NOVAS falhas: {classification['new_failures'] or 'nenhuma'}",
        f"- falhas conhecidas ainda presentes: {len(classification['known_failures_still_failing'])}",
        f"- corrigidas desde o baseline: {classification['fixed'] or 'nenhuma'}",
    ]
    (run_dir / "summary.md").write_text("\n".join(md), encoding="utf-8")

    LATEST_PATH.write_text(json.dumps(record, indent=2), encoding="utf-8")

    history = []
    if HISTORY_PATH.exists():
        try:
            history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        except Exception:
            history = []
    history.append({"run_id": run_id, "commit": commit, "mode": mode,
                     "passed": result["passed"], "failed": result["failed"],
                     "new_failures": len(classification["new_failures"])})
    HISTORY_PATH.write_text(json.dumps(history[-200:], indent=2), encoding="utf-8")

    if args.update_baseline:
        baseline["commit"] = commit
        baseline["captured_at"] = run_id
        baseline["known_failures"] = sorted(result["failed_tests"])
        BASELINE_PATH.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
        print("[zara_validate] baseline atualizado.")

    print(f"[zara_validate] {result['summary_line']}")
    if classification["new_failures"]:
        print(f"[zara_validate] ALERTA: {len(classification['new_failures'])} falha(s) NOVA(s):")
        for t in classification["new_failures"]:
            print(f"  - {t}")
        return 1
    print("[zara_validate] Nenhuma falha nova em relação ao baseline.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

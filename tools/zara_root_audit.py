"""ZARA-ROOT-AUDIT-001 -- auditoria mecanica da raiz do repositorio.

Sem IA, sem rede, deterministico. So LE e CLASSIFICA -- nunca move, nunca
apaga. Produz:

  .zara-tests/root_manifest.json   -- classificacao de cada item da raiz
  .zara-tests/latest/ZARA_ROOT_REPORT.md -- leitura humana

Uso:
    .venv\\Scripts\\python.exe tools\\zara_root_audit.py
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ZARA_TESTS_DIR = ROOT / ".zara-tests"
LATEST_DIR = ZARA_TESTS_DIR / "latest"

# Itens que SEMPRE ficam na raiz -- oficiais, nunca movidos por este auditor.
KEEP_ROOT = {
    "ZARA_TESTAR_TUDO.bat", "ABRIR-A-ZARA.bat", "ZARA_INICIAR.bat", "CLAUDE.md", "README.md",
    "pyproject.toml", ".gitignore", ".mcp.json", "main.py",
    "ZARA_ACTIVE_BUILD.json", "ZARA_ACTIVE_BUILD.txt",
    "ZARA_AGENT_START_HERE.md", "ZARA_ARCHITECTURE.md", "ZARA_DECISIONS.md",
    ".git", ".claude", ".zara-dev", ".zara-tests", ".venv",
    ".agent_context", ".ceo", ".opencode", "_quarentena", "_archive",
}

SOURCE_DIRS = {"core", "frontend", "memory", "memory_system", "integrations", "voice", "plugins", "profiles"}
TOOLS_DIRS = {"tools", "windows-ops"}
SCRIPTS_DIRS = {"scripts"}
TESTS_DIRS = {"tests"}
CONFIG_DIRS = {"config"}
DOCS_DIRS = {"docs", "wiki", "skills"}
BUILD_ARTIFACT_DIRS = {"build-sidecar", "dist-sidecar", "assets"}
CACHE_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".pnpm-store", ".dsh-inspect"}
RUNTIME_DIRS = {"data", "lembretes"}
LEGACY_DIRS = {"_design", "_quarentena", "spikes"}

CONFIG_FILES_EXT = {".toml", ".ini", ".cfg"}
LOG_EXT = {".log"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif"}
SCRIPT_EXT = {".bat", ".cmd", ".ps1"}

REPORT_NAME_HINTS = (
    "_REPORT", "_BASELINE", "_MAP", "_PLAN", "NIGHT_", "AUDIT_", "_AUDIT",
    "_SUMMARY", "_GOALS", "_HANDOFF", "_BOARD", "TRANSFORMATION", "_MANIFEST",
    "_CONTRACT", "_ARCHITECTURE", "_INTEGRATION", "_USE_CASES", "_FLOW",
    "_POLICY", "_VALIDATION", "_TEST", "SMOKE_", "FOUNDATION_",
)
OFFICIAL_DOC_NAMES = {"ZARA_ARCHITECTURE.md", "ZARA_DECISIONS.md", "ZARA_CURRENT_STATE.md"}


def _run_git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return result.stdout.strip()


def _is_git_tracked(name: str) -> bool:
    out = _run_git("ls-files", "--error-unmatch", name)
    return bool(out) or _run_git("ls-files", name) != ""


def _dir_size_and_count(path: Path) -> tuple[int, int]:
    total = 0
    count = 0
    try:
        for p in path.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                    count += 1
                except OSError:
                    pass
    except (OSError, PermissionError):
        pass
    return total, count


def _referenced_elsewhere(name: str) -> list[str]:
    """Busca textual barata (nao semantica) pelo nome do item em locais que
    importam ativamente: codigo, build, package scripts, bats. Falso-positivo
    e aceitavel aqui -- o objetivo e nunca dar falso-negativo (perder uma
    referencia real)."""
    hits: list[str] = []
    search_globs = [
        "core/**/*.py", "tools/**/*.py", "tests/**/*.py", "scripts/**/*.py",
        "frontend/src/**/*.ts", "frontend/src/**/*.tsx", "frontend/*.json",
        "*.bat", "*.ps1", "build_exe.py", "*.md",
    ]
    stem = Path(name).stem
    for pattern in search_globs:
        for f in ROOT.glob(pattern):
            if not f.is_file() or f.name == name:
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if name in text or (len(stem) > 3 and stem in text):
                hits.append(str(f.relative_to(ROOT)))
                if len(hits) >= 5:
                    return hits
    return hits


def classify(name: str, path: Path) -> dict:
    is_dir = path.is_dir()
    ext = path.suffix.lower()
    category = "UNKNOWN"
    reason = ""

    if name in KEEP_ROOT:
        category, reason = "KEEP_ROOT", "oficial, fixo na raiz"
    elif is_dir and name in SOURCE_DIRS:
        category, reason = "SOURCE", "codigo-fonte ativo"
    elif is_dir and name in TOOLS_DIRS:
        category, reason = "TOOLS", "ferramentas de operacao"
    elif is_dir and name in SCRIPTS_DIRS:
        category, reason = "SCRIPTS", "scripts utilitarios"
    elif is_dir and name in TESTS_DIRS:
        category, reason = "TESTS", "suite de testes"
    elif is_dir and name in CONFIG_DIRS:
        category, reason = "CONFIG", "configuracao"
    elif is_dir and name in DOCS_DIRS:
        category, reason = "DOCS", "documentacao"
    elif is_dir and name in BUILD_ARTIFACT_DIRS:
        category, reason = "BUILD_ARTIFACTS", "saida de build/empacotamento"
    elif is_dir and name in CACHE_DIRS:
        category, reason = "CACHE", "cache regeneravel"
    elif is_dir and name in RUNTIME_DIRS:
        category, reason = "RUNTIME", "estado de runtime do usuario"
    elif is_dir and name in LEGACY_DIRS:
        category, reason = "LEGACY", "ja isolado intencionalmente (prefixo _)"
    elif is_dir and name in {"build-sidecar", "dist-sidecar"}:
        category, reason = "BUILD_ARTIFACTS", "saida de build"
    elif name in OFFICIAL_DOC_NAMES:
        category, reason = "DOCS", "documento operacional oficial (secao 46)"
    elif ext in LOG_EXT:
        category, reason = "LOGS", "arquivo de log"
    elif ext in IMAGE_EXT:
        category, reason = "UNKNOWN", "imagem solta na raiz -- proposito nao obvio"
    elif ext == ".zip":
        category, reason = "UNKNOWN", "arquivo compactado solto na raiz"
    elif ext in SCRIPT_EXT:
        category, reason = "TOOLS", "script solto na raiz (bat/ps1/cmd)"
    elif name.endswith(".py") and not is_dir:
        category, reason = "SCRIPTS", "script Python solto na raiz"
    elif ext == ".db" or ext == ".sqlite3":
        category, reason = "RUNTIME", "banco de dados local"
    elif any(hint in name.upper() for hint in REPORT_NAME_HINTS) and ext == ".md":
        category, reason = "REPORTS", "relatorio/registro historico pontual"
    elif ext == ".txt":
        category, reason = "REPORTS", "texto solto -- provavel relatorio/registro"
    elif is_dir:
        category, reason = "UNKNOWN", "diretorio nao classificado pelas regras"
    else:
        category, reason = "UNKNOWN", "arquivo nao classificado pelas regras"

    tracked = _is_git_tracked(name)
    refs = _referenced_elsewhere(name) if category in {"UNKNOWN", "LEGACY", "REPORTS"} else []

    entry: dict = {
        "name": name,
        "type": "dir" if is_dir else "file",
        "category": category,
        "reason": reason,
        "git_tracked": tracked,
        "referenced_by": refs,
    }
    if is_dir:
        size_bytes, file_count = _dir_size_and_count(path)
        entry["size_mb"] = round(size_bytes / (1024 * 1024), 2)
        entry["file_count"] = file_count
    else:
        try:
            entry["size_kb"] = round(path.stat().st_size / 1024, 2)
        except OSError:
            entry["size_kb"] = None
    return entry


def audit_root() -> dict:
    entries = []
    for path in sorted(ROOT.iterdir(), key=lambda p: p.name.lower()):
        name = path.name
        if name in (".git",):
            entries.append({"name": name, "type": "dir", "category": "KEEP_ROOT",
                             "reason": "controle de versao", "git_tracked": True,
                             "referenced_by": [], "size_mb": None, "file_count": None})
            continue
        entries.append(classify(name, path))
    return entries


def build_report(entries: list[dict]) -> tuple[str, dict]:
    by_cat: dict[str, list[dict]] = {}
    for e in entries:
        by_cat.setdefault(e["category"], []).append(e)

    unknown = by_cat.get("UNKNOWN", [])
    reports = by_cat.get("REPORTS", [])
    hygiene = "CLEAN"
    if len(unknown) > 20 or len(reports) > 30:
        hygiene = "CRITICAL"
    elif len(unknown) > 8 or len(reports) > 15:
        hygiene = "MESSY"
    elif len(unknown) > 0 or len(reports) > 5:
        hygiene = "WARNING"

    lines = [
        "# ZARA ROOT REPORT",
        "",
        f"- gerado em: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"- itens na raiz: {len(entries)}",
        f"- ROOT HYGIENE: **{hygiene}**",
        "",
        "## Contagem por categoria",
        "",
    ]
    for cat in sorted(by_cat, key=lambda c: -len(by_cat[c])):
        lines.append(f"- {cat}: {len(by_cat[cat])}")
    lines.append("")

    if unknown:
        lines += ["## UNKNOWN -- precisa de decisao do Alex", ""]
        for e in unknown:
            size = f", {e['size_mb']}MB" if e.get("size_mb") else (f", {e['size_kb']}KB" if e.get("size_kb") else "")
            refs = f" -- referenciado por: {', '.join(e['referenced_by'])}" if e["referenced_by"] else " -- nenhuma referencia encontrada"
            lines.append(f"- **{e['name']}** ({e['reason']}{size}){refs}")
        lines.append("")

    if reports:
        lines += ["## REPORTS -- candidatos a arquivar (nao apagar)", ""]
        for e in reports:
            lines.append(f"- {e['name']}")
        lines.append("")

    for cat in ("SOURCE", "TOOLS", "SCRIPTS", "TESTS", "CONFIG", "DOCS", "RUNTIME", "CACHE", "BUILD_ARTIFACTS", "LOGS", "LEGACY", "KEEP_ROOT"):
        items = by_cat.get(cat, [])
        if not items:
            continue
        lines += [f"## {cat}", ""]
        for e in items:
            size = f" ({e['size_mb']}MB, {e['file_count']} arquivos)" if e.get("size_mb") else ""
            lines.append(f"- {e['name']}{size}")
        lines.append("")

    manifest = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "commit": _run_git("rev-parse", "--short", "HEAD") or "unknown",
        "root_hygiene": hygiene,
        "entries": entries,
    }
    return "\n".join(lines), manifest


def main() -> int:
    entries = audit_root()
    report_md, manifest = build_report(entries)

    LATEST_DIR.mkdir(parents=True, exist_ok=True)
    (LATEST_DIR / "ZARA_ROOT_REPORT.md").write_text(report_md, encoding="utf-8")
    (ZARA_TESTS_DIR / "root_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    by_cat: dict[str, int] = {}
    for e in entries:
        by_cat[e["category"]] = by_cat.get(e["category"], 0) + 1
    print(f"ROOT HYGIENE: {manifest['root_hygiene']}")
    print(f"Itens: {len(entries)}")
    for cat, n in sorted(by_cat.items(), key=lambda kv: -kv[1]):
        print(f"  {cat}: {n}")
    print(f"\nRelatorio: {LATEST_DIR / 'ZARA_ROOT_REPORT.md'}")
    print(f"Manifest:  {ZARA_TESTS_DIR / 'root_manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

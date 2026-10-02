#!/usr/bin/env python3
"""bruno_security_audit.py — BRUNO (time de Saude & Seguranca).
Auditoria SOMENTE LEITURA. Nunca edita, nunca commita, nunca apaga.
Roda da raiz do repo:  python tools/bruno_security_audit.py
Saida: 0 = limpo, 1 = achados (lista o que achou).
"""
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
findings = []


def ok(msg):
    print("OK   " + msg)


def bad(msg):
    print("FALHA " + msg)
    findings.append(msg)


def sh(*args):
    try:
        return subprocess.run(
            args, cwd=ROOT, capture_output=True, timeout=60,
            encoding="utf-8", errors="replace", text=True,
        ).stdout or ""
    except Exception:
        return ""


# 1) Simbolos da quarentena: so podem existir nas 2 linhas de comentario conhecidas
print("== 1) Quarentena ==")
allowed = {
    ("core/auto_repair.py", 17),
    ("core/supercerebro_grant.py", 19),
    ("core/supercerebro_grant.py", 20),
}
pats = ["work_mode_active", "work_mode_sentinel", "_watch_supercerebro_work_mode"]
hits = 0
for py in (ROOT / "core").rglob("*.py"):
    try:
        lines = py.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        continue
    for i, ln in enumerate(lines, 1):
        for p in pats:
            if p in ln:
                rel = py.relative_to(ROOT).as_posix()
                if (rel, i) not in allowed:
                    bad("simbolo banido fora do comentario: %s:%d" % (rel, i))
                    hits += 1
if hits == 0:
    ok("nenhum simbolo da quarentena fora dos comentarios conhecidos")

# 2) Segredos no diff nao-commitado
print("== 2) Segredos no diff ==")
diff = sh("git", "diff", "--", ".")
secret_re = re.compile(
    r"(?i)(api[_-]?key|bearer|token|passwd|password|secret)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{16,}"
)
found = [ln for ln in diff.splitlines() if ln.startswith("+") and secret_re.search(ln)]
if found:
    bad("%d linhas suspeitas de segredo no diff" % len(found))
else:
    ok("nenhum segredo aparente no diff")

# 3) SHA256 dos arquivos criticos vs baseline (doc 39, 01/10/2026 ~23:50)
print("== 3) Hashes baseline ==")
baseline = {
    "core/action_registry.py": "B1A29505B01BC1370DD82CA0B02FB1B83FE94BEB25FBFDCA035D3CB96247F713",
    "core/computer_agent.py": "1113224137A65E42C4AB51D8565B231468BC857F86226844BDECF755D1DBD5DA",
    "core/actions/computer_command.py": "A89C2B9B12B5984728599B16E1EF5A2F462B80CA24AF61A36D226C164EC0D597",
    "core/ipc_handlers.py": "DB7B1DA9ED58696434B98B77B7EAFE73CA34D4C1DB0FCF9A4CBF5DE4052647E0",
    "memory/project_memory.py": "A1D2096EDC22DB58A508EDF89C8968E47972C41BD5E348DBB47933D4F74D5B73",
    "frontend/src/zoeBridge.ts": "C256CF8181F56E045EA16FFBCF26599DEE67230EBA859D7F9270E9620C9C8BC6",
}
drift = 0
for rel, want in baseline.items():
    p = ROOT / rel
    if not p.exists():
        bad("arquivo sumiu: " + rel)
        continue
    got = hashlib.sha256(p.read_bytes()).hexdigest().upper()
    if got != want:
        bad("hash mudou: " + rel)
        drift += 1
if drift == 0:
    ok("6/6 hashes iguais ao baseline")

# 4) BOM do ipc_handlers.py (regra do time; hoje ausente — so reporta)
print("== 4) BOM ipc_handlers.py ==")
raw = (ROOT / "core/ipc_handlers.py").read_bytes()[:3]
if raw == b"\xef\xbb\xbf":
    ok("BOM presente")
else:
    print("INFO BOM ausente (pre-existente, doc 48)")

print()
if findings:
    print("RESULTADO: %d achado(s)" % len(findings))
    sys.exit(1)
print("RESULTADO: limpo")

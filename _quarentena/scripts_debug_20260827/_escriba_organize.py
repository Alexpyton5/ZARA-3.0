import os, re, subprocess, shutil, json

ROOT = os.path.abspath(os.path.dirname(__file__))
os.chdir(ROOT)

KEEP = {
    "main.py", "build_exe.py", "run.py", "run_tests.py", "snapshot_zara.py",
    "pyproject.toml", "pytest.ini", "requirements.txt", "README.md",
    "_escriba_organize.py", "coverage.json", ".gitignore",
}

files = [f for f in os.listdir(".") if os.path.isfile(f)]

def cat(f):
    if f in KEEP:
        return None
    low = f.lower()
    base, ext = os.path.splitext(low)
    # python debug/test/check/temp
    if ext == ".py":
        if base.startswith("fix_") or base in ("do_patch", "do_update", "patch_gemini", "patch_user_memory", "apply_both", "apply_pipecat", "add_format_check", "add_format_check2"):
            return "scripts/fix"
        if (base.startswith(("debug_", "check_", "test_", "temp_", "tmp_", "smoke_test",
                             "verify_", "extract_", "show_", "update_pattern", "list_",
                             "ipc_", "demo_", "compare_", "compile_", "coverage_",
                             "analyze_", "audit_", "class_check", "final_", "find_coverage",
                             "get_backend_handlers", "get_handler_names", "dup_check",
                             "cap_action_count", "categorize_added", "category_status",
                             "clean_section", "create_template", "insert_section",
                             "large_files", "model_router_check", "new_action_mapping",
                             "orchestrator_check", "scan_actions", "secret_check",
                             "nightly_regression", "backend_ipc", "frontend_ipc",
                             "do_it", "hello", "_audit_runner", "_read_head",
                             "enable_pc_control", "update_correct", "update_manifest",
                             "update_user_memory", "run_test"))
            or base.endswith("_check")):
            return "scripts/debug"
        return None
    # audit / report docs
    if ext in (".md", ".txt"):
        if re.search(r"(audit|auditoria|report|relatorio|vigia|lixo_candidatos|metricas-baseline)", low):
            return "docs/audits"
        if base in ("outcome", "response", "finalresponse", "final_response", "resultado_final",
                    "status", "temp_mapping", "frontend_ipc", "frontend_ipc_calls",
                    "frontend_methods", "frontend_underscore", "test_quotes",
                    "ultimo_candidato"):
            return "docs/audits"
    return None

plan = {}
for f in sorted(files):
    d = cat(f)
    if d:
        plan.setdefault(d, []).append(f)

# api_keys backups
bk = [f for f in os.listdir("config") if f.startswith("api_keys.json") and f != "api_keys.json" and f != "api_keys.example.json"]

def tracked(p):
    r = subprocess.run(["git", "ls-files", "--error-unmatch", p], capture_output=True, text=True)
    return r.returncode == 0

def move(src, dstdir):
    os.makedirs(dstdir, exist_ok=True)
    dst = os.path.join(dstdir, os.path.basename(src))
    if os.path.exists(dst):
        return ("skip-exists", src)
    if tracked(src):
        r = subprocess.run(["git", "mv", src, dst], capture_output=True, text=True)
        if r.returncode == 0:
            return ("git mv", src)
    shutil.move(src, dst)
    return ("shutil", src)

log = []
for d, fs in plan.items():
    for f in fs:
        log.append((d,) + move(f, d))
for f in bk:
    log.append(("config/backups",) + move(os.path.join("config", f), "config/backups"))

print(json.dumps({"moved": len(log), "log": [list(x) for x in log]}, indent=1, ensure_ascii=False))

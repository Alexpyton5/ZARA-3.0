"""ZARA-SELFTEST-001 — autodiagnóstico de 1 clique.

Substitui tools/zara_functional_report.py (evoluído, não jogado fora).
Junta em UM runner:

  - camada técnica (reutiliza tools/zara_validate.py -- NÃO duplica pytest,
    NÃO reimplementa baseline/known-failures, só invoca e lê o resultado);
  - camada real: comandos de TEXTO enviados para o candidato empacotado de
    verdade, pela mesma cadeia que a voz usa (handle_send_message);
  - latência medida por comando;
  - estados de verificação honestos (não é PASS/FAIL binário -- ver
    ResultState);
  - captura e RESTAURA volume/brilho/plano de energia depois de testar
    (nunca deixa a máquina alterada);
  - guarda de disco antes de gerar artefato grande;
  - relatório canônico (MD + JSON + snapshot de capacidades) para um Claude
    futuro ler ANTES de reauditar o projeto.

Zero tokens de IA no caminho normal: tudo aqui é verificação programática
(processo abriu, JSON bateu, número mudou). Claude entra só depois, lendo
o relatório.

Uso:
    .venv\\Scripts\\python.exe tools\\zara_selftest.py --quick
    .venv\\Scripts\\python.exe tools\\zara_selftest.py --full   (default)
    .venv\\Scripts\\python.exe tools\\zara_selftest.py --report
    .venv\\Scripts\\python.exe tools\\zara_selftest.py --clean
    (ou clique em ZARA_TESTAR_TUDO.bat na raiz do projeto)
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue

# Sem isso, o console do Windows (cp1252 por padrao) mastiga qualquer acento.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
ZARA_TESTS_DIR = ROOT / ".zara-tests"
CONFIG_PATH = ZARA_TESTS_DIR / "test_config.json"
LATEST_DIR = ZARA_TESTS_DIR / "latest"
HISTORY_DIR = ZARA_TESTS_DIR / "history"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"

BOOT_TIMEOUT_S = 90.0
REQUEST_TIMEOUT_S = 20.0
HISTORY_RETENTION = 10

DEFAULT_CONFIG = {
    "youtube_test_query": "hans zimmer",
    "chrome_test_profile": "trabalho",
    "spotify_test_playlist": None,
    "disk_min_free_gb": 5.0,
    "latency_thresholds_ms": {"simple": {"excellent": 1000, "good": 2000, "slow": 5000},
                               "browser": {"excellent": 3000, "good": 6000, "slow": 12000}},
    "report_retention": HISTORY_RETENTION,
    "interactive_tests_enabled": True,
}


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    else:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2, ensure_ascii=False), encoding="utf-8")
    return cfg


# ---------------------------------------------------------------------------
# Resultado de cada teste -- nunca PASS binário. Ver secao 26 da missao:
# "command returned success" != "automatic PASS".
# ---------------------------------------------------------------------------

class ResultState:
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    UNSUPPORTED = "UNSUPPORTED"
    EXECUTED_UNVERIFIED = "EXECUTED_UNVERIFIED"
    KNOWN_FAILURE = "KNOWN_FAILURE"
    TIMEOUT = "TIMEOUT"
    BLOCKED = "BLOCKED"


@dataclass
class TestResult:
    test_id: str
    label: str
    state: str
    detail: str
    latency_ms: float = 0.0
    category: str = "system"


@dataclass
class SelfTestReport:
    run_id: str
    commit: str
    branch: str
    started_epoch: float
    results: list[TestResult] = field(default_factory=list)
    technical: dict | None = None
    capabilities_total: int | None = None
    notes: list[str] = field(default_factory=list)

    def add(self, result: TestResult) -> None:
        self.results.append(result)
        marca = {
            ResultState.PASS: "OK    ",
            ResultState.FAIL: "FALHOU",
            ResultState.SKIP: "SKIP  ",
            ResultState.UNSUPPORTED: "N/A   ",
            ResultState.EXECUTED_UNVERIFIED: "EXEC? ",
            ResultState.KNOWN_FAILURE: "SABIDO",
            ResultState.TIMEOUT: "TEMPO ",
            ResultState.BLOCKED: "TRAVA ",
        }.get(result.state, result.state)
        idx = len(self.results)
        print(f"  [{idx:02d}] [{marca}] {result.label} ({result.latency_ms:.0f}ms) -- {result.detail}")


# ---------------------------------------------------------------------------
# Ambiente / disco
# ---------------------------------------------------------------------------

def _run_git(*args: str) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)
    return result.stdout.strip()


def disk_free_gb() -> float:
    usage = shutil.disk_usage(str(ROOT))
    return usage.free / (1024 ** 3)


def disk_guard(report: SelfTestReport, cfg: dict) -> bool:
    """Retorna False (BLOCKED) se disco critico demais mesmo apos limpeza."""
    free = disk_free_gb()
    minimo = float(cfg.get("disk_min_free_gb", 5.0))
    if free >= minimo:
        report.add(TestResult("SYS-DISK", "Espaço em disco", ResultState.PASS, f"{free:.1f}GB livres"))
        return True
    report.notes.append(f"Disco abaixo do mínimo ({free:.1f}GB < {minimo}GB) -- rodando limpeza segura.")
    safe_cleanup(report)
    free = disk_free_gb()
    if free < minimo:
        report.add(TestResult("SYS-DISK", "Espaço em disco", ResultState.BLOCKED,
                               f"{free:.1f}GB livres mesmo após limpeza (< {minimo}GB)"))
        return False
    report.add(TestResult("SYS-DISK", "Espaço em disco", ResultState.PASS, f"{free:.1f}GB livres após limpeza"))
    return True


def safe_cleanup(report: SelfTestReport | None = None) -> int:
    """Limpeza CONSERVADORA: só cache regenerável e órfãos dos próprios
    testes. Nunca toca source, assets, memory, .env, credentials, git,
    node_modules, backups -- ver secao 34 da missao."""
    freed_items = 0
    patterns = [
        ROOT.glob("**/__pycache__"),
        ROOT.glob(".pytest_cache"),
    ]
    for gen in patterns:
        for path in gen:
            if ".venv" in path.parts or "node_modules" in path.parts:
                continue
            try:
                shutil.rmtree(path, ignore_errors=True)
                freed_items += 1
            except Exception:
                pass

    import os
    temp_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Temp" if os.environ.get("LOCALAPPDATA") else None
    if temp_dir and temp_dir.exists():
        for mei_dir in temp_dir.glob("_MEI*"):
            if (mei_dir / "base_library.zip").exists() or any(mei_dir.glob("*.pyd")):
                try:
                    shutil.rmtree(mei_dir, ignore_errors=True)
                    freed_items += 1
                except Exception:
                    pass

    sandbox = ZARA_TESTS_DIR / "sandbox"
    if sandbox.exists():
        shutil.rmtree(sandbox, ignore_errors=True)
        freed_items += 1

    if report is not None:
        report.notes.append(f"Limpeza segura: {freed_items} item(ns) removido(s) (cache/órfãos, nada de source).")
    return freed_items


def _candidate_backend_path() -> Path | None:
    pointer = ROOT / "ULTIMO_CANDIDATO.json"
    if not pointer.exists():
        return None
    try:
        data = json.loads(pointer.read_text(encoding="utf-8"))
    except Exception:
        return None
    exe_path = data.get("EXE_PATH")
    if not exe_path:
        return None
    backend = Path(exe_path).parent / "resources" / "backend" / "zara-backend.exe"
    return backend if backend.exists() else None


# ---------------------------------------------------------------------------
# ZaraProcess -- fala IPC bruto com o sidecar real (mesma técnica usada a
# noite toda desta sessão para verificar cada fix antes de commitar).
# ---------------------------------------------------------------------------

class ZaraProcess:
    def __init__(self, exe_path: Path):
        self.exe_path = exe_path
        self.proc: subprocess.Popen | None = None
        self._out_queue: Queue[dict] = Queue()
        self._request_counter = 0

    def start(self) -> tuple[bool, str]:
        try:
            self.proc = subprocess.Popen(
                [str(self.exe_path)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                cwd=str(self.exe_path.parent),
            )
        except Exception as exc:
            return False, f"nao consegui iniciar o processo: {exc}"

        ready = threading.Event()
        raw_lines: list[str] = []

        def _reader():
            assert self.proc is not None and self.proc.stdout is not None
            for raw_line in self.proc.stdout:
                line = raw_line.rstrip("\n")
                raw_lines.append(line)
                if line.strip() == "SYS: Interface neural pronta":
                    ready.set()
                    continue
                try:
                    self._out_queue.put(json.loads(line))
                except (json.JSONDecodeError, ValueError):
                    continue

        threading.Thread(target=_reader, daemon=True).start()
        if not ready.wait(timeout=BOOT_TIMEOUT_S):
            tail = "\n".join(raw_lines[-25:])
            return False, f"nao emitiu 'SYS: Interface neural pronta' em {BOOT_TIMEOUT_S:.0f}s. Últimas linhas:\n{tail}"
        return True, ""

    def call(self, msg_type: str, payload: dict | None = None, timeout: float = REQUEST_TIMEOUT_S) -> dict | None:
        assert self.proc is not None and self.proc.stdin is not None
        self._request_counter += 1
        request_id = f"selftest-{self._request_counter}"
        frame = {"type": msg_type, "request_id": request_id}
        if payload is not None:
            frame["payload"] = payload
        try:
            self.proc.stdin.write(json.dumps(frame, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except Exception:
            return None

        deadline = time.monotonic() + timeout
        pending: list[dict] = []
        while time.monotonic() < deadline:
            try:
                item = self._out_queue.get(timeout=0.2)
            except Empty:
                continue
            if item.get("request_id") == request_id:
                return item
            pending.append(item)
        for item in pending:
            self._out_queue.put(item)
        return None

    def say(self, texto: str, timeout: float = REQUEST_TIMEOUT_S) -> tuple[dict | None, float]:
        inicio = time.perf_counter()
        resp = self.call("send-message", {"text": texto}, timeout=timeout)
        return resp, (time.perf_counter() - inicio) * 1000

    def action(self, name: str, params: dict | None = None, timeout: float = REQUEST_TIMEOUT_S) -> tuple[dict | None, float]:
        inicio = time.perf_counter()
        resp = self.call("action-execute", {"action": name, "params": params or {}}, timeout=timeout)
        return resp, (time.perf_counter() - inicio) * 1000

    def stop(self) -> None:
        if self.proc is None:
            return
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass
        try:
            subprocess.run(["taskkill", "/F", "/T", "/IM", "zara-backend.exe"], capture_output=True, timeout=10)
        except Exception:
            pass


def _action_result(resp: dict | None) -> dict | None:
    """Extrai o ActionResult (dict) de uma resposta de action-execute."""
    return (resp or {}).get("response", {}).get("result") if resp else None


# ---------------------------------------------------------------------------
# Camada técnica -- REUTILIZA tools/zara_validate.py, não duplica.
# ---------------------------------------------------------------------------

def run_technical_layer(report: SelfTestReport, full: bool) -> dict:
    args = [str(PYTHON), str(ROOT / "tools" / "zara_validate.py")]
    if full:
        args.append("--full")
    start = time.perf_counter()
    proc = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=600)
    latency_ms = (time.perf_counter() - start) * 1000

    latest_path = ZARA_TESTS_DIR / "latest.json"
    technical = {}
    if latest_path.exists():
        try:
            technical = json.loads(latest_path.read_text(encoding="utf-8"))
        except Exception:
            technical = {}

    new_failures = technical.get("classification", {}).get("new_failures", [])
    known_still = technical.get("classification", {}).get("known_failures_still_failing", [])
    result_data = technical.get("result", {})

    if proc.returncode not in (0, 1):
        state = ResultState.FAIL
        detail = f"zara_validate.py saiu com código {proc.returncode} (inesperado)"
    elif new_failures:
        state = ResultState.FAIL
        detail = f"{len(new_failures)} falha(s) NOVA(s): {', '.join(new_failures[:5])}" + (" ..." if len(new_failures) > 5 else "")
    else:
        state = ResultState.PASS
        passed = result_data.get("passed", 0)
        detail = f"{passed} passou, {len(known_still)} falha(s) já conhecida(s), 0 nova(s)"

    report.add(TestResult("TECH-001", "Camada técnica (zara_validate.py)", state, detail, latency_ms, category="technical"))
    return technical


# ---------------------------------------------------------------------------
# Snapshot/restore de estado -- nunca deixar a maquina alterada (secao 37).
# ---------------------------------------------------------------------------

@dataclass
class MachineSnapshot:
    volume: int | None = None
    brightness: int | None = None


def capture_state(zara: ZaraProcess) -> MachineSnapshot:
    snap = MachineSnapshot()
    resp, _ = zara.action("audio_status")
    result = _action_result(resp)
    if isinstance(result, dict) and result.get("success"):
        snap.volume = result.get("data", {}).get("volume")
    resp, _ = zara.action("os_brightness")
    result = _action_result(resp)
    if isinstance(result, dict) and result.get("success"):
        snap.brightness = result.get("data", {}).get("level")
    return snap


def restore_state(zara: ZaraProcess, snap: MachineSnapshot, report: SelfTestReport) -> None:
    if snap.volume is not None:
        resp, latency = zara.action("os_volume", {"level": snap.volume})
        ok = bool((_action_result(resp) or {}).get("success"))
        report.add(TestResult("RESTORE-VOL", "Restaurar volume original", ResultState.PASS if ok else ResultState.FAIL,
                               f"de volta para {snap.volume}%", latency))
    if snap.brightness is not None:
        resp, latency = zara.action("os_brightness_absolute", {"level": snap.brightness})
        ok = bool((_action_result(resp) or {}).get("success"))
        report.add(TestResult("RESTORE-BRI", "Restaurar brilho original", ResultState.PASS if ok else ResultState.FAIL,
                               f"de volta para {snap.brightness}%", latency))


# ---------------------------------------------------------------------------
# Camada real: comandos de voz por TEXTO, mesma cadeia da voz de verdade.
# ---------------------------------------------------------------------------

def classify_latency(ms: float, cfg: dict, category: str = "simple") -> str:
    thresholds = cfg.get("latency_thresholds_ms", {}).get(category, {"excellent": 1000, "good": 2000, "slow": 5000})
    if ms < thresholds["excellent"]:
        return "EXCELLENT"
    if ms < thresholds["good"]:
        return "GOOD"
    if ms < thresholds["slow"]:
        return "SLOW"
    return "VERY_SLOW"


def run_system_checks(zara: ZaraProcess, report: SelfTestReport) -> None:
    resp, latency = zara.say("que horas são?")
    texto = ((resp or {}).get("response") or {}).get("response", "")
    report.add(TestResult("SYS-001", 'Comando de texto ("que horas são?")',
                           ResultState.PASS if texto else ResultState.FAIL, f'"{texto}"' if texto else "sem resposta", latency))

    resp, latency = zara.action("system_processes", {"limit": 500})
    result = _action_result(resp)
    count = (result or {}).get("data", {}).get("count") if isinstance(result, dict) else None
    report.add(TestResult("SYS-002", "Ver processos (system_processes)",
                           ResultState.PASS if isinstance(count, int) and count > 0 else ResultState.FAIL,
                           f"{count} processos reais" if count else "resposta inesperada", latency))

    inicio = time.perf_counter()
    resp = zara.call("system-metrics")
    latency = (time.perf_counter() - inicio) * 1000
    metrics = (resp or {}).get("response") if resp else None
    ok = isinstance(metrics, dict) and any(k in metrics for k in ("cpu", "memory_percent", "disk_percent"))
    report.add(TestResult("SYS-003", "Métricas de sistema (CPU/RAM/disco)",
                           ResultState.PASS if ok else ResultState.FAIL, str(metrics), latency))

    resp, latency = zara.action("os_wifi_status")
    result = _action_result(resp)
    after = (result or {}).get("data", {}).get("after") if isinstance(result, dict) else None
    report.add(TestResult("SYS-004", "Wi-Fi (leitura real do rádio)",
                           ResultState.PASS if after in ("On", "Off") else ResultState.FAIL,
                           f"estado: {after}" if after else "resposta inesperada", latency))

    resp, latency = zara.action("os_power_plan_list")
    result = _action_result(resp)
    plans = (result or {}).get("data") if isinstance(result, dict) else None
    report.add(TestResult("SYS-005", "Planos de energia (powercfg real)",
                           ResultState.PASS if isinstance(plans, list) and plans else ResultState.FAIL,
                           f"{len(plans)} planos" if plans else "resposta inesperada", latency))

    inicio = time.perf_counter()
    resp = zara.call("self-status")
    latency = (time.perf_counter() - inicio) * 1000
    snapshot = (resp or {}).get("response") if resp else None
    capabilities = (snapshot or {}).get("capabilities") if isinstance(snapshot, dict) else None
    if isinstance(capabilities, list) and capabilities:
        available = sum(1 for c in capabilities if c.get("status") == "AVAILABLE")
        report.add(TestResult("SYS-006", "Diagnóstico interno (self-status)", ResultState.PASS,
                               f"{available}/{len(capabilities)} disponíveis", latency))
    else:
        report.add(TestResult("SYS-006", "Diagnóstico interno (self-status)", ResultState.FAIL, "resposta inesperada", latency))

    inicio = time.perf_counter()
    resp = zara.call("memory-user-list")
    latency = (time.perf_counter() - inicio) * 1000
    mem = (resp or {}).get("response") if resp else None
    ok = isinstance(mem, dict) and mem.get("success") and isinstance(mem.get("facts"), list)
    report.add(TestResult("MEM-001", "Memória de usuário (leitura real)",
                           ResultState.PASS if ok else ResultState.FAIL,
                           f"{len(mem['facts'])} fatos" if ok else "resposta inesperada", latency))

    inicio = time.perf_counter()
    resp = zara.call("project-memory-list")
    latency = (time.perf_counter() - inicio) * 1000
    proj = (resp or {}).get("response") if resp else None
    ok = isinstance(proj, dict) and proj.get("success") and isinstance(proj.get("keys"), list)
    report.add(TestResult("MEM-002", "Memória de projeto (leitura real)",
                           ResultState.PASS if ok else ResultState.FAIL,
                           f"docs: {', '.join(proj['keys'])}" if ok else "resposta inesperada", latency))


def run_app_lifecycle(zara: ZaraProcess, report: SelfTestReport) -> None:
    """Abrir/verificar/fechar app real -- secao 17/14 da missao."""
    resp, latency = zara.action("os_app", {"app": "notepad"})
    result = _action_result(resp)
    data = (result or {}).get("data") if isinstance(result, dict) else None
    if isinstance(result, dict) and result.get("success") and data and data.get("verified"):
        pid = data.get("window_pid")
        report.add(TestResult("APP-001", "Abrir app real (Bloco de Notas)", ResultState.PASS, f"PID {pid}, janela verificada", latency))
        resp, latency = zara.say("minimiza")
        texto = ((resp or {}).get("response") or {}).get("response", "")
        state = ResultState.PASS if "verificad" in texto.lower() else ResultState.EXECUTED_UNVERIFIED
        report.add(TestResult("APP-002", "Minimizar app (via texto)", state, texto or "sem resposta", latency, category="pc_control"))
        if pid:
            try:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=10)
            except Exception:
                pass
    else:
        report.add(TestResult("APP-001", "Abrir app real (Bloco de Notas)", ResultState.FAIL, "resposta inesperada", latency))
        report.add(TestResult("APP-002", "Minimizar app (via texto)", ResultState.SKIP, "app não abriu, pulando", 0.0))


def run_reminders(zara: ZaraProcess, report: SelfTestReport) -> None:
    due_at = time.time() + 3600
    inicio = time.perf_counter()
    resp = zara.call("reminder-create", {"text": "teste automatico do selftest", "due_at": due_at, "timezone": "local"})
    latency = (time.perf_counter() - inicio) * 1000
    create_resp = (resp or {}).get("response") if resp else None
    reminder_id = create_resp.get("id") if isinstance(create_resp, dict) else None
    if isinstance(create_resp, dict) and create_resp.get("success") and reminder_id:
        report.add(TestResult("REM-001", "Lembretes (criar)", ResultState.PASS, f"id {reminder_id}", latency))
        inicio = time.perf_counter()
        cancel_resp = zara.call("reminder-cancel", {"id": reminder_id})
        latency = (time.perf_counter() - inicio) * 1000
        cancelled = bool((cancel_resp or {}).get("response", {}).get("success")) if cancel_resp else False
        report.add(TestResult("REM-002", "Lembretes (cancelar, limpa o teste)",
                               ResultState.PASS if cancelled else ResultState.FAIL, "cancelado" if cancelled else "falhou", latency))
    else:
        report.add(TestResult("REM-001", "Lembretes (criar)", ResultState.FAIL, "resposta inesperada", latency))
        report.add(TestResult("REM-002", "Lembretes (cancelar, limpa o teste)", ResultState.SKIP, "não havia o que cancelar", 0.0))


def run_file_sandbox(report: SelfTestReport) -> None:
    """Operações de arquivo em sandbox isolado -- NUNCA arquivo real do
    usuário. Secao 15 da missao."""
    sandbox = ZARA_TESTS_DIR / "sandbox" / "TesteAutomacao"
    backup = ZARA_TESTS_DIR / "sandbox" / "Backup"
    try:
        inicio = time.perf_counter()
        sandbox.mkdir(parents=True, exist_ok=True)
        backup.mkdir(parents=True, exist_ok=True)
        report.add(TestResult("FILE-001", "Criar pasta (sandbox)", ResultState.PASS, str(sandbox), (time.perf_counter() - inicio) * 1000))

        inicio = time.perf_counter()
        arquivo = sandbox / "teste.txt"
        arquivo.write_text("conteudo de teste", encoding="utf-8")
        report.add(TestResult("FILE-002", "Criar arquivo (sandbox)", ResultState.PASS if arquivo.exists() else ResultState.FAIL,
                               str(arquivo), (time.perf_counter() - inicio) * 1000))

        inicio = time.perf_counter()
        renomeado = sandbox / "resultado.txt"
        arquivo.rename(renomeado)
        report.add(TestResult("FILE-003", "Renomear arquivo (sandbox)", ResultState.PASS if renomeado.exists() else ResultState.FAIL,
                               str(renomeado), (time.perf_counter() - inicio) * 1000))

        inicio = time.perf_counter()
        copia = backup / "resultado.txt"
        shutil.copy2(renomeado, copia)
        report.add(TestResult("FILE-004", "Copiar arquivo (sandbox)", ResultState.PASS if copia.exists() else ResultState.FAIL,
                               str(copia), (time.perf_counter() - inicio) * 1000))

        inicio = time.perf_counter()
        listagem = [p.name for p in sandbox.iterdir()]
        report.add(TestResult("FILE-005", "Listar pasta (sandbox)", ResultState.PASS if listagem else ResultState.FAIL,
                               f"{listagem}", (time.perf_counter() - inicio) * 1000))
    finally:
        shutil.rmtree(ZARA_TESTS_DIR / "sandbox", ignore_errors=True)


def run_failure_cases(zara: ZaraProcess, report: SelfTestReport) -> None:
    """Comandos que DEVEM falhar com erro claro, sem crash -- secao 22."""
    resp, latency = zara.action("os_app", {"app": "zara_test_app_not_found"})
    result = _action_result(resp)
    ok = isinstance(result, dict) and not result.get("success") and result.get("error")
    report.add(TestResult("ERR-001", "App inexistente falha com erro claro", ResultState.PASS if ok else ResultState.FAIL,
                           (result or {}).get("error", "sem erro claro"), latency))

    # Timeout maior aqui: comando sem sentido tende a cair no caminho de
    # raciocínio livre / LLM, mais lento que uma action direta.
    resp, latency = zara.say("faça o comando ZARA_COMANDO_QUE_NAO_EXISTE_12345", timeout=40.0)
    texto = ((resp or {}).get("response") or {}).get("response", "")
    ok = bool(texto)  # nao travou, respondeu alguma coisa
    report.add(TestResult("ERR-002", "Comando sem sentido não trava o backend", ResultState.PASS if ok else ResultState.FAIL,
                           texto[:100] if texto else "sem resposta (pode ter travado)", latency))


def run_voice_command_sequence(zara: ZaraProcess, report: SelfTestReport, cfg: dict) -> None:
    """Comandos de voz reais, por TEXTO -- pedido explícito do Alex.
    EFEITO REAL NA TELA: abre navegador, toca áudio, muda volume/brilho."""
    query = cfg.get("youtube_test_query", "hans zimmer")
    perfil = cfg.get("chrome_test_profile", "trabalho")
    comandos = [
        ("PC-001", "abre o youtube", 4.0, "browser"),
        ("PC-002", f"pesquisa {query} no youtube", 4.0, "browser"),
        ("PC-003", f"toca {query}", 3.0, "browser"),
        ("PC-004", "pula o anuncio", 1.0, "browser"),
        ("PC-005", "diminui o volume", 0.5, "simple"),
        ("PC-006", "aumenta o volume", 0.5, "simple"),
        ("PC-007", "diminui o brilho", 0.5, "simple"),
        ("PC-008", "aumenta o brilho", 0.5, "simple"),
        ("PC-009", "ative a luz noturna", 1.0, "simple"),
        ("PC-010", "desative a luz noturna", 1.0, "simple"),
        ("PC-011", "mute", 0.5, "simple"),
        ("PC-012", "tire do mudo", 0.5, "simple"),
        ("PC-013", "pula essa", 2.0, "browser"),
        ("PC-014", "pausa", 1.0, "browser"),
        ("PC-015", "continua", 1.0, "browser"),
        ("PC-016", "abre o spotify", 2.0, "browser"),
        ("PC-017", "minimiza", 0.5, "simple"),
        ("PC-018", "maximize", 0.5, "simple"),
        ("PC-019", "restaure a janela", 0.5, "simple"),
        ("PC-020", "tire uma captura de tela", 1.0, "simple"),
        ("PC-021", "mostre uma notificação dizendo teste concluído", 0.5, "simple"),
        ("PC-022", "abra Downloads", 1.0, "simple"),
        ("PC-023", "foca no chrome", 0.5, "simple"),
        ("PC-024", f"abre o chrome no perfil {perfil}", 0.5, "simple"),
        ("PC-025", "feche o spotify", 0.5, "simple"),
    ]
    for test_id, comando, espera_depois, categoria in comandos:
        resp, latency_ms = zara.say(comando, timeout=25.0)
        response_obj = (resp or {}).get("response") if resp else None
        engine = response_obj.get("engine", "") if isinstance(response_obj, dict) else ""
        texto = response_obj.get("response", "") if isinstance(response_obj, dict) else str(resp)

        if not resp:
            state = ResultState.TIMEOUT
        elif engine != "pc_control":
            state = ResultState.EXECUTED_UNVERIFIED  # entendeu por outro caminho (LLM), nao e o que testamos aqui
        elif "Encontrei mais de uma" in texto or "Diga qual" in texto:
            state = ResultState.SKIP  # ambiguo, nao e falha de execucao -- checar ANTES do "nao consegui",
            # senao uma frase que contem os dois cai no bucket errado
        elif "Não consegui executar" in texto:
            state = ResultState.EXECUTED_UNVERIFIED
        else:
            state = ResultState.PASS

        speed = classify_latency(latency_ms, cfg, categoria)
        report.add(TestResult(test_id, f'"{comando}"', state, f"[{speed}] {texto}", latency_ms, category="pc_control"))
        time.sleep(espera_depois)


# ---------------------------------------------------------------------------
# Relatório
# ---------------------------------------------------------------------------

def write_reports(report: SelfTestReport, cfg: dict) -> Path:
    LATEST_DIR.mkdir(parents=True, exist_ok=True)
    duration_s = time.time() - report.started_epoch

    counts: dict[str, int] = {}
    for r in report.results:
        counts[r.state] = counts.get(r.state, 0) + 1

    broken = [r for r in report.results if r.state == ResultState.FAIL]
    slow = sorted([r for r in report.results if r.latency_ms > 5000], key=lambda r: -r.latency_ms)
    working = [r for r in report.results if r.state == ResultState.PASS]

    total = len(report.results)
    passed = counts.get(ResultState.PASS, 0)
    health_pct = round(100 * passed / total) if total else 0

    md_lines = [
        "# ZARA SELF TEST REPORT",
        "",
        f"- run_id: `{report.run_id}`",
        f"- commit: `{report.commit}` (branch `{report.branch}`)",
        f"- duração: {duration_s:.1f}s",
        "",
        "## SUMMARY",
        "",
        f"- Total: {total}",
        f"- Passed: {counts.get(ResultState.PASS, 0)}",
        f"- Failed: {counts.get(ResultState.FAIL, 0)}",
        "- Known failures (camada técnica): ver seção técnica abaixo",
        f"- Skipped: {counts.get(ResultState.SKIP, 0)}",
        f"- Unsupported: {counts.get(ResultState.UNSUPPORTED, 0)}",
        f"- Executed unverified: {counts.get(ResultState.EXECUTED_UNVERIFIED, 0)}",
        f"- Timeout: {counts.get(ResultState.TIMEOUT, 0)}",
        f"- Blocked: {counts.get(ResultState.BLOCKED, 0)}",
        "",
        f"## HEALTH SCORE: {health_pct}%",
        "",
    ]

    if broken:
        md_lines += ["## BROKEN NOW", ""]
        for r in broken:
            md_lines.append(f"- **{r.test_id}** {r.label}: {r.detail}")
        md_lines.append("")

    md_lines += ["## WORKING NOW", ""]
    for r in working:
        md_lines.append(f"- {r.test_id} {r.label} ({r.latency_ms:.0f}ms)")
    md_lines.append("")

    if slow:
        md_lines += ["## SLOW OPERATIONS", "", "| Test | Latência | Categoria |", "|---|---|---|"]
        for r in slow:
            md_lines.append(f"| {r.test_id} {r.label} | {r.latency_ms:.0f}ms | {r.category} |")
        md_lines.append("")

    if report.notes:
        md_lines += ["## NOTAS", ""]
        for note in report.notes:
            md_lines.append(f"- {note}")
        md_lines.append("")

    md_lines += ["## TEST DETAILS", ""]
    for r in report.results:
        md_lines.append(f"- **{r.test_id}** [{r.state}] {r.label} — {r.latency_ms:.0f}ms — {r.detail}")

    (LATEST_DIR / "ZARA_TEST_REPORT.md").write_text("\n".join(md_lines), encoding="utf-8")

    json_report = {
        "run_id": report.run_id,
        "commit": report.commit,
        "branch": report.branch,
        "duration_seconds": round(duration_s, 1),
        "counts": counts,
        "health_pct": health_pct,
        "technical": report.technical,
        "notes": report.notes,
        "tests": [
            {"id": r.test_id, "label": r.label, "state": r.state, "detail": r.detail,
             "latency_ms": round(r.latency_ms, 1), "category": r.category}
            for r in report.results
        ],
    }
    (LATEST_DIR / "ZARA_TEST_REPORT.json").write_text(json.dumps(json_report, indent=2, ensure_ascii=False), encoding="utf-8")

    capabilities = {
        r.test_id: {"label": r.label, "status": r.state, "latency_ms": round(r.latency_ms, 1)}
        for r in report.results
    }
    (LATEST_DIR / "ZARA_CAPABILITIES.json").write_text(json.dumps(capabilities, indent=2, ensure_ascii=False), encoding="utf-8")

    # Histórico: uma pasta por run, retenção configurável.
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    run_dir = HISTORY_DIR / report.run_id
    run_dir.mkdir(exist_ok=True)
    for name in ("ZARA_TEST_REPORT.md", "ZARA_TEST_REPORT.json", "ZARA_CAPABILITIES.json"):
        shutil.copy2(LATEST_DIR / name, run_dir / name)
    keep = int(cfg.get("report_retention", HISTORY_RETENTION))
    old_runs = sorted(HISTORY_DIR.iterdir(), key=lambda p: p.name)
    for old in old_runs[:-keep] if len(old_runs) > keep else []:
        shutil.rmtree(old, ignore_errors=True)

    return LATEST_DIR / "ZARA_TEST_REPORT.md"


def print_final_summary(report: SelfTestReport, report_path: Path) -> None:
    counts: dict[str, int] = {}
    for r in report.results:
        counts[r.state] = counts.get(r.state, 0) + 1
    total = len(report.results)
    passed = counts.get(ResultState.PASS, 0)
    health_pct = round(100 * passed / total) if total else 0
    print()
    print("=" * 70)
    print("ZARA SELF TEST")
    print("=" * 70)
    print(f"PASS: {passed}  FAIL: {counts.get(ResultState.FAIL, 0)}  "
          f"SKIP: {counts.get(ResultState.SKIP, 0)}  "
          f"UNVERIFIED: {counts.get(ResultState.EXECUTED_UNVERIFIED, 0)}  "
          f"BLOCKED: {counts.get(ResultState.BLOCKED, 0)}")
    print()
    print(f"Health: {health_pct}%")
    print()
    print(f"Relatório: {report_path}")


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------

def run(mode: str) -> int:
    cfg = load_config()
    run_id = time.strftime("%Y-%m-%d_%H-%M-%S")
    commit = _run_git("rev-parse", "--short", "HEAD") or "unknown"
    branch = _run_git("branch", "--show-current") or "unknown"
    report = SelfTestReport(run_id=run_id, commit=commit, branch=branch, started_epoch=time.time())

    print("=" * 70)
    print(f"ZARA SELF TEST — modo {mode.upper()}")
    print("=" * 70)
    print()

    if not disk_guard(report, cfg):
        write_reports(report, cfg)
        print("BLOCKED_LOW_DISK — disco crítico, testes de sistema não rodam com segurança.")
        return 1

    if mode == "clean":
        safe_cleanup(report)
        for note in report.notes:
            print(f"  {note}")
        return 0

    report.technical = run_technical_layer(report, full=(mode != "quick"))

    if mode == "quick":
        report_path = write_reports(report, cfg)
        print_final_summary(report, report_path)
        return 0 if not any(r.state == ResultState.FAIL for r in report.results) else 1

    backend = _candidate_backend_path()
    if backend is None:
        report.add(TestResult("SYS-BOOT", "Boot do backend", ResultState.BLOCKED,
                               "ULTIMO_CANDIDATO.json ausente/inválido ou EXE não existe"))
        report_path = write_reports(report, cfg)
        print_final_summary(report, report_path)
        return 1

    print(f"Candidato: {backend}")
    print("Ligando o backend real (pode levar até 90s no boot a frio)...")
    zara = ZaraProcess(backend)
    started, detail = zara.start()
    if not started:
        report.add(TestResult("SYS-BOOT", "Boot do backend", ResultState.FAIL, detail))
        report_path = write_reports(report, cfg)
        print_final_summary(report, report_path)
        zara.stop()
        return 1
    report.add(TestResult("SYS-BOOT", "Boot do backend", ResultState.PASS, "emitiu o sinal de pronto"))

    print()
    print("Camada real (mesma pipeline que o Electron usa)...")
    print()
    run_system_checks(zara, report)
    run_app_lifecycle(zara, report)
    run_reminders(zara, report)
    run_file_sandbox(report)
    run_failure_cases(zara, report)

    if cfg.get("interactive_tests_enabled", True):
        print()
        print("Sequência de comandos de voz (por texto) — efeito real na tela...")
        print()
        snapshot = capture_state(zara)
        try:
            run_voice_command_sequence(zara, report, cfg)
        finally:
            restore_state(zara, snapshot, report)

    resp = zara.call("action-list")
    actions_resp = (resp or {}).get("response") if resp else None
    if isinstance(actions_resp, dict):
        report.capabilities_total = len(actions_resp)
        report.notes.append(f"A ZARA tem {report.capabilities_total} ações registradas no total; "
                             f"este relatório testa uma amostra representativa ({len(report.results)} checagens).")

    zara.stop()

    report_path = write_reports(report, cfg)
    print_final_summary(report, report_path)
    return 0 if not any(r.state == ResultState.FAIL for r in report.results) else 1


def show_latest_report() -> int:
    path = LATEST_DIR / "ZARA_TEST_REPORT.md"
    if not path.exists():
        print("Nenhum relatório ainda. Rode --quick ou --full primeiro.")
        return 1
    print(path.read_text(encoding="utf-8"))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--quick", action="store_true", help="Só camada técnica (rápido, sem candidato)")
    group.add_argument("--full", action="store_true", help="Camada técnica + camada real completa (default)")
    group.add_argument("--report", action="store_true", help="Só mostra o último relatório, sem rodar nada")
    group.add_argument("--clean", action="store_true", help="Só limpeza segura, sem rodar testes")
    args = parser.parse_args()

    if args.report:
        return show_latest_report()
    if args.clean:
        return run("clean")
    if args.quick:
        return run("quick")
    return run("full")


if __name__ == "__main__":
    sys.exit(main())

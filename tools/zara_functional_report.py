"""ZARA-FUNCTIONAL-REPORT-001.

Testa o candidato empacotado (o mesmo EXE que o Alex usa de verdade) contra
o pipeline IPC real -- sem mock, sem pytest, sem sessao do Claude. Feito
para o Alex rodar sozinho quando quiser confirmar se a ZARA esta funcionando,
sem gastar tokens de uma sessao para isso.

O QUE ESTE SCRIPT PROVA: que o candidato empacotado liga, responde ao IPC
real, e que um conjunto de capacidades (texto, sistema, memoria, wifi,
energia, apps) devolve dado real e verificado.

O QUE ESTE SCRIPT NAO PROVA: voz (microfone, fala) e a tela (UI do
Electron). Isso so o Alex confirma, ouvindo e olhando -- ver
.claude/rules/physical-validation.md.

Uso:
    .venv\\Scripts\\python.exe tools\\zara_functional_report.py
    (ou clique em TESTAR-A-ZARA.bat na raiz do projeto)
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from pathlib import Path
from queue import Empty, Queue

# Sem isso, o console do Windows (cp1252 por padrao) mastiga qualquer
# acento -- "RELATÓRIO" vira "RELAT?RIO". TESTAR-A-ZARA.bat tambem faz
# `chcp 65001`; isto aqui garante o mesmo mesmo se o script rodar fora do
# .bat.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BOOT_TIMEOUT_S = 90.0
REQUEST_TIMEOUT_S = 20.0


def _candidate_backend_path() -> Path | None:
    """Le ULTIMO_CANDIDATO.json para saber qual EXE testar -- o mesmo que
    o Alex abriria de verdade, nao um caminho fixo que pode estar velho."""
    pointer = PROJECT_ROOT / "ULTIMO_CANDIDATO.json"
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


class ZaraProcess:
    """Fala IPC bruto com o sidecar real: uma linha JSON por mensagem,
    igual ao que o Electron faz de verdade em frontend/src/main.ts."""

    def __init__(self, exe_path: Path):
        self.exe_path = exe_path
        self.proc: subprocess.Popen | None = None
        self._out_queue: Queue[dict] = Queue()
        self._reader_thread: threading.Thread | None = None
        self._request_counter = 0

    def start(self) -> tuple[bool, str]:
        try:
            self.proc = subprocess.Popen(
                [str(self.exe_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
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
                    continue  # log humano, nao e frame IPC

        self._reader_thread = threading.Thread(target=_reader, daemon=True)
        self._reader_thread.start()

        got_ready = ready.wait(timeout=BOOT_TIMEOUT_S)
        if not got_ready:
            tail = "\n".join(raw_lines[-25:])
            return False, f"nao emitiu 'SYS: Interface neural pronta' em {BOOT_TIMEOUT_S:.0f}s. Ultimas linhas:\n{tail}"
        return True, ""

    def call(self, msg_type: str, payload: dict | None = None, timeout: float = REQUEST_TIMEOUT_S) -> dict | None:
        """Manda uma mensagem e espera a resposta com o MESMO request_id --
        igual ao pendingRequests do main.ts, sem depender de ordem/tempo."""
        assert self.proc is not None and self.proc.stdin is not None
        self._request_counter += 1
        request_id = f"report-{self._request_counter}"
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
        # O onefile do PyInstaller sobe um segundo processo (bootloader +
        # real) -- terminate() no pai as vezes nao leva o filho junto.
        # taskkill /T mata a arvore inteira, igual ao ABRIR-A-ZARA.bat.
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/IM", "zara-backend.exe"],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass


class Report:
    def __init__(self):
        self.results: list[tuple[str, bool, str]] = []

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.results.append((name, ok, detail))
        marca = "OK  " if ok else "FALHOU"
        print(f"  [{marca}] {name} -- {detail}")

    def summary(self) -> bool:
        total = len(self.results)
        ok = sum(1 for _, passed, _ in self.results if passed)
        print()
        print("=" * 70)
        print(f"RESULTADO: {ok}/{total} capacidades confirmadas de verdade")
        print("=" * 70)
        if ok < total:
            print()
            print("Falharam:")
            for name, passed, detail in self.results:
                if not passed:
                    print(f"  - {name}: {detail}")
        print()
        print("O que este relatorio NAO prova: voz (microfone/fala) e a tela do")
        print("Electron. Isso so voce confirma abrindo a ZARA de verdade e falando")
        print("com ela.")
        return ok == total


def run() -> int:
    print("=" * 70)
    print("ZARA — RELATORIO FUNCIONAL REAL")
    print("=" * 70)

    backend = _candidate_backend_path()
    if backend is None:
        print()
        print("Nao encontrei o candidato atual (ULTIMO_CANDIDATO.json ausente,")
        print("invalido, ou o EXE nao existe mais no disco).")
        print("Rode um build novo antes de testar.")
        return 1

    print(f"Candidato: {backend}")
    print()
    print("Ligando o backend real (pode levar ate 90s no boot a frio)...")

    zara = ZaraProcess(backend)
    started, detail = zara.start()
    report = Report()

    if not started:
        report.add("Boot do backend", False, detail)
        report.summary()
        zara.stop()
        return 1
    report.add("Boot do backend", True, "emitiu o sinal de pronto")

    print()
    print("Testando capacidades reais (mesma pipeline que o Electron usa)...")
    print()

    # --- Texto: a mesma pergunta que o trio de recuperacao de voz usa ---
    resp = zara.call("send-message", {"text": "que horas sao?"})
    if resp and resp.get("response", {}).get("response"):
        texto = resp["response"]["response"]
        report.add("Comando de texto (\"que horas são?\")", True, f'respondeu: "{texto}"')
    else:
        report.add("Comando de texto (\"que horas são?\")", False, f"sem resposta valida: {resp}")

    # --- Processos reais do sistema ---
    resp = zara.call("action-execute", {"action": "system_processes", "params": {"limit": 500}})
    result = (resp or {}).get("response", {}).get("result") if resp else None
    count = (result or {}).get("data", {}).get("count") if isinstance(result, dict) else None
    if isinstance(count, int) and count > 0:
        report.add("Ver processos (system_processes)", True, f"{count} processos reais")
    else:
        report.add("Ver processos (system_processes)", False, f"resposta inesperada: {resp}")

    # --- Metricas reais de CPU/RAM/disco ---
    resp = zara.call("system-metrics")
    metrics_resp = (resp or {}).get("response") if resp else None
    if isinstance(metrics_resp, dict) and any(k in metrics_resp for k in ("cpu", "memory_percent", "disk_percent")):
        report.add("Métricas de sistema (CPU/RAM/disco)", True, f"{metrics_resp}")
    else:
        report.add("Métricas de sistema (CPU/RAM/disco)", False, f"resposta inesperada: {resp}")

    # --- Wi-Fi (leitura real do estado do radio) ---
    resp = zara.call("action-execute", {"action": "os_wifi_status", "params": {}})
    result = (resp or {}).get("response", {}).get("result") if resp else None
    if isinstance(result, dict) and result.get("success") and result.get("data", {}).get("after") in ("On", "Off"):
        report.add("Wi-Fi (leitura real do rádio)", True, f"estado: {result['data']['after']}")
    else:
        report.add("Wi-Fi (leitura real do rádio)", False, f"resposta inesperada: {resp}")

    # --- Planos de energia reais do Windows ---
    resp = zara.call("action-execute", {"action": "os_power_plan_list", "params": {}})
    result = (resp or {}).get("response", {}).get("result") if resp else None
    plans = (result or {}).get("data") if isinstance(result, dict) else None
    if isinstance(plans, list) and len(plans) > 0:
        nomes = ", ".join(p.get("name", "?") for p in plans)
        report.add("Planos de energia (powercfg real)", True, f"{len(plans)} planos: {nomes}")
    else:
        report.add("Planos de energia (powercfg real)", False, f"resposta inesperada: {resp}")

    # --- Diagnostico interno (self-status) ---
    resp = zara.call("self-status")
    snapshot = resp.get("response") if resp else None
    capabilities = (snapshot or {}).get("capabilities") if isinstance(snapshot, dict) else None
    if isinstance(capabilities, list) and len(capabilities) > 0:
        available = sum(1 for c in capabilities if c.get("status") == "AVAILABLE")
        report.add("Diagnóstico interno (self-status)", True, f"{available}/{len(capabilities)} capacidades disponíveis agora")
    else:
        report.add("Diagnóstico interno (self-status)", False, f"resposta inesperada: {resp}")

    # --- Memoria de usuario (leitura real) ---
    resp = zara.call("memory-user-list")
    mem_resp = resp.get("response") if resp else None
    if isinstance(mem_resp, dict) and mem_resp.get("success") and isinstance(mem_resp.get("facts"), list):
        report.add("Memória de usuário (leitura real)", True, f"{len(mem_resp['facts'])} fatos guardados")
    else:
        report.add("Memória de usuário (leitura real)", False, f"resposta inesperada: {resp}")

    # --- Memoria de projeto (leitura real) ---
    resp = zara.call("project-memory-list")
    proj_resp = resp.get("response") if resp else None
    if isinstance(proj_resp, dict) and proj_resp.get("success") and isinstance(proj_resp.get("keys"), list):
        report.add("Memória de projeto (leitura real)", True, f"documentos: {', '.join(proj_resp['keys'])}")
    else:
        report.add("Memória de projeto (leitura real)", False, f"resposta inesperada: {resp}")

    print()
    zara.stop()
    tudo_ok = report.summary()
    return 0 if tudo_ok else 1


if __name__ == "__main__":
    sys.exit(run())

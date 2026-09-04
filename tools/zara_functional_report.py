"""ZARA-FUNCTIONAL-REPORT-001.

Testa o candidato empacotado (o mesmo EXE que o Alex usa de verdade) contra
o pipeline IPC real -- sem mock, sem pytest, sem sessao do Claude. Feito
para o Alex rodar sozinho quando quiser confirmar se a ZARA esta funcionando,
sem gastar tokens de uma sessao para isso.

O QUE ESTE SCRIPT PROVA: que o candidato empacotado liga, responde ao IPC
real, que um conjunto de capacidades (texto, sistema, memoria, wifi,
energia, apps) devolve dado real e verificado, E que uma sequência de
comandos de voz (navegador, YouTube, Spotify, volume, brilho, janelas)
enviados por TEXTO -- mesma cadeia que a voz usa de verdade
(handle_send_message) -- executa e responde, com o tempo real de cada
resposta medido.

O QUE ESTE SCRIPT NAO PROVA: voz (microfone, fala) e a tela (UI do
Electron). Isso so o Alex confirma, ouvindo e olhando -- ver
.claude/rules/physical-validation.md.

AVISO: a sequência de comandos de voz tem efeito REAL na tela (abre
navegador, toca áudio, muda volume/brilho de verdade).

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

    def say(self, texto: str, timeout: float = REQUEST_TIMEOUT_S) -> tuple[dict | None, float]:
        """Manda um comando de TEXTO como se fosse falado -- mesma cadeia que
        a voz usa de verdade (handle_send_message), não action-execute
        direto. Devolve (resposta, latência em ms) para o relatório medir
        tempo real de resposta, não só se funcionou."""
        inicio = time.perf_counter()
        resp = self.call("send-message", {"text": texto}, timeout=timeout)
        latencia_ms = (time.perf_counter() - inicio) * 1000
        return resp, latencia_ms

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
        self.voice_steps: list[tuple[str, str, str, float]] = []  # comando, engine, resposta, latencia_ms

    def add(self, name: str, ok: bool, detail: str) -> None:
        self.results.append((name, ok, detail))
        marca = "OK  " if ok else "FALHOU"
        print(f"  [{marca}] {name} -- {detail}")

    def add_voice_step(self, comando: str, engine: str, resposta: str, latencia_ms: float) -> None:
        self.voice_steps.append((comando, engine, resposta, latencia_ms))
        reconhecido = "reconhecido como comando" if engine == "pc_control" else f"caiu em '{engine}'"
        print(f'  "{comando}"')
        print(f"    -> {reconhecido}, {latencia_ms:.0f}ms")
        print(f'    -> resposta: "{resposta}"')

    def voice_summary(self) -> None:
        if not self.voice_steps:
            return
        print()
        print("-" * 70)
        print("LATÊNCIA DOS COMANDOS DE VOZ (enviados por texto, mesma cadeia da voz)")
        print("-" * 70)
        tempos = [latencia for _, _, _, latencia in self.voice_steps]
        media = sum(tempos) / len(tempos)
        pior_comando, pior_engine, _, pior_tempo = max(self.voice_steps, key=lambda s: s[3])
        reconhecidos = sum(1 for _, engine, _, _ in self.voice_steps if engine == "pc_control")
        falhou_execucao = sum(1 for _, _, resposta, _ in self.voice_steps if "Não consegui executar" in resposta)
        print(f"  {reconhecidos}/{len(self.voice_steps)} comandos reconhecidos como ação direta (engine=pc_control)")
        print(f"  {falhou_execucao}/{len(self.voice_steps)} reconhecidos MAS a execução falhou (ver \"Não consegui")
        print("  executar\" em cada resposta acima -- a ação real não aconteceu, mesmo com o")
        print("  comando entendido).")
        print(f"  Latência média: {media:.0f}ms | Mais lento: \"{pior_comando}\" ({pior_tempo:.0f}ms, engine={pior_engine})")
        if pior_tempo > 5000:
            print(f"  ATENÇÃO: \"{pior_comando}\" levou mais de 5s -- vale investigar por que.")
        print()
        print("  Nota: comandos NÃO reconhecidos como pc_control (ex.: caíram em raciocínio")
        print("  livre/LLM) tendem a ser mais lentos por natureza -- isso sozinho não é bug,")
        print("  mas se um comando que deveria ser direto (ex. \"diminui o volume\") aparecer")
        print("  aqui, é sinal de regressão no reconhecimento de intenção.")
        print()
        print("  Nota 2: falhas em comandos ligados ao YouTube (tocar, pular anúncio, pausar,")
        print("  continuar) podem ser o navegador não ter tido tempo real de carregar a")
        print("  página entre um comando e o outro, não necessariamente um bug -- reveja as")
        print("  respostas com atenção antes de assumir regressão.")

    def summary(self) -> bool:
        total = len(self.results)
        ok = sum(1 for _, passed, _ in self.results if passed)
        print()
        print("=" * 70)
        print(f"RESULTADO: {ok}/{total} checagens da amostra confirmadas de verdade")
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
    print()
    print("Este relatório tem efeito REAL na tela: abre navegador, toca áudio,")
    print("muda volume e brilho de verdade. Não é simulação.")

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

    # --- Volume/audio (leitura real, sem mudar nada) ---
    resp = zara.call("action-execute", {"action": "audio_status", "params": {}})
    result = (resp or {}).get("response", {}).get("result") if resp else None
    if isinstance(result, dict) and result.get("success"):
        report.add("Áudio (leitura real do volume)", True, f"{result.get('output', '')}")
    else:
        report.add("Áudio (leitura real do volume)", False, f"resposta inesperada: {resp}")

    # --- Abrir app real (Bloco de Notas) e fechar de novo, verificando os dois lados ---
    resp = zara.call("action-execute", {"action": "os_app", "params": {"app": "notepad"}})
    result = (resp or {}).get("response", {}).get("result") if resp else None
    data = (result or {}).get("data") if isinstance(result, dict) else None
    if isinstance(result, dict) and result.get("success") and data and data.get("verified"):
        pid = data.get("window_pid")
        report.add("Abrir app real (Bloco de Notas)", True, f"PID {pid}, janela verificada")
        if pid:
            try:
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, timeout=10)
            except Exception:
                pass
    else:
        report.add("Abrir app real (Bloco de Notas)", False, f"resposta inesperada: {resp}")

    # --- Lembrete real: cria, confere que existe, cancela (nao deixa lixo) ---
    due_at = time.time() + 3600
    resp = zara.call("reminder-create", {"text": "teste automatico do relatorio", "due_at": due_at, "timezone": "local"})
    create_resp = resp.get("response") if resp else None
    reminder_id = create_resp.get("id") if isinstance(create_resp, dict) else None
    if isinstance(create_resp, dict) and create_resp.get("success") and reminder_id:
        report.add("Lembretes (criar)", True, f"id {reminder_id}")
        cancel_resp = zara.call("reminder-cancel", {"id": reminder_id})
        cancelled = (cancel_resp or {}).get("response", {}).get("success") if cancel_resp else False
        report.add("Lembretes (cancelar, limpa o teste)", bool(cancelled), f"resposta: {cancel_resp}")
    else:
        report.add("Lembretes (criar)", False, f"resposta inesperada: {resp}")

    # --- Sequencia de comandos de voz, enviados por TEXTO (mesma cadeia que
    # a voz usa de verdade: handle_send_message -> _try_pc_intent -> action).
    # Pedido do Alex: testar o que a ZARA fazia por voz -- navegador, YouTube,
    # Spotify, volume, brilho, janelas -- sem precisar falar, e medir o tempo
    # de resposta de cada um. ISSO TEM EFEITO REAL NA TELA: abre navegador,
    # toca audio, muda volume/brilho de verdade.
    print()
    print("=" * 70)
    print("SEQUÊNCIA DE COMANDOS DE VOZ (por texto) — efeito real na tela")
    print("=" * 70)
    print()
    # (comando, segundos de espera DEPOIS dele antes do proximo -- YouTube
    # precisa de tempo de carregamento de pagina de verdade; sem isso, o
    # proximo comando (ex. "toca hans zimmer") roda antes da pagina existir
    # e falha por timing, nao por bug real. Comandos instantaneos (volume,
    # brilho, minimizar) nao precisam de espera longa.
    comandos = [
        ("abre o youtube", 4.0),
        ("pesquisa hans zimmer no youtube", 4.0),
        ("toca hans zimmer", 3.0),
        ("pula o anuncio", 1.0),
        ("diminui o volume", 0.5),
        ("diminui o brilho", 0.5),
        ("pula essa", 2.0),
        ("pausa", 1.0),
        ("continua", 1.0),
        ("abre o spotify", 2.0),
        ("minimiza", 0.5),
        ("foca no chrome", 0.5),
        ("abre o chrome no perfil trabalho", 0.5),
    ]
    for comando, espera_depois in comandos:
        resp, latencia_ms = zara.say(comando, timeout=25.0)
        response_obj = (resp or {}).get("response") if resp else None
        engine = response_obj.get("engine", "sem resposta") if isinstance(response_obj, dict) else "sem resposta"
        texto_resposta = response_obj.get("response", "") if isinstance(response_obj, dict) else str(resp)
        report.add_voice_step(comando, engine, texto_resposta, latencia_ms)
        time.sleep(espera_depois)

    report.voice_summary()

    # --- Inventario real de actions -- contexto de escala, nao pass/fail ---
    resp = zara.call("action-list")
    actions_resp = resp.get("response") if resp else None
    total_actions = len(actions_resp) if isinstance(actions_resp, dict) else None

    print()
    zara.stop()
    if total_actions:
        print(f"Nota: a ZARA tem {total_actions} ações registradas no total.")
        print(f"Este relatório testa uma AMOSTRA representativa ({len(report.results)} checagens),")
        print("não é a lista completa do que ela sabe fazer.")
        print()
    tudo_ok = report.summary()
    return 0 if tudo_ok else 1


if __name__ == "__main__":
    sys.exit(run())

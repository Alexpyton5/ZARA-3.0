# -*- coding: utf-8 -*-
"""ZARA Auto-Suite — a suite que se testa sozinha.

Roda via Agendador de Tarefas do Windows (a cada 6h), sem ninguem olhando.
So GRITA (escreve AUTO-SUITE-ALERTA.md na ZOE-INBOX) quando aparece uma
falha NOVA em relacao ao baseline. Falha antiga conhecida nao gera alerta.

Autor: zoe — 28/09/2026. Logica pura, so stdlib, custo zero.
"""
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ZARA_TESTS = PROJECT_ROOT / ".zara-tests"
RUNS_DIR = ZARA_TESTS / "runs"
BASELINE_FILE = ZARA_TESTS / "auto_suite_baseline.json"
LOG_FILE = ZARA_TESTS / "auto_suite.log"
INBOX = PROJECT_ROOT / "ZOE-INBOX"
ALERT_FILE = INBOX / "AUTO-SUITE-ALERTA.md"
VALIDATOR = PROJECT_ROOT / "tools" / "zara_validate.py"


def agora():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def registrar(msg):
    linha = f"[{agora()}] {msg}"
    print(linha, flush=True)
    ZARA_TESTS.mkdir(exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(linha + "\n")


def carregar_baseline():
    try:
        dados = json.loads(BASELINE_FILE.read_text(encoding="utf-8"))
        return set(dados.get("failed", []))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def salvar_baseline(failed):
    BASELINE_FILE.write_text(
        json.dumps({"failed": sorted(failed), "updated": agora()}, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )


def pastas_runs():
    if not RUNS_DIR.is_dir():
        return set()
    return set(p.name for p in RUNS_DIR.iterdir() if p.is_dir())


def resumo_da_rodada(pastas_antes):
    """Le o summary.json da pasta de run criada NESTA rodada (ignora antigas)."""
    novas = sorted(pastas_runs() - pastas_antes)
    for nome in reversed(novas):
        arq = RUNS_DIR / nome / "summary.json"
        if arq.exists():
            try:
                return json.loads(arq.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
    return None


def extrair_falhas(resumo):
    """Acha os IDs dos testes que falharam, tolerando formatos diferentes.

    Retorna: lista de IDs, [] se a rodada foi verde, ou None se ilegivel.
    Erros de coleta ("N errors" na summary_line) tornam o resumo ilegivel:
    nao da para enumerar o que quebrou, entao nao se finge que esta verde.
    """
    if not isinstance(resumo, dict):
        return None
    res = resumo.get("result")
    if isinstance(res, dict):
        resumo = res
    ids = []
    for chave in ("failed_tests", "failures", "failed"):
        val = resumo.get(chave)
        if isinstance(val, list):
            for item in val:
                if isinstance(item, str):
                    ids.append(item)
                elif isinstance(item, dict):
                    ids.append(item.get("nodeid") or item.get("id") or item.get("name") or str(item))
            break
    linha = str(resumo.get("summary_line", ""))
    m = re.search(r"(\d+)\s+errors?", linha)
    if m and int(m.group(1)) > 0:
        return None
    for chave_num in ("failed", "failed_count", "n_failed"):
        n = resumo.get(chave_num)
        if isinstance(n, int) and n > len(ids):
            return None
    return ids


def escrever_alerta(novas, total_falhas, detalhe_extra=""):
    INBOX.mkdir(exist_ok=True)
    linhas = [
        "# ALERTA AUTO-SUITE — falha NOVA detectada",
        f"- Quando: {agora()}",
        f"- Falhas novas: {len(novas)} (total com falha: {total_falhas})",
        "",
    ]
    for nid in sorted(novas)[:20]:
        linhas.append(f"- {nid}")
    if len(novas) > 20:
        linhas.append(f"- ... e mais {len(novas) - 20}")
    if detalhe_extra:
        linhas += ["", detalhe_extra]
    linhas += ["", "A zoe e o Codex verificam em paralelo, sem parar a obra."]
    ALERT_FILE.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def main():
    pastas_antes = pastas_runs()
    registrar("inicio da rodada automatica")
    try:
        proc = subprocess.run(
            [sys.executable, str(VALIDATOR), "--full"],
            cwd=str(PROJECT_ROOT),
            capture_output=True, text=True, timeout=3600,
        )
        ok = proc.returncode == 0
    except Exception as e:
        registrar(f"ERRO: validador nao executou: {e}")
        escrever_alerta(set(), 0, f"O validador nem executou: {e}. Ver o log.")
        return 2

    baseline = carregar_baseline()
    resumo = resumo_da_rodada(pastas_antes)
    falhas = extrair_falhas(resumo)
    if falhas == [] and not ok:
        falhas = None  # exit != 0 mas sem falhas enumeraveis: ilegivel, nao verde

    if baseline is None:
        if ok and falhas is not None:
            salvar_baseline(set(falhas))
            registrar(f"baseline inicial criado (exit={proc.returncode}, falhas={len(falhas)})")
            return 0
        registrar(f"ERRO: primeira rodada nao limpa (exit={proc.returncode}) — baseline NAO criado")
        escrever_alerta(set(), -1, f"A primeira rodada da auto-suite nao foi limpa (exit={proc.returncode}). Ver o log da rodada; baseline nao criado para nao mascarar o estado real.")
        return 1

    if falhas is None:
        if not ok:
            registrar("suite vermelha, detalhe ilegivel — alerta generico")
            escrever_alerta(set(), -1, "Nao consegui ler o summary.json; ver o log da rodada.")
            return 1
        registrar("suite verde (detalhe ilegivel, exit 0)")
        return 0

    falhas_set = set(falhas)
    novas = falhas_set - baseline
    if novas:
        registrar(f"FALHAS NOVAS: {len(novas)}")
        escrever_alerta(novas, len(falhas_set))
        return 1
    corrigidas = baseline - falhas_set
    if corrigidas:
        salvar_baseline(falhas_set)
        registrar(f"ok; {len(corrigidas)} falha(s) antiga(s) sumiram, baseline atualizado")
    else:
        registrar(f"ok; sem falhas novas (total com falha: {len(falhas_set)})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

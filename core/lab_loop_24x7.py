# -*- coding: utf-8 -*-
"""ZARA Lab 24/7 — o processo que mantem o Lab vivo sozinho.

MISSAO GAP-ZERO, frente 5 ("Loop 24/7 do Lab nao roda continuo").
Processo de longa duracao: a cada ciclo aprova o topo da fila, executa
UM ciclo do Lab Vivo (backlog + turno + worker local), escreve o
heartbeat em .lab-vivo/heartbeat-24x7.json e dorme ate o proximo ciclo.

Garantias:
- Custo zero: so stdlib + as pecas do Lab (nada de rede, nada de API paga).
- Trava do supercerebro: intocada — este modulo nem importa o assunto.
- Parada elegante: criar o arquivo .lab-vivo/PARAR -> sai com codigo 0
  (o supervisor respeita e NAO relanca).
- Se o ciclo quebrar feio 3 vezes seguidas, sai com codigo 2 para o
  supervisor relancar do zero (auto-recuperacao).

Uso (a partir da raiz do projeto):
    .venv\\Scripts\\python.exe -m core.lab_loop_24x7

Env:
    ZARA_LAB24_CICLO_MIN  minutos entre ciclos (padrao 15)
    ZARA_LAB24_BUDGET     orcamento contabil por ciclo (padrao 1.0)
    ZARA_LAB24_RAIZ       raiz do projeto (padrao: detectada do modulo)
    ZARA_LAB24_MAX_CICLOS para apos N ciclos (uso dos testes; vazio = infinito)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path

HEARTBEAT_NOME = "heartbeat-24x7.json"
PARAR_NOME = "PARAR"
LOG_DIR_NOME = "logs"
MAX_FALHAS_SEGUIDAS = 3
VERSAO = 1


def raiz_projeto() -> Path:
    override = os.environ.get("ZARA_LAB24_RAIZ")
    if override:
        return Path(override)
    # core/lab_loop_24x7.py -> a raiz e o pai do pai
    return Path(__file__).resolve().parents[1]


def ciclo_minutos() -> float:
    try:
        return max(1.0, float(os.environ.get("ZARA_LAB24_CICLO_MIN", "15")))
    except (TypeError, ValueError):
        return 15.0


def budget_ciclo() -> float:
    try:
        return max(0.0, float(os.environ.get("ZARA_LAB24_BUDGET", "1.0")))
    except (TypeError, ValueError):
        return 1.0


def max_ciclos() -> int:
    try:
        return max(0, int(os.environ.get("ZARA_LAB24_MAX_CICLOS", "0") or "0"))
    except (TypeError, ValueError):
        return 0


def _agora_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def escrever_heartbeat(estado_dir: Path, pid: int, ciclo: int,
                       estado: str, detalhe: str = "") -> Path:
    """Grava o heartbeat de forma atomica (o supervisor nunca le meio-arquivo)."""
    arq = estado_dir / HEARTBEAT_NOME
    tmp = arq.with_suffix(".tmp")
    payload = {
        "viva": True,
        "ts": time.time(),
        "ts_iso": _agora_iso(),
        "pid": pid,
        "ciclo": ciclo,
        "estado": estado,
        "detalhe": (detalhe or "")[:200],
        "versao": VERSAO,
    }
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, arq)
    return arq


def parar_pedido(estado_dir: Path) -> bool:
    return (estado_dir / PARAR_NOME).exists()


def configurar_log(estado_dir: Path) -> logging.Logger:
    log_dir = estado_dir / LOG_DIR_NOME
    log_dir.mkdir(parents=True, exist_ok=True)
    arq = log_dir / ("lab24x7-%s.log" % datetime.now().strftime("%Y%m%d"))
    logger = logging.getLogger("lab24x7")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(arq, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(fh)
    return logger


def dormir_com_parada(segundos: float, estado_dir: Path) -> bool:
    """Dorme em fatias de 5s; devolve True se o arquivo PARAR apareceu."""
    fim = time.monotonic() + segundos
    while True:
        if parar_pedido(estado_dir):
            return True
        restante = fim - time.monotonic()
        if restante <= 0:
            return False
        time.sleep(min(5.0, restante))


def main() -> int:
    raiz = raiz_projeto()
    estado_dir = raiz / ".lab-vivo"
    estado_dir.mkdir(parents=True, exist_ok=True)
    log = configurar_log(estado_dir)
    pid = os.getpid()

    if str(raiz) not in sys.path:
        sys.path.insert(0, str(raiz))
    from core.lab_vivo import LabVivo
    from core.lab_workers import worker_vivo_factory

    vivo = LabVivo(raiz)
    vivo.preparar()
    # worker proprio via factory publica (mesmo comportamento do LabVivo,
    # sem encostar em atributo privado)
    worker = worker_vivo_factory(vivo.dir_work, vivo.backlog)

    intervalo_s = ciclo_minutos() * 60.0
    orcamento = budget_ciclo()
    teto = max_ciclos()

    log.info("daemon 24/7 iniciado pid=%s ciclo_min=%.1f teto_ciclos=%s",
             pid, intervalo_s / 60.0, teto or "infinito")
    escrever_heartbeat(estado_dir, pid, 0, "INICIANDO")

    ciclo = 0
    falhas_seguidas = 0
    while True:
        if parar_pedido(estado_dir):
            log.info("PARAR encontrado: saindo com elegancia")
            escrever_heartbeat(estado_dir, pid, ciclo, "PARADO",
                               "parada pedida via arquivo PARAR")
            return 0
        ciclo += 1
        escrever_heartbeat(estado_dir, pid, ciclo, "RODANDO")
        try:
            aprovado = vivo.aprovar_topo()
            rel = vivo.loop.run_cycle(
                backlog=vivo.backlog, dropbox=vivo.caixinha,
                worker=worker, budget_usd=orcamento,
                max_turns=10, max_per_seat=2, max_splits=3)
            vivo.salvar_backlog()
            falhas_seguidas = 0
            resumo = ("ciclo=%d idle=%s despachados=%d concluidos=%d "
                      "falhas=%d motivo=%s" % (
                          rel.cycle, rel.idle, rel.dispatched,
                          rel.completed, rel.failed, rel.idle_reason))
            log.info("ciclo %d ok: %s (aprovado=%s)", ciclo, resumo,
                     aprovado.item_id if aprovado else None)
            escrever_heartbeat(estado_dir, pid, ciclo, "RODANDO", resumo)
        except Exception as exc:  # nunca morrer calado no meio de um ciclo
            falhas_seguidas += 1
            log.exception("ciclo %d quebrou (%d/%d)", ciclo,
                          falhas_seguidas, MAX_FALHAS_SEGUIDAS)
            escrever_heartbeat(estado_dir, pid, ciclo, "ERRO",
                               "%s: %s" % (type(exc).__name__, exc))
            if falhas_seguidas >= MAX_FALHAS_SEGUIDAS:
                log.error("falhas seguidas demais: saindo p/ supervisor relancar")
                return 2
        if teto and ciclo >= teto:
            log.info("teto de %d ciclos atingido: saindo", teto)
            escrever_heartbeat(estado_dir, pid, ciclo, "PARADO",
                               "teto de ciclos atingido (ZARA_LAB24_MAX_CICLOS)")
            return 0
        if dormir_com_parada(intervalo_s, estado_dir):
            log.info("PARAR encontrado durante o descanso: saindo")
            escrever_heartbeat(estado_dir, pid, ciclo, "PARADO",
                               "parada pedida via arquivo PARAR")
            return 0


if __name__ == "__main__":
    raise SystemExit(main())

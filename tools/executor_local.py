#!/usr/bin/env python3
"""ZARA 3.0 — executor local. A ponte entre o Mentor e o Windows do Alex.

PROBLEMA QUE RESOLVE
O terminal do Mentor roda Linux isolado: le e edita a pasta do projeto, mas nao
executa nada no Windows. Ate agora cada acao virava um .bat novo para o Alex
clicar. Isso encheu a pasta, gastou tempo dele e queimou tokens.

COMO FUNCIONA
Este processo fica aberto observando `.zara-dev/fila/`. O Mentor escreve um
pedido em JSON; o executor roda, grava a saida em `.zara-dev/fila/resultados/`
e o Mentor le. Sem .bat novo, sem clique, sem espera.

SEGURANCA — o ponto que torna isto aceitavel
NAO existe shell livre. So rodam as tarefas NOMEADAS abaixo, cada uma com a
linha de comando fixa no proprio codigo. Um pedido com qualquer outro nome e
recusado e registrado. O Mentor nao pode inventar comando: pode apenas escolher
um desta lista, que o Alex consegue ler e auditar.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILA = ROOT / ".zara-dev" / "fila"
RESULTADOS = FILA / "resultados"
PY = sys.executable

# Unicas tarefas executaveis. Linha de comando fixa: o pedido escolhe o nome,
# nunca os argumentos.
TAREFAS: dict[str, tuple[list[str], str]] = {
    "testes":      ([PY, "-m", "pytest", "-q"],                          "roda os 641 testes"),
    "auditoria":   ([PY, "tools/auditar_compreensao.py"],                "mede a compreensao de fala"),
    "ambiente":    ([PY, "tools/fix_pydantic.py"],                       "confere o ambiente Python"),
    "compilar":    ([PY, "build_exe.py"],                                "compila o backend"),
    "montar":      ([PY, "tools/build_candidate.py", "--base", "auto", "--tag", "kore"], "monta a versao nova"),
    "provar_voz":  ([PY, "tools/probe_voice.py"],                        "confirma se a voz Kore sobe"),
    "limpar":      ([PY, "tools/limpar_pasta.py", "--auto"],             "limpa a pasta"),
    "lembretes":   ([PY, "tools/lembretes.py"],                          "lista os lembretes"),
    "limpar_lembretes": ([PY, "tools/lembretes.py", "--limpar"],         "apaga lembretes ja resolvidos"),
    "fechar_zara": (["taskkill", "/F", "/IM", "ZARA 3.0.exe"],           "fecha a ZARA"),
    "fechar_backend": (["taskkill", "/F", "/IM", "zara-backend.exe"],    "fecha o backend"),
    "processos":   (["tasklist"],                                        "lista processos"),
    "abrir_zara":  ([],                                                  "abre a versao atual"),
    "git_status":  (["git", "status", "--porcelain"],                    "estado do repositorio"),
    "git_salvar":  ([],                                                  "salva o trabalho no git"),
}

TIMEOUT_PADRAO = 1800  # 30 min: o build e demorado


def agora() -> str:
    return datetime.now().strftime("%H:%M:%S")


def caminho_do_exe() -> str | None:
    try:
        return json.loads((ROOT / "ULTIMO_CANDIDATO.json").read_text(encoding="utf-8"))["EXE_PATH"]
    except Exception:
        return None


def executar(nome: str, extra: list[str] | None) -> dict:
    if nome not in TAREFAS:
        return {"ok": False, "saida": f"tarefa nao permitida: {nome}",
                "permitidas": sorted(TAREFAS)}

    cmd, _ = TAREFAS[nome]

    if nome == "abrir_zara":
        exe = caminho_do_exe()
        if not exe or not Path(exe).exists():
            return {"ok": False, "saida": "nao encontrei a versao atual do aplicativo"}
        subprocess.run(["taskkill", "/F", "/IM", "ZARA 3.0.exe"], capture_output=True)
        subprocess.run(["taskkill", "/F", "/IM", "zara-backend.exe"], capture_output=True)
        time.sleep(3)
        subprocess.Popen([exe], cwd=str(Path(exe).parent))
        time.sleep(12)
        r = subprocess.run(["tasklist", "/fi", "imagename eq ZARA 3.0.exe"],
                           capture_output=True, text=True, errors="replace")
        aberto = "ZARA 3.0.exe" in (r.stdout or "")
        return {"ok": aberto,
                "saida": f"{'A ZARA ABRIU' if aberto else 'A ZARA NAO ABRIU'}\n{exe}"}

    if nome == "git_salvar":
        msg = (extra or ["checkpoint automatico do Mentor"])[0]
        subprocess.run(["git", "add", "-A", "--",
                        "core", "tests", "tools", "memory", "integrations",
                        "frontend/src", "frontend/tests", "main.py", "build_exe.py",
                        ".claude", "docs", "CLAUDE.md", ".gitignore"],
                       cwd=str(ROOT), capture_output=True)
        r = subprocess.run(["git", "commit", "-m", msg], cwd=str(ROOT),
                           capture_output=True, text=True, errors="replace")
        return {"ok": r.returncode == 0, "saida": (r.stdout or "") + (r.stderr or "")}

    try:
        r = subprocess.run(cmd + (extra or []), cwd=str(ROOT), capture_output=True,
                           text=True, errors="replace", timeout=TIMEOUT_PADRAO)
        return {"ok": r.returncode == 0,
                "codigo": r.returncode,
                "saida": ((r.stdout or "") + (r.stderr or ""))[-40000:]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "saida": f"tempo esgotado ({TIMEOUT_PADRAO}s)"}
    except Exception as exc:
        return {"ok": False, "saida": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    FILA.mkdir(parents=True, exist_ok=True)
    RESULTADOS.mkdir(parents=True, exist_ok=True)

    print("=" * 66)
    print("  EXECUTOR DA ZARA — ligado")
    print("=" * 66)
    print("\n  Deixe esta janela aberta e minimizada.")
    print("  Enquanto ela estiver aberta, o Mentor executa sozinho:")
    print("  testar, compilar, montar versao, abrir a ZARA, limpar.\n")
    print("  Para desligar, feche a janela.\n")
    print(f"  {len(TAREFAS)} tarefas permitidas. Nenhum outro comando roda.")
    print("=" * 66 + "\n")

    vistos: set[str] = set()
    while True:
        try:
            for pedido in sorted(FILA.glob("*.json")):
                if pedido.name in vistos:
                    continue
                vistos.add(pedido.name)
                try:
                    dados = json.loads(pedido.read_text(encoding="utf-8"))
                except Exception:
                    continue
                nome = str(dados.get("tarefa") or "")
                extra = dados.get("extra") or None
                desc = TAREFAS.get(nome, ([], "?"))[1]
                print(f"[{agora()}] {nome}  ({desc})")

                inicio = time.time()
                res = executar(nome, extra)
                res["tarefa"] = nome
                res["segundos"] = round(time.time() - inicio, 1)
                res["quando"] = datetime.now().isoformat()

                saida = RESULTADOS / pedido.name
                saida.write_text(json.dumps(res, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
                try:
                    pedido.unlink()
                except Exception:
                    pass
                estado = "ok" if res.get("ok") else "FALHOU"
                print(f"[{agora()}] {nome} -> {estado} em {res['segundos']}s\n")
            time.sleep(2)
        except KeyboardInterrupt:
            print("\nExecutor desligado.")
            return 0
        except Exception as exc:
            print(f"[{agora()}] erro no laco: {exc}")
            time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main())

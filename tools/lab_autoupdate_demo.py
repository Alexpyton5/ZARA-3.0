# -*- coding: utf-8 -*-
"""Demonstração do autoupdate seguro — Fase C da GIGANTE 2 "LAB VIVO".

Duas provas reais contra um diretório-alvo de verdade (.lab-vivo/sandbox-alvo)
contendo um módulo Python de verdade. O GATE é o pytest rodando DE VERDADE
sobre o código atualizado (subprocesso, como a suíte real faria):

  1. SABOTAGEM: plano com erro de sintaxe -> pytest fica vermelho ->
     NADA publica e o rollback é provado por hash (hash depois == snapshot).
  2. UPDATE BOM: plano íntegro -> pytest verde -> publica de verdade.

Mecânica idêntica à produção; o alvo é um sandbox para risco zero ao app.

Uso (na raiz do app):
    .\\.venv\\Scripts\\python.exe tools\\lab_autoupdate_demo.py
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.lab_autoupdate import AutoupdatePipeline  # noqa: E402

MOD_OK_V1 = 'def ola():\n    return "ola v1"\n'
MOD_OK_V2 = 'def ola():\n    return "ola v2"\n'
MOD_QUEBRADO = 'def ola(:\n    return <<<quebrado!!!\n'
TESTE = ('def test_ola():\n'
         '    from saudacao import ola\n'
         '    assert ola().startswith("ola")\n')


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def montar(raiz: Path, python: str):
    alvo = raiz / ".lab-vivo" / "sandbox-alvo"
    alvo.mkdir(parents=True, exist_ok=True)
    (alvo / "saudacao.py").write_text(MOD_OK_V1, encoding="utf-8")
    (alvo / "test_saudacao.py").write_text(TESTE, encoding="utf-8")
    plano_atual: dict = {}

    def ler(caminho):
        p = alvo / caminho
        return p.read_text(encoding="utf-8") if p.exists() else None

    def aplicar(caminho, conteudo):
        (alvo / caminho).write_text(conteudo, encoding="utf-8")

    def remover(caminho):
        p = alvo / caminho
        if p.exists():
            p.unlink()

    def gate():
        """O gate de verdade: pytest sobre o código recém-aplicado."""
        env = dict(os.environ)
        env["PYTHONPATH"] = str(alvo) + os.pathsep + env.get("PYTHONPATH", "")
        proc = subprocess.run(
            [python, "-m", "pytest", str(alvo), "-q", "-p", "no:cacheprovider"],
            capture_output=True, text=True, timeout=120, env=env,
            cwd=str(alvo))
        ok = proc.returncode == 0
        detalhe = (proc.stdout + proc.stderr).strip().splitlines()
        detalhe = "\n".join(detalhe[-3:]) if detalhe else "(sem saída)"
        return ok, f"pytest no sandbox: {'VERDE' if ok else 'VERMELHO'}\n{detalhe}"

    def publicar(_rel):
        pub = raiz / ".lab-vivo" / "publicado"
        pub.mkdir(parents=True, exist_ok=True)
        (pub / "saudacao.py").write_text(
            (alvo / "saudacao.py").read_text(encoding="utf-8"), encoding="utf-8")
        return True

    avisos: list = []
    pipe = AutoupdatePipeline(
        fetch_plan=lambda: dict(plano_atual),
        read_fn=ler, apply_fn=aplicar, remove_fn=remover,
        run_gates=gate,
        publish=publicar,
        notify=avisos.append,
    )
    return alvo, plano_atual, pipe, avisos


def main() -> int:
    raiz = Path(__file__).resolve().parent.parent
    python = sys.executable
    alvo, plano, pipe, avisos = montar(raiz, python)

    print("=" * 60)
    print("LAB VIVO — demonstração da Fase C (autoupdate seguro)")
    print("=" * 60)

    # 1) SABOTAGEM
    hash_antes = sha(alvo / "saudacao.py")
    plano["saudacao.py"] = MOD_QUEBRADO
    rel1 = pipe.run_once()
    hash_depois = sha(alvo / "saudacao.py")
    sabotagem_ok = (rel1.publicado is False and hash_antes == hash_depois
                    and (alvo / "saudacao.py").read_text(encoding="utf-8") == MOD_OK_V1)
    print(f"[1] Sabotagem: publicado={rel1.publicado} "
          f"revertido={rel1.revertido} rollback_provado={hash_antes == hash_depois}")
    msg1 = ("SABOTAGEM BLOQUEADA (pytest vermelho), rollback provado por hash"
            if sabotagem_ok else "FALHOU")
    print(f"    -> {msg1}")

    # 2) UPDATE BOM
    plano["saudacao.py"] = MOD_OK_V2
    rel2 = pipe.run_once()
    bom_ok = (rel2.publicado is True
              and (alvo / "saudacao.py").read_text(encoding="utf-8") == MOD_OK_V2
              and (raiz / ".lab-vivo" / "publicado" / "saudacao.py").exists())
    print(f"[2] Update bom: publicado={rel2.publicado}")
    print(f"    -> {'PUBLICADO (pytest verde)' if bom_ok else 'FALHOU'}")

    ok = sabotagem_ok and bom_ok
    print("RESULTADO:", "AUTOUPDATE SEGURO — quebra não publica, bom publica"
          if ok else "FALHOU — ver journal")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

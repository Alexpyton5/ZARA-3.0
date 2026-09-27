@echo off & python -x "%~f0" %* & exit /b %ERRORLEVEL%
# -*- coding: utf-8 -*-
# ============================================================================
# CORRIGIR-TIPOS-LAB.bat — Corrige os 9 erros do tsc na etapa [5/5]
#
# O que faz (sozinho, duplo clique):
#   1) Em frontend/src/renderer/global.d.ts: corrige o bloco de tipos labV1
#      (o submit estava tipado como (payload) e o certo e' com os argumentos
#      posicionais que os paineis usam; tambem adiciona roomMessage,
#      autopilot e cancelMission que faltavam nos tipos).
#   2) Em frontend/src/renderer/components/zara-lab-v2/LabRoom.tsx: ajusta
#      uma chamada para configureAutonomy?.() (protecao contra indefinido).
#   Faz backup dos arquivos antes (.bak-corrigir-tipos).
#
# Depois de rodar, execute o INSTALAR-ZARA.bat novamente.
# ============================================================================
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
GLOBAL_DTS = os.path.join(ROOT, "frontend", "src", "renderer", "global.d.ts")
LABROOM = os.path.join(ROOT, "frontend", "src", "renderer", "components",
                       "zara-lab-v2", "LabRoom.tsx")

NEW_LABV1_BLOCK = """      // Lab v1 — API usada pelos painéis zara-home / zara-lab-v2
      labV1?: {
        snapshot?: (...args: any[]) => Promise<any>;
        createSession?: (...args: any[]) => Promise<any>;
        deleteSession?: (...args: any[]) => Promise<any>;
        submit?: (...args: any[]) => Promise<any>;
        cancel?: (...args: any[]) => Promise<any>;
        cancelMission?: (...args: any[]) => Promise<any>;
        roomMessage?: (...args: any[]) => Promise<any>;
        autopilot?: (...args: any[]) => Promise<any>;
        researchSkill?: (...args: any[]) => Promise<any>;
        agentProfile?: (...args: any[]) => Promise<any>;
        createAgent?: (...args: any[]) => Promise<any>;
        updateAgentProfile?: (...args: any[]) => Promise<any>;
        rollbackAgentProfile?: (...args: any[]) => Promise<any>;
        rebindRole?: (...args: any[]) => Promise<any>;
        archiveAgent?: (...args: any[]) => Promise<any>;
        proposalList?: (...args: any[]) => Promise<any>;
        proposalUpdate?: (...args: any[]) => Promise<any>;
        proposalFeedUpdate?: (...args: any[]) => Promise<any>;
        configureAutonomy?: (...args: any[]) => Promise<any>;
      };"""


def find_matching_brace(text, open_idx):
    depth = 0
    in_str = None
    i = open_idx
    while i < len(text):
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        elif ch in ("'", '"', "`"):
            in_str = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    raise ValueError("chave de fechamento nao encontrada")


def fix_global_dts():
    if not os.path.isfile(GLOBAL_DTS):
        print("[ERRO] Nao encontrei: %s" % os.path.relpath(GLOBAL_DTS, ROOT))
        return 1
    with open(GLOBAL_DTS, encoding="utf-8", errors="replace") as f:
        text = f.read()
    m = re.search(r"[ \t]*labV1\?:[ \t]*\{", text)
    if not m:
        print("[ERRO] Bloco labV1 nao encontrado no global.d.ts")
        return 1
    open_idx = text.index("{", m.start())
    close_idx = find_matching_brace(text, open_idx)
    end_idx = close_idx + 1
    if end_idx < len(text) and text[end_idx] == ";":
        end_idx += 1
    # inclui a linha de comentario "// ..." se estiver colada antes do labV1
    line_start = text.rfind("\n", 0, m.start()) + 1
    prev_end = line_start - 1
    prev_start = text.rfind("\n", 0, prev_end) + 1
    if text[prev_start:prev_end].strip().startswith("//"):
        start_idx = prev_start
    else:
        start_idx = line_start
    new_text = text[:start_idx] + NEW_LABV1_BLOCK + text[end_idx:]
    if new_text == text:
        print("[OK] global.d.ts ja estava correto, nada a mudar")
        return 0
    shutil.copyfile(GLOBAL_DTS, GLOBAL_DTS + ".bak-corrigir-tipos")
    with open(GLOBAL_DTS, "w", encoding="utf-8") as f:
        f.write(new_text)
    print("[OK] global.d.ts corrigido (bloco labV1)")
    print("     backup em global.d.ts.bak-corrigir-tipos")
    return 0


def fix_labroom():
    if not os.path.isfile(LABROOM):
        print("[ERRO] Nao encontrei: %s" % os.path.relpath(LABROOM, ROOT))
        return 1
    with open(LABROOM, encoding="utf-8", errors="replace") as f:
        text = f.read()
    old = "window.zaraIPC?.labV1?.configureAutonomy("
    new = "window.zaraIPC?.labV1?.configureAutonomy?.("
    if new in text:
        print("[OK] LabRoom.tsx ja estava correto, nada a mudar")
        return 0
    if old not in text:
        print("[AVISO] Trecho esperado nao encontrado no LabRoom.tsx; pulando")
        return 0
    shutil.copyfile(LABROOM, LABROOM + ".bak-corrigir-tipos")
    text = text.replace(old, new)
    with open(LABROOM, "w", encoding="utf-8") as f:
        f.write(text)
    print("[OK] LabRoom.tsx corrigido (configureAutonomy?.())")
    print("     backup em LabRoom.tsx.bak-corrigir-tipos")
    return 0


def main():
    print("Corrigindo os tipos do labV1 (9 erros do tsc)...")
    print()
    r1 = fix_global_dts()
    r2 = fix_labroom()
    print()
    if r1 == 0 and r2 == 0:
        print("Pronto! Agora rode o INSTALAR-ZARA.bat novamente.")
        print("(As etapas 1 a 4 passam rapido; o que importa e a etapa 5.)")
        return 0
    print("[ERRO] Algo nao saiu como esperado. Me avise e mande o texto acima.")
    return 1


if __name__ == "__main__":
    sys.exit(main())

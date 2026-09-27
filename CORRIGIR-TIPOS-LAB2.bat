@echo off & python -x "%~f0" %* & exit /b %ERRORLEVEL%
# -*- coding: utf-8 -*-
# ============================================================================
# CORRIGIR-TIPOS-LAB2.bat — Corrige os 8 erros restantes do tsc (etapa [5/5])
#
# A v1 procurou o global.d.ts na pasta errada. Esta v2 procura o arquivo em
# TODOS os lugares possiveis dentro de frontend/ e corrige cada copia
# encontrada. Tambem refaz o ajuste no LabRoom.tsx (sem problema rodar 2x).
# Faz backup antes (.bak-corrigir-tipos2).
#
# Depois de rodar, execute o INSTALAR-ZARA.bat novamente.
# ============================================================================
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND = os.path.join(ROOT, "frontend")
LABROOM = os.path.join(FRONTEND, "src", "renderer", "components",
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


def fix_one_dts(path):
    """Troca o bloco labV1 no arquivo. Retorna True se alterou."""
    with open(path, encoding="utf-8", errors="replace") as f:
        text = f.read()
    m = re.search(r"[ \t]*labV1\?:[ \t]*\{", text)
    if not m:
        return False
    open_idx = text.index("{", m.start())
    close_idx = find_matching_brace(text, open_idx)
    end_idx = close_idx + 1
    if end_idx < len(text) and text[end_idx] == ";":
        end_idx += 1
    line_start = text.rfind("\n", 0, m.start()) + 1
    prev_end = line_start - 1
    prev_start = text.rfind("\n", 0, prev_end) + 1
    if text[prev_start:prev_end].strip().startswith("//"):
        start_idx = prev_start
    else:
        start_idx = line_start
    new_text = text[:start_idx] + NEW_LABV1_BLOCK + text[end_idx:]
    if new_text == text:
        return False
    shutil.copyfile(path, path + ".bak-corrigir-tipos2")
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_text)
    return True


def find_dts_candidates():
    found = []
    # 1) caminho exato onde o CORRIGIR-PONTE escreveu
    exact = os.path.join(FRONTEND, "src", "renderer", "types", "global.d.ts")
    if os.path.isfile(exact):
        found.append(exact)
    # 2) varredura geral: qualquer .d.ts dentro de frontend/ que mencione labV1
    for dirpath, _dirnames, filenames in os.walk(FRONTEND):
        if "node_modules" in dirpath.split(os.sep):
            continue
        for fn in filenames:
            if not fn.endswith(".d.ts"):
                continue
            p = os.path.join(dirpath, fn)
            if p in found:
                continue
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    head = f.read(200000)
            except OSError:
                continue
            if "labV1" in head:
                found.append(p)
    return found


def fix_labroom():
    if not os.path.isfile(LABROOM):
        print("[AVISO] LabRoom.tsx nao encontrado; pulando")
        return True
    with open(LABROOM, encoding="utf-8", errors="replace") as f:
        text = f.read()
    old = "window.zaraIPC?.labV1?.configureAutonomy("
    new = "window.zaraIPC?.labV1?.configureAutonomy?.("
    if new in text:
        print("[OK] LabRoom.tsx ja estava correto")
        return True
    if old not in text:
        print("[AVISO] Trecho esperado nao encontrado no LabRoom.tsx; pulando")
        return True
    shutil.copyfile(LABROOM, LABROOM + ".bak-corrigir-tipos2")
    with open(LABROOM, "w", encoding="utf-8") as f:
        f.write(text.replace(old, new))
    print("[OK] LabRoom.tsx corrigido (configureAutonomy?.())")
    return True


def main():
    print("Procurando os arquivos de tipos do labV1...")
    print()
    candidates = find_dts_candidates()
    if not candidates:
        print("[ERRO] Nenhum arquivo .d.ts com labV1 encontrado em frontend/")
        print("       Rode a partir da pasta principal da ZARA.")
        return 1
    print("Encontrados %d arquivo(s):" % len(candidates))
    for c in candidates:
        print("   - %s" % os.path.relpath(c, ROOT))
    print()
    changed = 0
    for c in candidates:
        try:
            if fix_one_dts(c):
                print("[OK] corrigido: %s" % os.path.relpath(c, ROOT))
                changed += 1
            else:
                print("[OK] ja estava correto: %s" % os.path.relpath(c, ROOT))
        except Exception as e:
            print("[ERRO] %s: %s" % (os.path.relpath(c, ROOT), e))
            return 1
    print()
    if not fix_labroom():
        return 1
    print()
    print("Pronto! %d arquivo(s) de tipos atualizado(s)." % changed)
    print("Agora rode o INSTALAR-ZARA.bat novamente.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

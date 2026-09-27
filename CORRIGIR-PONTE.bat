@echo off & python -x "%~f0" %* & exit /b %ERRORLEVEL%
# -*- coding: utf-8 -*-
# ============================================================================
# CORRIGIR-PONTE.bat — Restaura a ponte do frontend da ZARA
#
# O que faz (sozinho, sem você copiar nada na mão):
#   1) Escreve o global.d.ts corrigido (tipos das APIs labV1, desktop, etc.)
#   2) Lê o preload.js COMPILADO ORIGINAL (frontend/dist-electron/preload.js),
#      que ainda tem os nomes reais dos canais IPC da sua ZARA,
#      e reconstrói o preload.ts com as APIs que faltavam.
#   3) Se o INSTALAR-ZARA.bat da pasta for a versão antiga (v2), troca pela
#      versão com .venv (INSTALAR-ZARA__1.bat).
#
# Depois de rodar, execute o INSTALAR-ZARA.bat novamente (só a etapa 5 importa).
# ============================================================================
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

FRONTEND = os.path.join(ROOT, "frontend")
PRELOAD_TS = os.path.join(FRONTEND, "src", "preload.ts")
GLOBAL_DTS = os.path.join(FRONTEND, "src", "renderer", "types", "global.d.ts")

GLOBAL_DTS_CONTENT = """/// <reference types="vite/client" />

import type React from 'react';
import type { ReminderEvent } from '../../reminderEvents';

declare global {
  // Elemento <webview> do Electron (usado pela aba "ZOE" para embutir o app da zoe).
  namespace JSX {
    interface IntrinsicElements {
      webview: React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & {
        src?: string;
        partition?: string;
        allowpopups?: boolean | '';
        preload?: string;
      };
    }
  }

  interface ZaraWindowControl {
    minimize: () => Promise<void>;
    maximize: () => Promise<void>;
    close: () => Promise<void>;
  }

  interface Window {
    zaraIPC: {
      engine?: { change?: (engine: string) => Promise<any>; list?: () => Promise<any> };
      supercerebro?: { toggle?: (active: boolean) => Promise<any>; status?: () => Promise<any> };
      message?: { send?: (payload: { message: string; engine: string; history: Array<{ role: string; content: string }> }) => Promise<any>; interrupt?: () => Promise<any> };
      conversationHistory?: {
        list?: (limit?: number) => Promise<any>;
        clear?: () => Promise<any>;
      };
      action?: { execute?: (action: string, params: Record<string, any>) => Promise<any>; list?: () => Promise<any> };
      system?: { metrics?: () => Promise<any>; info?: () => Promise<any> };
      voice?: { start?: () => Promise<any>; stop?: () => Promise<any>; status?: () => Promise<any>; mute?: (muted: boolean) => Promise<any>; sendMicChunk?: (pcm: any) => Promise<any> };
      config?: { get?: () => Promise<any>; set?: (key: string, value: any) => Promise<any> };
      // Atalhos de desktop (abrir apps, pastas, links externos, configurações)
      desktop?: {
        openExternal?: (id: string) => Promise<any>;
        openFolder?: (id: string) => Promise<any>;
        openSettings?: (id: string) => Promise<any>;
        openApp?: (id: string) => Promise<any>;
      };
      // Memória de projeto / galáxia de memórias / memória do usuário
      projectMemory?: { context?: () => Promise<any>; get?: (key: string) => Promise<any> };
      memoryGalaxy?: { list?: () => Promise<any> };
      userMemory?: { add?: (payload: { fact: string; source: string }) => Promise<any> };
      // Lab v1 — API usada pelos painéis zara-home / zara-lab-v2
      labV1?: {
        snapshot?: (...args: any[]) => Promise<any>;
        createSession?: (objective: string) => Promise<any>;
        deleteSession?: (sessionId: string) => Promise<any>;
        submit?: (payload: Record<string, any>) => Promise<any>;
        cancel?: (payload: Record<string, any>) => Promise<any>;
        researchSkill?: (payload: any) => Promise<any>;
        agentProfile?: (agentId: string) => Promise<any>;
        createAgent?: (payload: Record<string, any>) => Promise<any>;
        updateAgentProfile?: (payload: Record<string, any>) => Promise<any>;
        rollbackAgentProfile?: (agentId: string, version: number) => Promise<any>;
        rebindRole?: (payload: Record<string, any>) => Promise<any>;
        archiveAgent?: (agentId: string) => Promise<any>;
        proposalList?: (...args: any[]) => Promise<any>;
        proposalUpdate?: (...args: any[]) => Promise<any>;
        proposalFeedUpdate?: (...args: any[]) => Promise<any>;
        configureAutonomy?: (enabled: boolean) => Promise<any>;
      };
      lab?: {
        state?: () => Promise<any>;
        send?: (payload: { author: string; target: string; content: string }) => Promise<any>;
        createProposal?: (payload: { title: string; summary: string; risk: string; owner: string }) => Promise<any>;
        decideProposal?: (payload: { id: string; decision: 'APPROVE' | 'REJECT' }) => Promise<any>;
        missionState?: () => Promise<any>;
        missionVerify?: (payload: { code: string; state: string; evidence?: string[]; note?: string }) => Promise<any>;
        missionCycle?: (payload: { action: 'resume' | 'complete'; objective?: string; cycle_id?: string; summary?: string }) => Promise<any>;
        missionRecruit?: (payload: { task: string; needed_capabilities?: string[] }) => Promise<any>;
        missionFinding?: (payload: { reader: string; source_name: string; url: string; summary: string }) => Promise<any>;
        missionPrioritize?: (payload: { finding_id: string; decision: 'PRIORITIZED' | 'NO_CHANGE'; note?: string; proposal_id?: string }) => Promise<any>;
        missionPatch?: (payload: Record<string, unknown>) => Promise<any>;
        missionBot?: (payload: Record<string, unknown>) => Promise<any>;
        autonomyStart?: (payload?: { objective?: string }) => Promise<any>;
        autonomyStop?: () => Promise<any>;
        autonomyStatus?: () => Promise<any>;
      };
      reminders?: {
        create?: (payload: { text: string; due_at: number; timezone?: string }) => Promise<unknown>;
        list?: (state?: string) => Promise<unknown>;
        cancel?: (id: string) => Promise<unknown>;
      };
      conselheira?: {
        sendMessage?: (payload: { text: string }) => Promise<any>;
        sync?: () => Promise<any>;
        getMessages?: (payload?: { limit?: number }) => Promise<any>;
        getStatus?: () => Promise<any>;
      };
      window?: ZaraWindowControl;
      on?: {
        stateChange?: (callback: (state: string) => void) => () => void;
        message?: (callback: (message: { role: string; content: string }) => void) => () => void;
        metrics?: (callback: (metrics: any) => void) => () => void;
        voiceLevel?: (callback: (level: number, tone: number, speaking: boolean) => void) => () => void;
        supercerebroChange?: (callback: (active: boolean) => void) => () => void;
        reminderCreated?: (callback: (reminder: ReminderEvent) => void) => () => void;
        reminderFired?: (callback: (reminder: ReminderEvent) => void) => () => void;
        voiceOutputAudio?: (callback: (data: any) => void) => () => void;
        labOperationResult?: (callback: (event: any) => void) => () => void;
      };
    };
  }
}

export {};
"""


def extract_brace_block(s, open_idx):
    """Dado o índice de um '{', retorna (conteúdo_interno, índice_do_'}')."""
    depth = 0
    i = open_idx
    in_str = None
    while i < len(s):
        c = s[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        else:
            if c in "\"'`":
                in_str = c
            elif c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    return s[open_idx + 1:i], i
        i += 1
    raise ValueError("chaves desbalanceadas")


def top_level_groups(body):
    """Retorna [(nome, corpo)] só dos grupos de nível superior (ignora objetos aninhados)."""
    groups = []
    occupied = []
    for gm in re.finditer(r"([A-Za-z_$][\w$]*)\s*:\s*\{", body):
        if any(s <= gm.start() < e for s, e in occupied):
            continue
        try:
            gbody, close_idx = extract_brace_block(body, gm.end() - 1)
        except ValueError:
            continue
        occupied.append((gm.start(), close_idx + 1))
        groups.append((gm.group(1), gbody))
    return groups


def parse_compiled_preload(js):
    """Extrai {grupo: {'invoke': {metodo: canal}, 'on': {metodo: canal}}} do preload.js compilado."""
    m = re.search(r"(?:const|var)\s+zaraAPI\s*=\s*\{", js)
    if not m:
        return {}
    body, _ = extract_brace_block(js, m.end() - 1)
    groups = {}
    for gname, gbody in top_level_groups(body):
        invokes, ons = {}, {}
        for mm in re.finditer(
                r"([A-Za-z_$][\w$]*)\s*:\s*\([^)]*\)\s*=>\s*[\w.$]*ipcRenderer\.invoke\(\s*['\"]([^'\"]+)['\"]",
                gbody):
            invokes[mm.group(1)] = mm.group(2)
        for om in re.finditer(r"([A-Za-z_$][\w$]*)\s*:\s*\(\s*callback\b", gbody):
            brace = gbody.find("{", om.end())
            if brace < 0:
                continue
            try:
                hbody, _ = extract_brace_block(gbody, brace)
            except ValueError:
                continue
            ch = re.search(r"ipcRenderer\.on\(\s*['\"]([^'\"]+)['\"]", hbody)
            if ch:
                ons[om.group(1)] = ch.group(1)
        if invokes or ons:
            groups[gname] = {"invoke": invokes, "on": ons}
    return groups


def parse_ts_methods(ts):
    """Retorna {grupo: set(metodos)} do preload.ts atual (só nomes)."""
    m = re.search(r"const\s+zaraAPI\s*=\s*\{", ts)
    if not m:
        return {}
    body, _ = extract_brace_block(ts, m.end() - 1)
    groups = {}
    for gname, gbody in top_level_groups(body):
        methods = set(re.findall(r"^\s*([A-Za-z_$][\w$]*)\s*:\s*(?:\([^)]*\)\s*=>|async\b)", gbody, re.M))
        groups[gname] = methods
    return groups


def gen_invoke_line(method, channel):
    return "    %s: (...args: any[]) => ipcRenderer.invoke('%s', ...args)," % (method, channel)


def gen_on_lines(method, channel):
    return [
        "    %s: (callback: (data: any) => void) => {" % method,
        "      const handler = (_event: any, data: any) => callback(data);",
        "      ipcRenderer.on('%s', handler);" % channel,
        "      return () => ipcRenderer.off('%s', handler);" % channel,
        "    },",
    ]


def insert_methods_into_group(ts, gname, lines):
    """Insere linhas de métodos dentro de um grupo existente do zaraAPI."""
    m = re.search(r"^  " + re.escape(gname) + r"\s*:\s*\{", ts, re.M)
    if not m:
        return ts, False
    _, close_idx = extract_brace_block(ts, m.end() - 1)
    head = ts[:close_idx].rstrip()
    new_ts = head + "\n" + "\n".join(lines) + "\n  " + ts[close_idx:]
    return new_ts, True


def find_original_preload():
    """Procura o preload.js compilado ORIGINAL (com labV1)."""
    skip_dirs = ("node_modules", ".venv", "build-sidecar", "dist-sidecar", ".git", "__pycache__")
    candidates = []
    p1 = os.path.join(FRONTEND, "dist-electron", "preload.js")
    if os.path.isfile(p1):
        candidates.append(p1)
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.startswith(".")]
        if "preload.js" in filenames:
            p = os.path.join(dirpath, "preload.js")
            if p not in candidates:
                candidates.append(p)
    for c in candidates:
        try:
            with open(c, encoding="utf-8", errors="replace") as f:
                if "labV1" in f.read(500000):
                    return c
        except OSError:
            pass
    return None


def main():
    print("=" * 62)
    print("  CORRIGIR-PONTE — restaura preload.ts e global.d.ts da ZARA")
    print("=" * 62)
    print()

    if not os.path.isfile(PRELOAD_TS):
        print("[ERRO] Nao achei %s" % PRELOAD_TS)
        print("       Rode este .bat dentro da pasta raiz da ZARA.")
        return 1

    # 1) global.d.ts corrigido
    os.makedirs(os.path.dirname(GLOBAL_DTS), exist_ok=True)
    with open(GLOBAL_DTS, "w", encoding="utf-8") as f:
        f.write(GLOBAL_DTS_CONTENT)
    print("[OK] global.d.ts atualizado (tipos labV1, desktop, memorias, voz, eventos)")

    # 2) backup do preload.ts atual
    backup = PRELOAD_TS + ".bak-corrigir-ponte"
    shutil.copyfile(PRELOAD_TS, backup)

    # 3) acha o preload original compilado
    orig = find_original_preload()
    if not orig:
        print()
        print("[ERRO] Nao encontrei o preload.js original (com as APIs labV1).")
        print("       Procurei em frontend/dist-electron/preload.js e na pasta toda.")
        print("       Me envie o arquivo frontend/src/main.ts que eu gero a correcao.")
        return 1
    print("[OK] preload original encontrado: %s" % os.path.relpath(orig, ROOT))

    with open(orig, encoding="utf-8", errors="replace") as f:
        js = f.read()
    orig_groups = parse_compiled_preload(js)
    if "labV1" not in orig_groups:
        print("[ERRO] O preload.js encontrado nao contem as APIs originais (labV1).")
        print("       Me envie o arquivo frontend/src/main.ts que eu gero a correcao.")
        return 1

    with open(PRELOAD_TS, encoding="utf-8") as f:
        ts = f.read()
    cur = parse_ts_methods(ts)

    restored = []

    # 4) grupos inteiramente novos (labV1, desktop, projectMemory, ...)
    chunks = []
    for gname, g in orig_groups.items():
        if gname in cur or gname == "on":
            continue
        lines = ["  %s: {" % gname]
        for method, channel in g["invoke"].items():
            lines.append(gen_invoke_line(method, channel))
        for method, channel in g["on"].items():
            lines.extend(gen_on_lines(method, channel))
        lines.append("  },")
        chunks.append("\n".join(lines))
        restored.append("%s (%d metodos)" % (gname, len(g["invoke"]) + len(g["on"])))
    if chunks:
        header = "  // ----- Restaurado do preload original (CORRIGIR-PONTE) -----"
        marker = "\n  // Event listeners"
        idx = ts.find(marker)
        if idx >= 0:
            ts = ts[:idx] + "\n" + header + "\n" + "\n".join(chunks) + ts[idx:]
        else:
            m = re.search(r"const\s+zaraAPI\s*=\s*\{", ts)
            _, close_idx = extract_brace_block(ts, m.end() - 1)
            head = ts[:close_idx].rstrip()
            ts = head + "\n" + header + "\n" + "\n".join(chunks) + "\n}" + ts[close_idx + 1:]

    # 5) métodos faltantes em grupos que já existem (voice.mute, on.voiceOutputAudio, ...)
    for gname, g in orig_groups.items():
        if gname not in cur:
            continue
        for method, channel in g["invoke"].items():
            if method not in cur[gname]:
                ts, ok = insert_methods_into_group(ts, gname, [gen_invoke_line(method, channel)])
                if ok:
                    restored.append("%s.%s" % (gname, method))
        for method, channel in g["on"].items():
            if method not in cur[gname]:
                ts, ok = insert_methods_into_group(ts, gname, gen_on_lines(method, channel))
                if ok:
                    restored.append("%s.%s" % (gname, method))

    with open(PRELOAD_TS, "w", encoding="utf-8") as f:
        f.write(ts)

    if restored:
        print("[OK] preload.ts restaurado (%d itens):" % len(restored))
        for r in restored:
            print("     - %s" % r)
    else:
        print("[OK] preload.ts ja estava completo, nada a restaurar")
    print("     (backup do anterior em %s)" % os.path.basename(backup))

    # 6) garante INSTALAR-ZARA.bat = v3 (.venv)
    bat = os.path.join(ROOT, "INSTALAR-ZARA.bat")
    bat1 = os.path.join(ROOT, "INSTALAR-ZARA__1.bat")
    try:
        if os.path.isfile(bat) and os.path.isfile(bat1):
            with open(bat, encoding="utf-8", errors="replace") as f:
                b = f.read()
            with open(bat1, encoding="utf-8", errors="replace") as f:
                b1 = f.read()
            if "uv pip install --system" in b and "uv venv .venv" in b1:
                shutil.copyfile(bat1, bat)
                print("[OK] INSTALAR-ZARA.bat atualizado para a versao com .venv")
    except OSError as e:
        print("[AVISO] nao consegui verificar o INSTALAR-ZARA.bat: %s" % e)

    print()
    print("Pronto! Agora rode o INSTALAR-ZARA.bat novamente.")
    print("(As etapas 1 a 4 passam rapido; o que importa e a etapa 5.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

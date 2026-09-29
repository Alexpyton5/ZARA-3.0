/// <reference types="vite/client" />

import type React from 'react';
import type { ReminderEvent } from '../../reminderEvents';

declare global {
  // Elemento <webview> do Electron (usado pela aba "ZOE" para embutir o app da zoe).
  namespace JSX {
    interface IntrinsicElements {
      webview: React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & {
        src?: string;
        partition?: string;
        preload?: string;
      };
    }
  }

  interface ZaraWindowControl {
    minimize: () => Promise<void>;
    maximize: () => Promise<void>;
    close: () => Promise<void>;
  }

  // Computer-agent (use-computer) — Frente B. A ponte pode chegar por dois
  // caminhos (a Frente C escolhe um na integração — ver CONTRATO-FRENTE-C.md):
  //  - window.zaraComputerAgent (preload separado: src/preload-computer-agent.ts)
  //  - window.zaraIPC.computerAgent (seção mesclada no preload principal)
  interface ComputerAgentStartedPayload {
    goal: string;
  }
  interface ComputerAgentStepPayload {
    step: string;
    index?: number;
    total?: number;
  }
  interface ComputerAgentStoppedPayload {
    goal?: string;
    success?: boolean;
    refused?: boolean;
    verified?: boolean;
    /** Quantidade de passos executados (o backend manda o número, não a lista). */
    steps?: number;
    error?: string | null;
  }
  interface ComputerAgentPreloadAPI {
    run?: (goal: string) => Promise<any>;
    showOverlay?: () => Promise<any>;
    hideOverlay?: () => Promise<any>;
    onStarted?: (callback: (data: ComputerAgentStartedPayload) => void) => () => void;
    onStep?: (callback: (data: ComputerAgentStepPayload) => void) => () => void;
    onStopped?: (callback: (data: ComputerAgentStoppedPayload) => void) => () => void;
  }

  interface Window {
    zaraIPC: {
      zoeBridge?: { status?: () => Promise<{ ready: boolean }> };
      engine?: { change?: (engine: string) => Promise<any>; list?: () => Promise<any> };
      supercerebro?: { toggle?: (active: boolean) => Promise<any>; status?: () => Promise<any> };
      message?: { send?: (payload: { message: string; engine: string; history: Array<{ role: string; content: string }> }) => Promise<any>; interrupt?: () => Promise<any> };
      conversationHistory?: {
        list?: (limit?: number) => Promise<any>;
        clear?: () => Promise<any>;
      };
      action?: { execute?: (action: string, params: Record<string, any>) => Promise<any>; list?: () => Promise<any> };
      system?: { metrics?: () => Promise<any>; info?: () => Promise<any>; selfStatus?: () => Promise<any> };
      voice?: { start?: () => Promise<any>; startZoe?: () => Promise<any>; speakZoe?: (text: string) => Promise<any>; stop?: () => Promise<any>; status?: () => Promise<any>; getEngine?: () => Promise<any>; setEngine?: (engine: 'kore' | 'omnivoice') => Promise<any>; mute?: (muted?: boolean) => Promise<any>; sendMicChunk?: (pcm: any) => void };
      config?: { get?: () => Promise<any>; set?: (key: string, value: any) => Promise<any> };
      // Atalhos de desktop (abrir apps, pastas, links externos, configurações)
      desktop?: {
        openExternal?: (id: string) => Promise<any>;
        openFolder?: (id: string) => Promise<any>;
        openSettings?: (id: string) => Promise<any>;
        openApp?: (id: string) => Promise<any>;
      };
      // Memória de projeto / galáxia de memórias / memória do usuário
      projectMemory?: { context?: () => Promise<any>; get?: (key: string) => Promise<any>; list?: () => Promise<any> };
      memoryGalaxy?: { list?: () => Promise<any> };
      userMemory?: {
        add?: (payload: { fact: string; category?: string; confidence?: number; source?: string }) => Promise<any>;
        search?: (payload: { query: string; since?: number; until?: number; limit?: number }) => Promise<any>;
        list?: (payload?: { category?: string; status?: string }) => Promise<any>;
        forget?: (id: string) => Promise<any>;
      };
      // Lab v1 — API usada pelos painéis zara-home / zara-lab-v2
      labV1?: {
        snapshot?: (sessionId?: string, teamId?: string) => Promise<any>;
        createSession?: (objective: string, teamId?: string) => Promise<any>;
        deleteSession?: (sessionId: string) => Promise<any>;
        submit?: (sessionId: string, text: string, requestId?: string) => Promise<any>;
        cancel?: (...args: any[]) => Promise<any>;
        cancelMission?: (sessionId: string, requestId?: string) => Promise<any>;
        roomMessage?: (sessionId: string | undefined, content: string, requestId?: string) => Promise<any>;
        autopilot?: (intent: string, requestId?: string) => Promise<any>;
        activateAutopilot?: () => Promise<any>;
        providers?: () => Promise<any>;
        researchSkill?: (...args: any[]) => Promise<any>;
        teamChat?: (...args: any[]) => Promise<any>;
        agentProfile?: (...args: any[]) => Promise<any>;
        createAgent?: (...args: any[]) => Promise<any>;
        configureAgent?: (...args: any[]) => Promise<any>;
        updateAgentProfile?: (...args: any[]) => Promise<any>;
        rollbackAgentProfile?: (...args: any[]) => Promise<any>;
        rebindRole?: (...args: any[]) => Promise<any>;
        archiveAgent?: (...args: any[]) => Promise<any>;
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
      // Computer-agent (use-computer) — Frente B (só existe se a Frente C
      // mesclar a seção no preload principal; senão vive em window.zaraComputerAgent).
      computerAgent?: ComputerAgentPreloadAPI;
      on?: {
        stateChange?: (callback: (state: string) => void) => () => void;
        message?: (callback: (message: { role: string; content: string }) => void) => () => void;
        metrics?: (callback: (metrics: any) => void) => () => void;
        voiceLevel?: (callback: (level: number, tone: number, speaking: boolean) => void) => () => void;
        supercerebroChange?: (callback: (active: boolean) => void) => () => void;
        reminderCreated?: (callback: (reminder: ReminderEvent) => void) => () => void;
        reminderFired?: (callback: (reminder: ReminderEvent) => void) => () => void;
        voiceOutputAudio?: (callback: (data: any) => void) => () => void;
        zoeVoiceInput?: (callback: (data: { text: string }) => void) => () => void;
        labOperationResult?: (callback: (event: any) => void) => () => void;
        routingTelemetry?: (callback: (telemetry: any) => void) => () => void;
      };
    };
    // Computer-agent (use-computer) — Frente B: preload separado
    // (src/preload-computer-agent.ts). Opcional até a Frente C integrar.
    zaraComputerAgent?: ComputerAgentPreloadAPI;
  }
}

export {};

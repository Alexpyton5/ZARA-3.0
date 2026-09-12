/// <reference types="vite/client" />

import type { ReminderEvent } from '../../reminderEvents';

interface ZaraWindowControl {
  minimize: () => Promise<void>;
  maximize: () => Promise<void>;
  close: () => Promise<void>;
}

interface FrontMessageResponse {
  response_origin?: 'front_brain_run' | 'front_brain_policy' | 'local_deterministic';
  success?: boolean;
  response?: string;
  error?: string;
  engine?: string;
  run_id?: string;
  model_requested?: string;
  model_reported?: string | null;
  provider?: string;
  provenance_status?: 'UNREPORTED' | 'MATCHED' | 'MISMATCH_REJECTED';
  rerouted?: boolean;
  [key: string]: unknown;
}

declare global {
  interface Window {
    zaraIPC: {
      engine?: { change?: (engine: string) => Promise<any>; list?: () => Promise<any> };
      message?: { send?: (payload: { message: string; engine: string; history: Array<{ role: string; content: string }> }) => Promise<FrontMessageResponse>; interrupt?: () => Promise<any> };
      conversationHistory?: {
        list?: (limit?: number) => Promise<any>;
        clear?: () => Promise<any>;
      };
      memoryGalaxy?: { list?: () => Promise<any> };
      userMemory?: {
        add?: (payload: { fact: string; category?: string; confidence?: number; source?: string }) => Promise<any>;
        search?: (payload: { query: string; since?: number; until?: number; limit?: number }) => Promise<any>;
        list?: (payload?: { category?: string; status?: string }) => Promise<any>;
        forget?: (id: string) => Promise<any>;
      };
      projectMemory?: {
        get?: (key: string) => Promise<any>;
        list?: () => Promise<any>;
        context?: () => Promise<{ success: boolean; active_project_id: string | null; projects: Array<{ id: string; keys: string[]; updated_at: number | null }>; legacy_document_keys: string[] }>;
      };
      desktop?: {
        openApp?: (id: 'vscode' | 'figma' | 'postman' | 'docker') => Promise<{ success: boolean; output?: string; error?: string }>;
        openExternal?: (id: 'whatsapp' | 'telegram' | 'instagram' | 'gmail' | 'figma') => Promise<{ success: boolean; output?: string; error?: string }>;
        openSettings?: (id: 'storage' | 'temporary' | 'startup' | 'update' | 'security' | 'firewall' | 'privacy' | 'power') => Promise<{ success: boolean; output?: string; error?: string }>;
        openFolder?: (id: 'home' | 'documents' | 'downloads' | 'desktop') => Promise<{ success: boolean; output?: string; error?: string }>;
      };
      action?: { execute?: (action: string, params: Record<string, any>) => Promise<any>; list?: () => Promise<any> };
      system?: { metrics?: () => Promise<any>; info?: () => Promise<any>; selfStatus?: () => Promise<any> };
      voice?: {
        start?: () => Promise<any>;
        stop?: () => Promise<any>;
        status?: () => Promise<any>;
        // ZARA-AEC-RENDERER-001
        sendMicChunk?: (pcm: string) => void;
        // ZARA-BOTAO-MUDO-001
        mute?: (mudo?: boolean) => Promise<{ success: boolean; mudo: boolean }>;
      };
      config?: { get?: () => Promise<any>; set?: (key: string, value: any) => Promise<any> };
      lab?: {
        state?: () => Promise<any>;
        send?: (payload: { author: string; target: string; content: string }) => Promise<any>;
        createProposal?: (payload: { title: string; summary: string; risk: string; owner: string }) => Promise<any>;
        decideProposal?: (payload: { id: string; decision: 'APPROVE' | 'REJECT' }) => Promise<any>;
      };
      // ZARA-LAB-V1-001: new multi-agent runtime, additive sibling of `lab`.
      labV1?: {
        configureAutonomy: (enabled: boolean) => Promise<{ success: boolean; error?: string }>;
        autopilot: (intent: string) => Promise<{ success: boolean; session_id?: string; state?: string; code?: string; error?: string }>;
        cancelMission: (sessionId: string) => Promise<any>;
        snapshot?: (sessionId?: string, teamId?: string) => Promise<import('../components/zara-lab-v2/labTypes').RoomSnapshotResult>;
        createSession?: (objective: string, teamId?: string) => Promise<any>;
        submit?: (sessionId: string, text: string) => Promise<any>;
        providers?: () => Promise<any>;
        createAgent?: (payload: { name: string; provider_id: string; model: string; role?: string; team_id?: string; lifecycle?: string; instructions?: string; fallback_agent_id?: string }) => Promise<any>;
        archiveAgent?: (agentId: string) => Promise<any>;
        rebindRole?: (payload: { team_id: string; role: string; agent_id: string; reason?: string }) => Promise<any>;
      };
      reminders?: {
        create?: (payload: { text: string; due_at: number; timezone?: string }) => Promise<unknown>;
        list?: (state?: string) => Promise<unknown>;
        cancel?: (id: string) => Promise<unknown>;
      };
      window?: ZaraWindowControl;
      on?: {
        stateChange?: (callback: (state: string) => void) => () => void;
        message?: (callback: (message: { role: string; content: string }) => void) => () => void;
        metrics?: (callback: (metrics: any) => void) => () => void;
        voiceLevel?: (callback: (level: number, tone: number, speaking: boolean) => void) => () => void;
        // ZARA-AEC-RENDERER-001: PCM da Kore para o renderer tocar (far-end do AEC).
        voiceOutputAudio?: (
          callback: (data: { pcm?: string; sampleRate?: number; stop?: boolean }) => void,
        ) => () => void;
        reminderCreated?: (callback: (reminder: ReminderEvent) => void) => () => void;
        reminderFired?: (callback: (reminder: ReminderEvent) => void) => () => void;
        routingTelemetry?: (callback: (telemetry: { success: boolean; latency: number | null; fallback: boolean; pendingReview: number; error?: string | null }) => void) => () => void;
      };
    };
  }
}

export {};

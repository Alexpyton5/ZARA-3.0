/// <reference types="vite/client" />

import type { ReminderEvent } from '../../reminderEvents';

interface ZaraWindowControl {
  minimize: () => Promise<void>;
  maximize: () => Promise<void>;
  close: () => Promise<void>;
}

declare global {
  interface Window {
    zaraIPC: {
      engine?: { change?: (engine: string) => Promise<any>; list?: () => Promise<any> };
      message?: { send?: (payload: { message: string; engine: string; history: Array<{ role: string; content: string }> }) => Promise<any>; interrupt?: () => Promise<any> };
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

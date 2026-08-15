// Electron Preload Script — Secure IPC bridge
// This runs in the renderer process but has access to Node.js APIs

import { contextBridge, ipcRenderer } from 'electron'
import type { ReminderEvent } from './reminderEvents'

// Define the API we want to expose to the renderer
const zaraAPI = {
  // Engine management
  engine: {
    change: (engine: string) => ipcRenderer.invoke('engine-change', engine),
    list: () => ipcRenderer.invoke('engine-list'),
  },

  // Supercerebro
  supercerebro: {
    toggle: (active: boolean) => ipcRenderer.invoke('supercerebro-toggle', active),
    status: () => ipcRenderer.invoke('supercerebro-status'),
  },

  // Messaging
  message: {
    send: (payload: { message: string; engine: string; history: Array<{ role: string; content: string }> }) =>
      ipcRenderer.invoke('send-message', payload),
    interrupt: () => ipcRenderer.invoke('interrupt'),
  },

  // Private, local-only Home transcript
  conversationHistory: {
    list: (limit = 500) => ipcRenderer.invoke('conversation-history-list', { limit }),
    clear: () => ipcRenderer.invoke('conversation-history-clear'),
  },

  memoryGalaxy: {
    list: () => ipcRenderer.invoke('memory-galaxy-list'),
  },

  // Actions
  action: {
    execute: (action: string, params: Record<string, any>) => ipcRenderer.invoke('action-execute', action, params),
    list: () => ipcRenderer.invoke('action-list'),
  },

  // System
  system: {
    metrics: () => ipcRenderer.invoke('system-metrics'),
    info: () => ipcRenderer.invoke('system-info'),
  },

  // Voice
  voice: {
    start: () => ipcRenderer.invoke('voice-start'),
    stop: () => ipcRenderer.invoke('voice-stop'),
    status: () => ipcRenderer.invoke('voice-status'),
    // ZARA-AEC-RENDERER-001: microfone limpo pelo AEC do Chromium, sem
    // resposta do backend — é fluxo contínuo, não requisição.
    sendMicChunk: (pcm: string) => ipcRenderer.send('voice-mic-chunk', pcm),
    // ZARA-BOTAO-MUDO-005. Com argumento: define. Sem argumento: só consulta,
    // que é como o botão descobre a cor certa quando o app abre.
    mute: (mudo?: boolean) => ipcRenderer.invoke('voice-mute', mudo),
  },

  // Config
  config: {
    get: () => ipcRenderer.invoke('config-get'),
    set: (key: string, value: any) => ipcRenderer.invoke('config-set', key, value),
  },

  // ZARA Lab — local council and approval workflow
  lab: {
    state: () => ipcRenderer.invoke('lab-state'),
    send: (payload: { author: string; target: string; content: string }) => ipcRenderer.invoke('lab-send', payload),
    createProposal: (payload: { title: string; summary: string; risk: string; owner: string }) => ipcRenderer.invoke('lab-proposal-create', payload),
    decideProposal: (payload: { id: string; decision: 'APPROVE' | 'REJECT' }) => ipcRenderer.invoke('lab-proposal-decide', payload),
  },

  reminders: {
    create: (payload: { text: string; due_at: number; timezone?: string }) => ipcRenderer.invoke('reminder-create', payload),
    list: (state?: string) => ipcRenderer.invoke('reminder-list', state),
    cancel: (id: string) => ipcRenderer.invoke('reminder-cancel', id),
  },

  // Window controls
  window: {
    minimize: () => ipcRenderer.invoke('window-minimize'),
    maximize: () => ipcRenderer.invoke('window-maximize'),
    close: () => ipcRenderer.invoke('window-close'),
  },

  // Event listeners
  on: {
    stateChange: (callback: (state: string) => void) => {
      const handler = (_event: any, state: string) => callback(state)
      ipcRenderer.on('state-change', handler)
      return () => ipcRenderer.off('state-change', handler)
    },
    message: (callback: (message: { role: string; content: string }) => void) => {
      const handler = (_event: any, message: any) => callback(message)
      ipcRenderer.on('message', handler)
      return () => ipcRenderer.off('message', handler)
    },
    metrics: (callback: (metrics: any) => void) => {
      const handler = (_event: any, metrics: any) => callback(metrics)
      ipcRenderer.on('metrics', handler)
      return () => ipcRenderer.off('metrics', handler)
    },
    voiceLevel: (callback: (level: number, tone: number, speaking: boolean) => void) => {
      const handler = (_event: any, level: number, tone: number, speaking: boolean) => callback(level, tone, speaking)
      ipcRenderer.on('voice-level', handler)
      return () => ipcRenderer.off('voice-level', handler)
    },
    // ZARA-AEC-RENDERER-001. `stop: true` significa cortar agora (barge-in),
    // não silêncio.
    voiceOutputAudio: (
      callback: (data: { pcm?: string; sampleRate?: number; stop?: boolean }) => void,
    ) => {
      const handler = (_event: any, data: any) => callback(data || {})
      ipcRenderer.on('voice-output-audio', handler)
      return () => ipcRenderer.off('voice-output-audio', handler)
    },
    supercerebroChange: (callback: (active: boolean) => void) => {
      const handler = (_event: any, active: boolean) => callback(active)
      ipcRenderer.on('supercerebro-change', handler)
      return () => ipcRenderer.off('supercerebro-change', handler)
    },
    reminderCreated: (callback: (reminder: ReminderEvent) => void) => {
      const handler = (_event: unknown, reminder: ReminderEvent) => callback(reminder)
      ipcRenderer.on('reminder-created', handler)
      return () => ipcRenderer.off('reminder-created', handler)
    },
    reminderFired: (callback: (reminder: ReminderEvent) => void) => {
      const handler = (_event: unknown, reminder: ReminderEvent) => callback(reminder)
      ipcRenderer.on('reminder-fired', handler)
      return () => ipcRenderer.off('reminder-fired', handler)
    },
  },
}

// Expose the API to the renderer process
contextBridge.exposeInMainWorld('zaraIPC', zaraAPI)

// Type declarations
declare global {
  interface Window {
    zaraIPC: typeof zaraAPI
  }
}

export {}

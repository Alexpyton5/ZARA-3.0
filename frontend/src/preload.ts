// Electron Preload Script — Secure IPC bridge
// This runs in the renderer process but has access to Node.js APIs

import { contextBridge, ipcRenderer } from 'electron'
import type { ReminderEvent } from './reminderEvents'

// Define the API we want to expose to the renderer
const zaraAPI = {
  zoeBridge: {
    status: () => ipcRenderer.invoke('zoe-bridge-status') as Promise<{ ready: boolean }>,
  },
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

  // Project, galaxy and user memory bridges restored from the original
  // compiled preload. Keep the backend payload shapes unchanged.
  memoryGalaxy: {
    list: () => ipcRenderer.invoke('memory-galaxy-list'),
  },
  userMemory: {
    add: (payload: { fact: string; category?: string; confidence?: number; source?: string }) =>
      ipcRenderer.invoke('memory-user-add', payload),
    search: (payload: { query: string; since?: number; until?: number; limit?: number }) =>
      ipcRenderer.invoke('memory-user-search', payload),
    list: (payload?: { category?: string; status?: string }) =>
      ipcRenderer.invoke('memory-user-list', payload),
    forget: (id: string) => ipcRenderer.invoke('memory-user-forget', { id }),
  },
  projectMemory: {
    get: (key: string) => ipcRenderer.invoke('project-memory-get', { key }),
    list: () => ipcRenderer.invoke('project-memory-list'),
    context: () => ipcRenderer.invoke('project-memory-context'),
  },
  desktop: {
    openApp: (id: string) => ipcRenderer.invoke('desktop-open-app', id),
    openExternal: (id: string) => ipcRenderer.invoke('desktop-open-external', id),
    openSettings: (id: string) => ipcRenderer.invoke('desktop-open-settings', id),
    openFolder: (id: string) => ipcRenderer.invoke('desktop-open-folder', id),
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
    selfStatus: () => ipcRenderer.invoke('self-status'),
  },

  // Voice
  voice: {
    start: () => ipcRenderer.invoke('voice-start'),
    startZoe: () => ipcRenderer.invoke('zoe-voice-start'),
    speakZoe: (text: string) => ipcRenderer.invoke('zoe-voice-speak', text),
    stop: () => ipcRenderer.invoke('voice-stop'),
    status: () => ipcRenderer.invoke('voice-status'),
    getEngine: () => ipcRenderer.invoke('voice-engine-get'),
    setEngine: (engine: 'kore' | 'omnivoice') => ipcRenderer.invoke('voice-engine-set', { engine }),
    sendMicChunk: (pcm: any) => ipcRenderer.send('voice-mic-chunk', pcm),
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
    // Living Team mission (ZARA-LAB-LIVING-TEAM-20260925)
    missionState: () => ipcRenderer.invoke('lab-mission-state'),
    missionVerify: (payload: { code: string; state: string; evidence?: string[]; note?: string }) => ipcRenderer.invoke('lab-mission-verify', payload),
    missionCycle: (payload: { action: 'resume' | 'complete'; objective?: string; cycle_id?: string; summary?: string }) => ipcRenderer.invoke('lab-mission-cycle', payload),
    missionRecruit: (payload: { task: string; needed_capabilities?: string[] }) => ipcRenderer.invoke('lab-mission-recruit', payload),
    missionFinding: (payload: { reader: string; source_name: string; url: string; summary: string }) => ipcRenderer.invoke('lab-mission-finding', payload),
    missionPrioritize: (payload: { finding_id: string; decision: 'PRIORITIZED' | 'NO_CHANGE'; note?: string; proposal_id?: string }) => ipcRenderer.invoke('lab-mission-prioritize', payload),
    missionPatch: (payload: Record<string, unknown>) => ipcRenderer.invoke('lab-mission-patch', payload),
    missionBot: (payload: Record<string, unknown>) => ipcRenderer.invoke('lab-mission-bot', payload),
    // Autonomous mode (council works on its own)
    autonomyStart: (payload?: { objective?: string }) => ipcRenderer.invoke('lab-autonomy-start', payload || {}),
    autonomyStop: () => ipcRenderer.invoke('lab-autonomy-stop'),
    autonomyStatus: () => ipcRenderer.invoke('lab-autonomy-status'),
  },

  // ZARA Lab V1 — channels and payloads match frontend/dist-electron/preload.js.
  labV1: {
    roomMessage: (sessionId?: string, content?: string, requestId?: string) =>
      ipcRenderer.invoke('lab-v1-room-message', { session_id: sessionId, content, request_id: requestId }),
    snapshot: (sessionId?: string, teamId?: string) =>
      ipcRenderer.invoke('lab-v1-snapshot', { session_id: sessionId, team_id: teamId }),
    proposalList: () => ipcRenderer.invoke('lab-v1-proposal-list', {}),
    proposalUpdate: (payload: { proposalId?: string; state?: string } | Record<string, any>) =>
      ipcRenderer.invoke('lab-v1-proposal-update', {
        proposal_id: (payload as any).proposalId,
        state: (payload as any).state,
      }),
    createSession: (objective: string, teamId?: string) =>
      ipcRenderer.invoke('lab-v1-create-session', { objective, team_id: teamId }),
    submit: (sessionId: string, text: string, requestId?: string) =>
      ipcRenderer.invoke('lab-v1-submit', { session_id: sessionId, text, request_id: requestId }),
    autopilot: (intent: string, requestId?: string) =>
      ipcRenderer.invoke('lab-v1-autopilot', { intent, request_id: requestId }),
    activateAutopilot: () => ipcRenderer.invoke('lab-v1-autopilot-activate'),
    configureAutonomy: (enabled: boolean) =>
      ipcRenderer.invoke('lab-v1-autonomy-configure', { enabled }),
    cancelMission: (sessionId: string, requestId?: string) =>
      ipcRenderer.invoke('lab-v1-cancel-mission', { session_id: sessionId, request_id: requestId }),
    deleteSession: (sessionId: string) => ipcRenderer.invoke('lab-v1-delete-session', { session_id: sessionId }),
    providers: () => ipcRenderer.invoke('lab-v1-providers'),
    createAgent: (payload: Record<string, any>) => ipcRenderer.invoke('lab-v1-create-agent', payload),
    configureAgent: (payload: Record<string, any>) => ipcRenderer.invoke('lab-v1-configure-agent', payload),
    agentProfile: (agentId: string) => ipcRenderer.invoke('lab-v1-agent-profiles', { agent_id: agentId }),
    updateAgentProfile: (payload: Record<string, any>) => ipcRenderer.invoke('lab-v1-agent-profile-update', payload),
    rollbackAgentProfile: (agentId: string, version: number) =>
      ipcRenderer.invoke('lab-v1-agent-profile-rollback', { agent_id: agentId, version }),
    archiveAgent: (agentId: string) => ipcRenderer.invoke('lab-v1-archive-agent', { agent_id: agentId }),
    rebindRole: (payload: Record<string, any>) => ipcRenderer.invoke('lab-v1-rebind-role', payload),
    researchSkill: (payload: Record<string, any>) => ipcRenderer.invoke('lab-v1-research-skill', payload),
    teamChat: (payload: Record<string, any>) => ipcRenderer.invoke('lab-v1-team-chat', payload),
  },

  // Conselheira — chat contínuo com a zoe via ponte Gmail
  conselheira: {
    sendMessage: (payload: { text: string }) => ipcRenderer.invoke('conselheira-send', payload),
    sync: () => ipcRenderer.invoke('conselheira-sync'),
    getMessages: (payload?: { limit?: number }) => ipcRenderer.invoke('conselheira-messages', payload),
    getStatus: () => ipcRenderer.invoke('conselheira-status'),
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
    voiceOutputAudio: (callback: (data: any) => void) => {
      const handler = (_event: any, data: any) => callback(data || {})
      ipcRenderer.on('voice-output-audio', handler)
      return () => ipcRenderer.off('voice-output-audio', handler)
    },
    zoeVoiceInput: (callback: (data: { text: string }) => void) => {
      const handler = (_event: any, data: { text: string }) => callback(data)
      ipcRenderer.on('zoe-voice-input', handler)
      return () => ipcRenderer.off('zoe-voice-input', handler)
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
    routingTelemetry: (callback: (telemetry: any) => void) => {
      const handler = (_event: unknown, telemetry: any) => callback(telemetry)
      ipcRenderer.on('routing-telemetry', handler)
      return () => ipcRenderer.off('routing-telemetry', handler)
    },
    labOperationResult: (callback: (event: any) => void) => {
      const handler = (_event: unknown, result: any) => callback(result || {})
      ipcRenderer.on('lab-v1-operation-result', handler)
      return () => ipcRenderer.off('lab-v1-operation-result', handler)
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

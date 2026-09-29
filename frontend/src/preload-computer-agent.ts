// Preload do computer-agent (use-computer) — Frente B.
//
// ARQUIVO SEPARADO DE PROPÓSITO: o `main.ts` é território da Frente C.
// Este arquivo NÃO é referenciado por nada ainda — a Frente C escolhe como
// integrar (ver CONTRATO-FRENTE-C.md, seção "Preload"):
//   Opção A (recomendada): copiar o objeto `computerAgentAPI` para dentro do
//            `zaraAPI` no `preload.ts`, como `computerAgent: { ... }`.
//   Opção B: compilar este arquivo como segundo preload (adicionar em
//            `tsconfig.node.json` + fundir no build do electron).
// O renderer aceita os dois caminhos: `window.zaraComputerAgent` ou
// `window.zaraIPC.computerAgent` (ver `computerAgentBridge.ts`).

import { contextBridge, ipcRenderer } from 'electron'

export interface ComputerAgentStartedPayload {
  goal: string
}

export interface ComputerAgentStepPayload {
  step: string
  index?: number
  total?: number
}

export interface ComputerAgentStoppedPayload {
  goal?: string
  success?: boolean
  refused?: boolean
  verified?: boolean
  /** Quantidade de passos executados (o backend manda o número, não a lista). */
  steps?: number
  error?: string | null
}

function subscribe<T>(channel: string, callback: (data: T) => void): () => void {
  const handler = (_event: any, data: T) => callback(data)
  ipcRenderer.on(channel, handler)
  return () => {
    ipcRenderer.off(channel, handler)
  }
}

const computerAgentAPI = {
  /** Dispara o agente: o main repassa ao backend como IPC `computer-agent-run`. */
  run: (goal: string) => ipcRenderer.invoke('computer-agent-run', { goal }),
  /** Pede ao main para mostrar a janela de overlay (borda colorida). */
  showOverlay: () => ipcRenderer.invoke('computer-agent-overlay-show'),
  /** Pede ao main para esconder/destruir a janela de overlay. */
  hideOverlay: () => ipcRenderer.invoke('computer-agent-overlay-hide'),
  /** O backend começou a usar o PC. */
  onStarted: (callback: (data: ComputerAgentStartedPayload) => void) =>
    subscribe<ComputerAgentStartedPayload>('computer-agent-started', callback),
  /** Passo atual da execução (vem do backend). */
  onStep: (callback: (data: ComputerAgentStepPayload) => void) =>
    subscribe<ComputerAgentStepPayload>('computer-agent-step', callback),
  /** O backend terminou de usar o PC. */
  onStopped: (callback: (data: ComputerAgentStoppedPayload) => void) =>
    subscribe<ComputerAgentStoppedPayload>('computer-agent-stopped', callback),
}

contextBridge.exposeInMainWorld('zaraComputerAgent', computerAgentAPI)

// Tipo público da ponte (o renderer referencia via `global.d.ts`).
declare global {
  interface Window {
    zaraComputerAgent: typeof computerAgentAPI
  }
}

export {}

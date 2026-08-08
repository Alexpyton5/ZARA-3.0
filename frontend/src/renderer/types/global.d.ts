/// <reference types="vite/client" />

interface ZaraWindowControl {
  minimize: () => Promise<void>;
  maximize: () => Promise<void>;
  close: () => Promise<void>;
}

declare global {
  interface Window {
    zaraIPC: {
      engine?: { change?: (engine: string) => Promise<any>; list?: () => Promise<any> };
      supercerebro?: { toggle?: (active: boolean) => Promise<any>; status?: () => Promise<any> };
      message?: { send?: (payload: { message: string; engine: string; history: Array<{ role: string; content: string }> }) => Promise<any>; interrupt?: () => Promise<any> };
      action?: { execute?: (action: string, params: Record<string, any>) => Promise<any>; list?: () => Promise<any> };
      system?: { metrics?: () => Promise<any>; info?: () => Promise<any> };
      voice?: { start?: () => Promise<any>; stop?: () => Promise<any>; status?: () => Promise<any> };
      config?: { get?: () => Promise<any>; set?: (key: string, value: any) => Promise<any> };
      lab?: {
        state?: () => Promise<any>;
        send?: (payload: { author: string; target: string; content: string }) => Promise<any>;
        createProposal?: (payload: { title: string; summary: string; risk: string; owner: string }) => Promise<any>;
        decideProposal?: (payload: { id: string; decision: 'APPROVE' | 'REJECT' }) => Promise<any>;
      };
      window?: ZaraWindowControl;
      on?: {
        stateChange?: (callback: (state: string) => void) => () => void;
        message?: (callback: (message: { role: string; content: string }) => void) => () => void;
        metrics?: (callback: (metrics: any) => void) => () => void;
        voiceLevel?: (callback: (level: number, tone: number, speaking: boolean) => void) => () => void;
        supercerebroChange?: (callback: (active: boolean) => void) => () => void;
      };
    };
  }
}

export {};

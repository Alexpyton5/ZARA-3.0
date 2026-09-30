/**
 * Fiação da interface nova — hooks tipados sobre `window.zaraIPC`.
 *
 * REGRA: só canais que existem de verdade no `preload.ts` (verificado).
 * O que o frontend expõe mas o backend NÃO tem handler registrado
 * (manual §8.1/§8.2) leva `TODO(CODEX)` explícito — nunca é usado como
 * se funcionasse.
 */

import { useCallback, useEffect, useState } from 'react';
import React from 'react';
// DEPENDÊNCIA EXTERNA (Frente B): este arquivo vive em
// `frontend/src/renderer/components/computer-agent/computerAgentBridge.ts`
// no código-fonte real e AINDA NÃO foi copiado para `entrega/` —
// na árvore real o import resolve; em `entrega/` standalone, não.
// O PORTÃO coloca o arquivo no lugar na integração. NÃO duplicar aqui
// (duas cópias divergem — a fonte de verdade é a da Frente B).
import { getComputerAgentBridge } from '../components/computer-agent/computerAgentBridge';

/* ------------------------------------------------------------------ */
/* Supercérebro                                                        */
/* ------------------------------------------------------------------ */

export interface SupercerebroStatus {
  /** true = chave ligada (o Alex está monitorando). */
  active: boolean;
  /** true = o backend ainda não confirmou o estado (canal morto ou lento). */
  unknown: boolean;
  toggle: () => Promise<void>;
}

export function useSupercerebroStatus(): SupercerebroStatus {
  const [active, setActive] = useState(false);
  const [unknown, setUnknown] = useState(true);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let mounted = true;
    // TODO(CODEX): 'supercerebro-status' existe no preload mas NÃO está
    // registrado no handler_map do backend (manual §8.1) — hoje cai em
    // "[IPC] Unknown message type" e o promise expira no timeout.
    // Decidir: registrar handle_supercerebro_status no mapa ou remover a chamada.
    window.zaraIPC?.supercerebro
      ?.status?.()
      .then((s: any) => {
        if (mounted && s && typeof s.active === 'boolean') {
          setActive(s.active);
          setUnknown(false);
        }
      })
      .catch(() => {
        /* mantém unknown=true até o evento supercerebro-change chegar */
      });
    const unsub = window.zaraIPC?.on?.supercerebroChange?.((v: boolean) => {
      if (mounted) {
        setActive(!!v);
        setUnknown(false);
      }
    });
    return () => {
      mounted = false;
      unsub?.();
    };
  }, []);

  const toggle = useCallback(async () => {
    if (busy) return;
    const sc = window.zaraIPC?.supercerebro;
    if (!sc?.toggle) return;
    // TODO(CODEX): 'supercerebro-toggle' existe no preload mas NÃO está
    // registrado no handler_map do backend (manual §8.1). Registrar
    // handle_supercerebro_toggle no mapa ou remover a chamada.
    setBusy(true);
    try {
      const r: any = await sc.toggle(!active);
      if (r && typeof r.active === 'boolean') {
        setActive(r.active);
        setUnknown(false);
      }
    } catch {
      /* o estado real chega pelo evento supercerebro-change */
    } finally {
      setBusy(false);
    }
  }, [active, busy]);

  return { active, unknown, toggle };
}

/* ------------------------------------------------------------------ */
/* Voz — motor de TTS                                                  */
/* ------------------------------------------------------------------ */

export type VoiceEngineId = 'kore' | 'omnivoice';

export interface VoiceEngine {
  engine: VoiceEngineId;
  omnivoiceAvailable: boolean;
  busy: boolean;
  setEngine: (engine: VoiceEngineId) => Promise<boolean>;
  /**
   * Pede ao backend para falar um texto pela cascata de TTS.
   * TODO(CODEX): 'zoe-voice-speak' NÃO tem handler registrado no backend
   * (manual §8.2) — hoje cai em "Unknown message type" e nunca vira fala.
   * Decidir: registrar o handler (ligando o texto à cascata de TTS) ou
   * remover a chamada. A voz que o Alex ouve hoje vem pelo EVENTO
   * 'voice-output-audio', que continua funcionando.
   */
  speak: (text: string) => Promise<void>;
}

export function useVoiceEngine(): VoiceEngine {
  const [engine, setEngineState] = useState<VoiceEngineId>('kore');
  const [omnivoiceAvailable, setOmnivoiceAvailable] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let mounted = true;
    window.zaraIPC?.voice
      ?.getEngine?.()
      .then((result: any) => {
        if (!mounted || !result?.success) return;
        setEngineState(result.engine === 'omnivoice' ? 'omnivoice' : 'kore');
        setOmnivoiceAvailable(Boolean(result.omnivoice_available));
      })
      .catch(() => {
        /* motor desconhecido até o backend responder */
      });
    return () => {
      mounted = false;
    };
  }, []);

  const setEngine = useCallback(async (next: VoiceEngineId): Promise<boolean> => {
    setBusy(true);
    try {
      const result: any = await window.zaraIPC?.voice?.setEngine?.(next);
      if (result?.success !== true) return false;
      setEngineState(next);
      return true;
    } finally {
      setBusy(false);
    }
  }, []);

  const speak = useCallback(async (text: string): Promise<void> => {
    const result: any = await window.zaraIPC?.voice?.speakZoe?.(text);
    if (result?.success !== true) {
      throw new Error(result?.error || 'A voz da ZARA não respondeu (canal zoe-voice-speak sem handler no backend).');
    }
  }, []);

  return { engine, omnivoiceAvailable, busy, setEngine, speak };
}

/* ------------------------------------------------------------------ */
/* Computer-agent (use-computer) — via ponte existente                  */
/*                                                                     */
/* A trava fail-closed do supercérebro continua intacta: sem a chave,   */
/* o backend recusa (evento stopped com refused=true) — ver            */
/* CONTRATO-FRENTE-C.md §2. Este hook SÓ CHAMA a ponte existente,       */
/* nunca reimplementa controle do PC.                                  */
/* ------------------------------------------------------------------ */

export interface ComputerAgentCommand {
  /** true enquanto o agente está executando no PC. */
  running: boolean;
  /** Objetivo que disparou a execução atual (vem do evento started). */
  goal: string;
  /** Passo atual informado pelo backend (pode vir vazio — ver CONTRATO). */
  step: string;
  /** true quando o backend recusou (ex.: supercérebro desligado). */
  refused: boolean;
  /** Erro honesto da última tentativa (null = sem erro). */
  error: string | null;
  /** true quando o preload ainda não expôs a ponte (Frente C não ligou). */
  bridgeMissing: boolean;
  run: (goal: string) => Promise<void>;
  clearError: () => void;
}

export function useComputerAgent(): ComputerAgentCommand {
  const [running, setRunning] = useState(false);
  const [goal, setGoal] = useState('');
  const [step, setStep] = useState('');
  const [refused, setRefused] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [bridgeMissing, setBridgeMissing] = useState(false);

  useEffect(() => {
    const bridge = getComputerAgentBridge();
    if (!bridge) {
      setBridgeMissing(true);
      return;
    }
    setBridgeMissing(false);
    const offStarted = bridge.onStarted((data) => {
      setRunning(true);
      setRefused(false);
      setError(null);
      setGoal(typeof data?.goal === 'string' ? data.goal : '');
      setStep('');
    });
    const offStep = bridge.onStep((data) => {
      setStep(typeof data?.step === 'string' ? data.step : '');
    });
    const offStopped = bridge.onStopped((data) => {
      setRunning(false);
      setStep('');
      const wasRefused = data?.refused === true;
      setRefused(wasRefused);
      if (wasRefused) {
        setError(data?.error || 'O supercérebro está desligado: o agente recusou mexer no computador.');
      } else if (data?.success === false) {
        setError(data?.error || 'A ação no computador não foi concluída.');
      }
    });
    return () => {
      offStarted();
      offStep();
      offStopped();
    };
  }, []);

  const run = useCallback(async (nextGoal: string) => {
    const clean = nextGoal.trim();
    if (!clean) {
      setError('Diga o que você quer que seja feito no computador.');
      return;
    }
    const bridge = getComputerAgentBridge();
    if (!bridge) {
      setBridgeMissing(true);
      setError('O controle do computador não está disponível nesta versão do app.');
      return;
    }
    setError(null);
    setRefused(false);
    try {
      await bridge.run(clean);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Não foi possível enviar o comando.');
    }
  }, []);

  const clearError = useCallback(() => {
    setError(null);
    setRefused(false);
  }, []);

  return { running, goal, step, refused, error, bridgeMissing, run, clearError };
}

/* ------------------------------------------------------------------ */
/* Ponte remota da zoe (Tailscale) — NOVO REQUISITO do Alex (30/09)    */
/*                                                                     */
/* Canal real: `zoeBridge.status` no preload → o main responde          */
/* `{ ready: boolean }` (main.ts:966) — true = a ponte HTTP da zoe      */
/* (Bearer <redacted>) está no ar e o backend está pronto. Por essa ponte a  */
/* zoe opera o PC de fora (via Tailscale), usando as MESMAS ações       */
/* "computer_*" e "vision_*" do backend — não existe canal "remoto"     */
/* separado no renderer, nem precisa: a operação remota passa pelo      */
/* mesmo pipeline seguro, com a trava fail-closed do supercérebro       */
/* intacta. Este hook só EXPÕE o estado da ponte; não executa nada.     */
/* ------------------------------------------------------------------ */

export function useZoeBridgeStatus(): { ready: boolean; unknown: boolean } {
  const [ready, setReady] = useState(false);
  const [unknown, setUnknown] = useState(true);

  useEffect(() => {
    let mounted = true;
    window.zaraIPC?.zoeBridge
      ?.status?.()
      .then((s: any) => {
        if (mounted && s && typeof s.ready === 'boolean') {
          setReady(s.ready);
          setUnknown(false);
        }
      })
      .catch(() => {
        /* ponte desconhecida até o main responder */
      });
    return () => {
      mounted = false;
    };
  }, []);

  return { ready, unknown };
}

/* ------------------------------------------------------------------ */
/* Ponto de entrada "Operar o computador" (Fase 4 da missão)           */
/*                                                                     */
/* Botão discreto que abre o posto de comando do use-computer pela     */
/* interface nova. Chama SOMENTE a ponte existente (run/showOverlay);  */
/* a trava fail-closed do supercérebro continua no backend — sem ela,   */
/* o agente recusa e a recusa aparece na tela, sem fingir execução.     */
/* ------------------------------------------------------------------ */

const btnStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: '8px',
  padding: '9px 16px',
  borderRadius: '999px',
  border: '1px solid var(--borda, #e3d9c8)',
  background: 'var(--fundo-cartao, #fffdf8)',
  color: 'var(--txt-1, #3b2f23)',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
};

const popStyle: React.CSSProperties = {
  position: 'absolute',
  bottom: 'calc(100% + 10px)',
  right: 0,
  width: '300px',
  padding: '14px',
  borderRadius: '14px',
  border: '1px solid var(--borda, #e3d9c8)',
  background: 'var(--fundo-cartao, #fffdf8)',
  boxShadow: '0 12px 32px rgba(60,40,20,0.16)',
  zIndex: 50,
};

export const BotaoOperarComputador: React.FC = () => {
  const agent = useComputerAgent();
  const ponte = useZoeBridgeStatus();
  const [open, setOpen] = useState(false);
  const [pedido, setPedido] = useState('');

  const executar = () => {
    const clean = pedido.trim();
    // Validação local: com pedido vazio ou ponte ausente, mantém o painel
    // aberto para o erro honesto aparecer (fechar esconderia o erro).
    if (!clean || agent.bridgeMissing) {
      void agent.run(pedido);
      return;
    }
    void agent.run(clean);
    setOpen(false);
    setPedido('');
  };

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      {open && (
        <div style={popStyle}>
          <div style={{ fontSize: '13px', fontWeight: 700, marginBottom: '8px', color: 'var(--txt-1, #3b2f23)' }}>
            Operar o computador
          </div>
          <div style={{ fontSize: '12px', color: 'var(--txt-2, #8a7a63)', marginBottom: '10px' }}>
            O que deve ser feito no PC?
          </div>
          <input
            value={pedido}
            onChange={(e) => setPedido(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') executar();
            }}
            placeholder="Ex.: abrir o bloco de notas"
            autoFocus
            style={{
              width: '100%',
              boxSizing: 'border-box',
              padding: '9px 12px',
              borderRadius: '10px',
              border: '1px solid var(--borda, #e3d9c8)',
              fontSize: '13px',
              marginBottom: '10px',
            }}
          />
          <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
            <button type="button" onClick={() => setOpen(false)} style={{ ...btnStyle, padding: '7px 12px' }}>
              Cancelar
            </button>
            <button
              type="button"
              onClick={executar}
              disabled={agent.running || agent.bridgeMissing}
              style={{ ...btnStyle, padding: '7px 12px', opacity: agent.running || agent.bridgeMissing ? 0.5 : 1 }}
            >
              {agent.running ? 'Executando…' : 'Executar'}
            </button>
          </div>
          {agent.error && (
            <div style={{ marginTop: '10px', fontSize: '12px', color: '#b3261e' }}>{agent.error}</div>
          )}
          {agent.bridgeMissing && (
            <div style={{ marginTop: '10px', fontSize: '12px', color: '#b3261e' }}>
              O controle do computador ainda não foi ligado nesta versão do app.
            </div>
          )}
          <div style={{ marginTop: '10px', fontSize: '11px', color: 'var(--txt-2, #8a7a63)' }}>
            {ponte.unknown
              ? 'Ponte remota da zoe: verificando…'
              : ponte.ready
                ? 'Ponte remota da zoe: ligada — ela pode operar o PC de fora (Tailscale).'
                : 'Ponte remota da zoe: desligada — o controle funciona só aqui no PC.'}
          </div>
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title="Pedir para o motor da ZARA operar o computador"
        style={btnStyle}
      >
        <span aria-hidden="true" style={{ fontSize: '15px' }}>▣</span>
        {agent.running ? 'Operando o computador…' : 'Operar o computador'}
      </button>
      {agent.running && agent.goal && (
        <div style={{ fontSize: '11px', color: 'var(--txt-2, #8a7a63)', marginTop: '4px', maxWidth: '260px' }}>
          {agent.step || agent.goal}
        </div>
      )}
      {/* Erro fora do painel: o painel fecha ao executar, então o erro da
          execução aparece aqui embaixo do botão, nunca some em silêncio. */}
      {agent.error && !open && (
        <div style={{ fontSize: '11px', color: '#b3261e', marginTop: '4px', maxWidth: '260px' }}>
          {agent.error}
        </div>
      )}
    </div>
  );
};

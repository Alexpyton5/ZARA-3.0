/**
 * Fiação da interface nova — hooks tipados sobre `window.zaraIPC`.
 *
 * REGRA: só canais que existem de verdade no `preload.ts` (verificado).
 * O que o frontend expõe mas o backend NÃO tem handler registrado
 * (manual §8.1/§8.2) leva `TODO(CODEX)` explícito — nunca é usado como
 * se funcionasse.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
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
    // Consulta o estado autoritativo pelo IPC; se falhar, mantém estado desconhecido.
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
    // O backend confirma o estado; eventos também atualizam a tela.
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

export type VoiceEngineId = 'kore';

export interface VoiceEngine {
  engine: VoiceEngineId;
  busy: boolean;
  /**
   * Pede ao backend para falar um texto; resolve após a reprodução ser confirmada.
   */
  speak: (text: string) => Promise<void>;
}

export function useVoiceEngine(): VoiceEngine {
  const [engine, setEngineState] = useState<VoiceEngineId>('kore');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let mounted = true;
    window.zaraIPC?.voice
      ?.getEngine?.()
      .then((result: any) => {
        if (!mounted || !result?.success) return;
        setEngineState('kore');
      })
      .catch(() => {
        /* motor desconhecido até o backend responder */
      });
    return () => {
      mounted = false;
    };
  }, []);

  const speak = useCallback(async (text: string): Promise<void> => {
    setBusy(true);
    try {
      const result: any = await window.zaraIPC?.voice?.speakZoe?.(text);
      if (result?.success !== true) {
        throw new Error(result?.error || 'O motor não confirmou a fala.');
      }
    } finally {
      setBusy(false);
    }
  }, []);

  return { engine, busy, speak };
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
  busy: boolean;
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
  run: (goal: string) => Promise<boolean>;
  clearError: () => void;
}

export function useComputerAgent(): ComputerAgentCommand {
  const pending = useRef(false);
  const [busy, setBusy] = useState(false);
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
    if (pending.current || running) return false;
    const clean = nextGoal.trim();
    if (!clean) {
      setError('Diga o que você quer que seja feito no computador.');
      return false;
    }
    const bridge = getComputerAgentBridge();
    if (!bridge) {
      setBridgeMissing(true);
      setError('O controle do computador não está disponível nesta versão do app.');
      return false;
    }
    setError(null);
    setRefused(false);
    pending.current = true; setBusy(true);
    try {
      const result = await bridge.run(clean) as { success?: boolean; verified?: boolean; error?: string };
      if (result?.success !== true) {
        setError(result?.error || 'O executor não confirmou a conclusão.');
        return false;
      }
      if (result.verified !== true) setError('O executor terminou, mas o efeito na tela ainda não foi confirmado.');
      return true;
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Não foi possível enviar o comando.');
      return false;
    } finally {
      pending.current = false; setBusy(false);
    }
  }, [running]);

  const clearError = useCallback(() => {
    setError(null);
    setRefused(false);
  }, []);

  return { running, busy, goal, step, refused, error, bridgeMissing, run, clearError };
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

  const executar = async () => {
    const clean = pedido.trim();
    // Validação local: com pedido vazio ou ponte ausente, mantém o painel
    // aberto para o erro honesto aparecer (fechar esconderia o erro).
    if (!clean || agent.bridgeMissing) {
      void agent.run(pedido);
      return;
    }
    if (await agent.run(clean)) { setOpen(false); setPedido(''); }
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
              disabled={agent.busy || agent.running || agent.bridgeMissing || !pedido.trim()}
              style={{ ...btnStyle, padding: '7px 12px', opacity: agent.running || agent.bridgeMissing ? 0.5 : 1 }}
            >
              {agent.running ? 'Executando…' : agent.busy ? 'Enviando…' : 'Executar'}
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
                ? 'Canal do motor disponível. A conexão pela rede precisa estar configurada.'
                : 'Canal remoto indisponível.'}
          </div>
        </div>
      )}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        title="Pedir para o motor da TROPA dev. operar o computador"
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

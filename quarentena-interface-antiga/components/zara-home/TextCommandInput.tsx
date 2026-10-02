import { useEffect, useRef, useState } from 'react';
import { Monitor, Send } from 'lucide-react';
import zaraLogo from '../../../assets/zara-home/zara-mark.svg';
import { normalizeHistoryResponse } from '../../lib/chatHistory';
import { COMPUTER_TRIGGER_PREFIX, extractComputerGoal } from '../../lib/computerAgentTrigger';
import { getComputerAgentBridge } from '../computer-agent/computerAgentBridge';
import { errorMessage } from './homeActions';
import { BrainSelector, useBrainSelection } from './BrainSelector';
import { validateFrontBrainProvenance } from './frontBrainProvenance';
import './brain-selector.css';

interface TextCommandInputProps {
  /** Retained for existing callers; the persisted selection is authoritative. */
  engine?: string;
  onSent?: (message: string) => void;
}

/** Uses the persisted front brain and bounded local conversation context. */
export function TextCommandInput({ onSent }: TextCommandInputProps) {
  const [value, setValue] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');
  const selection = useBrainSelection();
  const pending = useRef(false);
  const mounted = useRef(true);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  // Provider availability does not gate deterministic PC commands; the backend routes them.
  const canSend = value.trim().length > 0 && !sending && !selection.busy && selection.selected !== null && Boolean(window.zaraIPC?.message?.send);
  const notice = selection.error || error || (!selection.busy && !selection.available ? selection.status : '');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const message = value.trim();
    if (!canSend || !message || !window.zaraIPC?.message?.send || pending.current) return;

    pending.current = true;
    setSending(true);
    setError('');
    let confirmed = false;
    try {
      const computerGoal = extractComputerGoal(message);
      if (computerGoal !== null) {
        // Gatilho "use o computador para ...": vai para o computer-agent,
        // não para a conversa.
        await submitComputerAgentGoal(computerGoal);
      } else {
        const [configuration, transcript] = await Promise.allSettled([
          selection.readCurrent(), window.zaraIPC.conversationHistory?.list?.(20),
        ]);
        if (configuration.status === 'rejected') throw configuration.reason;
        const selected = configuration.value;
        const history = normalizeHistoryResponse(transcript.status === 'fulfilled' ? transcript.value : undefined)
          .slice(-20).map(({ role, content }) => ({ role, content }));
        if (!mounted.current) return;
        const response = await window.zaraIPC.message.send({ message, engine: selected, history });
        validateFrontBrainProvenance(response, selected);
        if (response?.success === false || response?.error || typeof response?.response !== 'string') {
          throw new Error(response?.error || 'O envio não foi confirmado.');
        }
      }
      if (!mounted.current) return;
      setValue('');
      confirmed = true;
    } catch (cause) {
      if (mounted.current) {
        setError(errorMessage(cause, 'O envio não foi confirmado.'));
        void selection.refresh();
      }
    } finally {
      pending.current = false;
      if (mounted.current) setSending(false);
    }
    if (confirmed && mounted.current) {
      // A real reply may have proved the selected model; refresh its observed status.
      void selection.refresh();
      try {
        await onSent?.(message);
      } catch {
        if (mounted.current) setError('Mensagem enviada. Reabra a conversa para atualizar o histórico.');
      }
    }
  }

  /**
   * Gatilho "use o computador para ...": envia `computer-agent-run` com o goal
   * para o backend em vez de mandar como mensagem de chat (Frente B).
   */
  async function submitComputerAgentGoal(goal: string): Promise<void> {
    if (!goal) {
      throw new Error(`Descreva o que a ZARA deve fazer depois de "${COMPUTER_TRIGGER_PREFIX}".`);
    }
    const bridge = getComputerAgentBridge();
    if (!bridge) {
      throw new Error('O controle do PC ainda está ligando nesta versão. Tente de novo em instantes.');
    }
    const result = await bridge.run(goal);
    if (result && typeof result === 'object' && 'error' in result) {
      const message = (result as { error?: unknown }).error;
      if (message) throw new Error(String(message));
    }
  }

  /** Botão discreto "usar PC": insere o prefixo do gatilho e foca o campo. */
  function insertComputerTriggerPrefix() {
    setValue((current) => {
      const trimmed = current.trimStart();
      if (trimmed.toLowerCase().startsWith(COMPUTER_TRIGGER_PREFIX)) return current;
      return current ? `${COMPUTER_TRIGGER_PREFIX} ${current}` : `${COMPUTER_TRIGGER_PREFIX} `;
    });
    setError('');
    inputRef.current?.focus();
  }

  return (
    <form className="zh-command-form zh-command-form--brains zh-glass-panel" onSubmit={handleSubmit} aria-busy={sending || selection.busy}>
      <img src={zaraLogo} alt="" aria-hidden="true" />
      <input
        ref={inputRef}
        className="zh-command-input"
        placeholder="Como posso ajudar?"
        value={value}
        disabled={sending}
        onChange={(e) => setValue(e.target.value)}
        aria-label="Como posso ajudar?"
      />
      <BrainSelector selection={selection} disabled={sending} />
      <button
        className="zh-command-pc"
        type="button"
        disabled={sending}
        title="Usar o computador"
        aria-label="Usar o computador"
        onClick={insertComputerTriggerPrefix}
      >
        <Monitor aria-hidden="true" />
      </button>
      <button className="zh-command-submit" type="submit" disabled={!canSend} aria-label={sending ? 'Enviando mensagem' : 'Enviar mensagem'}>
        <Send aria-hidden="true" />
      </button>
      {notice && <span className="zh-command-error" role="alert">
        {notice}
        {(selection.error || !selection.available) && <button type="button" disabled={sending || selection.busy} onClick={() => { void selection.refresh(); }}>Atualizar cérebros</button>}
      </span>}
    </form>
  );
}

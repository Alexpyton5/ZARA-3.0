import { useState } from 'react';
import { AudioLines } from 'lucide-react';
import { cortarKore } from '../../lib/aecAudio';
import zaraLogo from '../../../assets/zara-home/zara-logo-transparent.png';

interface TextCommandInputProps {
  engine?: string;
  onSent?: (message: string) => void;
}

/**
 * Campo "Como posso ajudar?" — envia pelo MESMO canal IPC que o resto da
 * ZARA já usa para texto (`window.zaraIPC.message.send`), sem pipeline
 * paralelo. `history` vazio aqui de propósito: esta Home não mantém thread
 * de conversa própria ainda: cada envio é uma mensagem nova para o fluxo de
 * intent/Planner/ToolRouter existente, que já lida com contexto no backend.
 */
export function TextCommandInput({ engine = 'auto', onSent }: TextCommandInputProps) {
  const [value, setValue] = useState('');
  const [sending, setSending] = useState(false);

  const canSend = value.trim().length > 0 && !sending && Boolean(window.zaraIPC?.message?.send);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const message = value.trim();
    if (!message || !window.zaraIPC?.message?.send) return;

    setSending(true);
    try {
      // ZARA-BARGE-IN-TEXTO-001: se a ZARA estiver falando quando o Alex
      // digita, ela tem que calar e ouvir — mesma regra do "Zara, pare" e do
      // botão de voz. Antes só a voz interrompia; pelo texto ela continuava
      // falando por cima da própria resposta anterior. Cortar quando não há
      // áudio tocando é inofensivo.
      cortarKore();
      try {
        await window.zaraIPC?.message?.interrupt?.();
      } catch {
        // Áudio já foi cortado no cliente; avisar o backend é best-effort.
      }

      await window.zaraIPC.message.send({ message, engine, history: [] });
      onSent?.(message);
      setValue('');
    } finally {
      setSending(false);
    }
  }

  return (
    <form className="zh-command-form zh-glass-panel" onSubmit={handleSubmit}>
      <img src={zaraLogo} alt="" aria-hidden="true" />
      <input
        className="zh-command-input"
        placeholder="Como posso ajudar?"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        aria-label="Como posso ajudar?"
      />
      <button className="zh-command-submit" type="submit" disabled={!canSend} aria-label="Enviar mensagem">
        <span className="zh-command-waveform" aria-hidden="true">
          {[8, 14, 20, 11, 18, 9, 16, 7, 13].map((height, index) => (
            <span key={index} className="zh-command-wave-bar" style={{ height }} />
          ))}
        </span>
        <AudioLines size={1} aria-hidden="true" />
      </button>
    </form>
  );
}

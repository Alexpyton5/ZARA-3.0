import { useCallback, useEffect, useRef, useState } from 'react';
import { X, ArrowRight } from 'lucide-react';

export interface Turn {
  id: number;
  role: 'user' | 'assistant' | 'system';
  content: string;
  engine?: string;
}

/**
 * Onde a resposta da ZARA aparece na Home.
 *
 * O campo "Como posso ajudar?" enviava a mensagem e DESCARTAVA a resposta: o
 * Alex digitava "que horas são?" e não via nada acontecer na tela. Por texto
 * a resposta volta no retorno do próprio `message.send` (ver
 * `handle_send_message` -> `send_response({response, engine})`); por voz ela
 * chega como evento `message`. As duas entradas alimentam a mesma tira aqui,
 * pela mesma regra de "voz e texto compartilham a cadeia".
 *
 * Não é um chat novo nem uma thread paralela: é a leitura do que o backend já
 * respondeu. O histórico completo continua sendo a seção Conversas.
 */
export function useConversationFeed(limit = 6) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const nextId = useRef(0);

  const push = useCallback((role: Turn['role'], content: string, engine?: string) => {
    const texto = String(content ?? '').trim();
    if (!texto) return;
    nextId.current += 1;
    const turn: Turn = { id: nextId.current, role, content: texto, engine };
    setTurns((prev) => [...prev, turn].slice(-limit));
  }, [limit]);

  // Caminho de VOZ: o backend emite `message` para user e assistant.
  useEffect(() => {
    const subscribe = window.zaraIPC?.on?.message;
    if (!subscribe) return;
    return subscribe((m: { role?: string; content?: string; engine?: string }) => {
      const role = m?.role === 'user' ? 'user' : m?.role === 'system' ? 'system' : 'assistant';
      push(role, String(m?.content ?? ''), m?.engine);
    });
  }, [push]);

  return { turns, push, clear: () => setTurns([]) };
}

export function ConversationStrip({
  turns, onClear, onSeeAll, pending,
}: { turns: Turn[]; onClear: () => void; onSeeAll: () => void; pending: boolean }) {
  const bottom = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'nearest' });
  }, [turns.length, pending]);

  if (turns.length === 0 && !pending) return null;

  return (
    <div className="zh-strip zh-glass-panel" role="log" aria-label="Última conversa">
      <div className="zh-strip-head">
        <span>Conversa</span>
        <button type="button" onClick={onSeeAll} className="zh-strip-all">
          Ver tudo <ArrowRight size={12} strokeWidth={2} />
        </button>
        <button type="button" onClick={onClear} className="zh-strip-close" aria-label="Fechar">
          <X size={13} strokeWidth={2} />
        </button>
      </div>
      <div className="zh-strip-body">
        {turns.map((t) => (
          <p key={t.id} className="zh-strip-turn" data-role={t.role}>
            <strong>{t.role === 'user' ? 'Você' : t.role === 'system' ? 'Sistema' : 'ZARA'}</strong>
            {t.content}
          </p>
        ))}
        {pending && <p className="zh-strip-turn zh-strip-pending"><strong>ZARA</strong>Pensando…</p>}
        <div ref={bottom} />
      </div>
    </div>
  );
}

import { useEffect, useState } from 'react';

export interface HomeSignal {
  key: string;
  kind: 'reminder' | 'reminders' | 'history' | 'memory';
  label: string;
  sub: string;
}

/** Os cards "Para você" mostravam pessoas e compromissos inventados
 *  ("João espera sua resposta", "Reunião às 14:00"). Aqui o conteúdo vem
 *  só de fontes que o backend REALMENTE tem: lembretes persistidos,
 *  histórico local e memória do usuário. Sem fonte, o card diz que não há
 *  nada — nunca preenche com exemplo. */
export function useHomeSignals(): { signals: HomeSignal[]; loading: boolean; connected: boolean } {
  const listReminders = window.zaraIPC?.reminders?.list;
  const listHistory = window.zaraIPC?.conversationHistory?.list;
  const listMemory = window.zaraIPC?.userMemory?.list;
  const connected = Boolean(listReminders || listHistory || listMemory);

  const [signals, setSignals] = useState<HomeSignal[]>([]);
  // Sem canal nenhum não há leitura pendente: isso é conclusão de render,
  // não algo a sincronizar dentro de um efeito.
  const [loading, setLoading] = useState(connected);

  useEffect(() => {
    if (!connected) return;
    let alive = true;

    async function safe<T>(fn: (() => Promise<T>) | undefined): Promise<T | null> {
      if (!fn) return null;
      try { return await fn(); } catch { return null; }
    }

    Promise.all([
      safe(listReminders ? () => listReminders() : undefined),
      safe(listHistory ? () => listHistory(200) : undefined),
      safe(listMemory ? () => listMemory() : undefined),
    ]).then(([rem, hist, mem]) => {
      if (!alive) return;
      const out: HomeSignal[] = [];

      const reminders: Array<{ id: string; message: string; due_at_utc: number; state: string }> =
        Array.isArray((rem as { reminders?: unknown })?.reminders) ? (rem as { reminders: never[] }).reminders : [];
      const pendentes = reminders
        .filter((r) => r.state === 'PENDING')
        .sort((a, b) => (a.due_at_utc || 0) - (b.due_at_utc || 0));

      const proximo = pendentes[0];
      if (proximo) {
        const quando = new Date(proximo.due_at_utc < 1e12 ? proximo.due_at_utc * 1000 : proximo.due_at_utc);
        const valido = !Number.isNaN(quando.getTime());
        out.push({
          key: `rem-${proximo.id}`,
          kind: 'reminder',
          label: proximo.message,
          sub: valido
            ? quando.toLocaleString('pt-BR', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
            : 'lembrete pendente',
        });
      }
      if (pendentes.length > 1) {
        out.push({
          key: 'rem-count',
          kind: 'reminders',
          label: `${pendentes.length} lembretes pendentes`,
          sub: 'Ver em Automações',
        });
      }

      const mensagens = Number((hist as { count?: number })?.count ?? 0);
      if (mensagens > 0) {
        out.push({
          key: 'hist',
          kind: 'history',
          label: `${mensagens} mensagens no histórico`,
          sub: 'Só neste computador',
        });
      }

      const fatos = Array.isArray((mem as { facts?: unknown[] })?.facts) ? (mem as { facts: unknown[] }).facts.length : 0;
      if (fatos > 0) {
        out.push({
          key: 'mem',
          kind: 'memory',
          label: `${fatos} fatos na memória`,
          sub: 'Você pode apagar qualquer um',
        });
      }

      setSignals(out.slice(0, 4));
      setLoading(false);
    });

    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected]);

  return { signals, loading, connected };
}

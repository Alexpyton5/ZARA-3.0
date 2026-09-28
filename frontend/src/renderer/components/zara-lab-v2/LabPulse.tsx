import { useMemo } from 'react';
import { label, type Snapshot } from './labTypes';

type PulseTone = 'on' | 'off' | 'idle';

function heartbeatAgeText(heartbeat?: number | null): string | null {
  if (!heartbeat || !Number.isFinite(heartbeat)) return null;
  const ms = heartbeat < 1e12 ? heartbeat * 1000 : heartbeat;
  const ageSec = Math.round((Date.now() - ms) / 1000);
  if (!Number.isFinite(ageSec) || ageSec < 0) return null;
  if (ageSec < 5) return 'agora mesmo';
  if (ageSec < 60) return `há ${ageSec} s`;
  const minutes = Math.floor(ageSec / 60);
  if (minutes < 60) return `há ${minutes} min`;
  return `há ${Math.floor(minutes / 60)} h`;
}

/**
 * Pulso do Lab — faixa viva no topo da sala mostrando se o supervisor do Lab
 * está ativo e há quanto tempo deu o último sinal.
 *
 * Tudo aqui vem do snapshot real do backend (atualizado a cada 3 s).
 * Nada é simulado: sem dados do backend, mostramos "sem dados" / "em pausa".
 */
export function LabPulse({ policy, loading, error }: {
  policy?: Snapshot['autonomy_policy'];
  loading: boolean;
  error: string;
}) {
  const pulse = useMemo(() => {
    if (error) {
      return { tone: 'off' as PulseTone, title: 'Lab sem conexão', detail: 'Não foi possível falar com o supervisor' };
    }
    if (loading || !policy) {
      return { tone: 'idle' as PulseTone, title: 'Lab', detail: 'Conectando ao supervisor…' };
    }
    const live = policy.background_task_state === 'RUNNING' && policy.last_state !== 'FAILED';
    if (!live) {
      return {
        tone: 'off' as PulseTone,
        title: 'Lab em pausa',
        detail: policy.background_error
          ? 'Supervisor com erro'
          : `Supervisor ${label(policy.background_task_state).toLowerCase()}`,
      };
    }
    const age = heartbeatAgeText(policy.last_heartbeat ?? policy.last_tick);
    return {
      tone: 'on' as PulseTone,
      title: 'Lab ativo',
      detail: age ? `Último sinal ${age}` : 'Supervisor em andamento',
    };
  }, [policy, loading, error]);

  return (
    <div className={`zl-pulse zl-pulse--${pulse.tone}`} role="status" aria-label={`Pulso do Lab: ${pulse.title}. ${pulse.detail}`}>
      <span className="zl-pulse-dot" aria-hidden="true" />
      <div className="zl-pulse-text">
        <strong>{pulse.title}</strong>
        <small>{pulse.detail}</small>
      </div>
    </div>
  );
}

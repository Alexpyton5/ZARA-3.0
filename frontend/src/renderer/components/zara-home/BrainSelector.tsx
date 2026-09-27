import { useCallback, useEffect, useRef, useState } from 'react';
import { Brain, ChevronDown, RefreshCw } from 'lucide-react';
import { errorMessage } from './homeActions';

const BASE_BRAINS = [
  { id: 'gpt-5.6-luna', name: 'Luna' },
  { id: 'gpt-6-astra', name: 'Astra' },
  { id: 'gpt-5.6-sol', name: 'Sol' },
  { id: 'gpt-5.6-terra', name: 'Terra' },
  { id: 'nine_router_muse_spark_13', name: 'Muse Spark 1.3 (9Router)' },
  { id: 'nine_router_nemotron_lightning', name: 'Nemotron Lightning (9Router)' },
  { id: 'nine_router_mimo_v25', name: 'MiMo v2.5 (9Router)' },
] as const;

type BrainOption = { id: string; name: string; status: string };

/** An unverified catalog entry may be tried once; only AVAILABLE is proven. */
export function canTryBrain(status: string): boolean {
  return status === 'AVAILABLE' || status === 'DISCOVERED_UNPROVEN';
}

function isKnownBrainId(value: unknown, options: BrainOption[]): value is string {
  return typeof value === 'string' && options.some(option => option.id === value);
}

function statusLabel(status: string): string {
  switch (status) {
    case 'AVAILABLE': return 'Disponível';
    case 'DISCOVERED_UNPROVEN': return 'Acesso não confirmado';
    case 'AUTH_REQUIRED': return 'Entre na conta ChatGPT';
    case 'QUOTA_EXHAUSTED': return 'Cota esgotada';
    case 'OFFLINE': return 'Sem conexão';
    case 'DISABLED': return 'Desativado';
    default: return 'Indisponível';
  }
}

/** Selection is observed from the backend; only an explicit change can write it. */
export function useBrainSelection() {
  const [selected, setSelected] = useState<string | null>(null);
  const [options, setOptions] = useState<BrainOption[]>(() => BASE_BRAINS.map(brain => ({ ...brain, status: 'UNKNOWN' })));
  const [loading, setLoading] = useState(true);
  const [changing, setChanging] = useState<string | null>(null);
  const [error, setError] = useState('');
  const generation = useRef(0);
  const changePending = useRef(false);

  const refresh = useCallback(async () => {
    if (changePending.current) return;
    const request = ++generation.current;
    setLoading(true);
    setError('');
    try {
      const list = window.zaraIPC?.engine?.list;
      if (!list) throw new Error('O serviço de cérebros não está conectado.');
      const response = await list();
      if (response?.error || response?.success === false || typeof response?.current !== 'string' || !Array.isArray(response?.engines)) {
        throw new Error(typeof response?.error === 'string' ? response.error : 'Não foi possível confirmar os cérebros disponíveis.');
      }
      const engines: Array<{ id?: unknown; name?: unknown; provider?: unknown; status?: unknown }> = response.engines;
      // Base names stay observed; additional backend transports (e.g. OpenCode)
      // are appended as provided by the registry -- nothing is fabricated here.
      const observed: BrainOption[] = BASE_BRAINS.map(brain => {
        const match = engines.find(candidate => candidate?.id === brain.id);
        return { ...brain, status: typeof match?.status === 'string' ? match.status : 'UNKNOWN' };
      });
      const baseIds = new Set(observed.map(option => option.id));
      for (const candidate of engines) {
        if (typeof candidate?.id !== 'string' || !candidate.id || baseIds.has(candidate.id)) continue;
        const name = typeof candidate?.name === 'string' && candidate.name ? candidate.name : candidate.id;
        const suffix = candidate?.provider === 'opencode' ? ' (OpenCode)' : '';
        observed.push({ id: candidate.id, name: name + suffix, status: typeof candidate?.status === 'string' ? candidate.status : 'UNKNOWN' });
      }
      if (request !== generation.current) return;
      setSelected(isKnownBrainId(response.current, observed) ? response.current : null);
      setOptions(observed);
    } catch (cause) {
      if (request !== generation.current) return;
      setOptions(BASE_BRAINS.map(brain => ({ ...brain, status: 'UNKNOWN' })));
      setError(errorMessage(cause, 'Não foi possível atualizar os cérebros.'));
    } finally {
      if (request === generation.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    return () => { generation.current += 1; };
  }, [refresh]);

  async function select(id: string) {
    if (loading || changePending.current || id === selected || !options.some(option => option.id === id && canTryBrain(option.status))) return;
    changePending.current = true;
    const request = ++generation.current;
    setChanging(id);
    setError('');
    try {
      const change = window.zaraIPC?.engine?.change;
      if (!change) throw new Error('A troca de cérebro não está conectada.');
      const response = await change(id);
      if (response?.success !== true || response?.engine !== id || response?.error) {
        throw new Error(typeof response?.error === 'string' ? response.error : 'A troca não foi confirmada. Atualize os cérebros e tente novamente.');
      }
      if (request === generation.current) setSelected(id);
    } catch (cause) {
      if (request === generation.current) setError(errorMessage(cause, 'A troca não foi confirmada. Atualize os cérebros e tente novamente.'));
    } finally {
      changePending.current = false;
      if (request === generation.current) setChanging(null);
    }
  }

  async function readCurrent() {
    if (changePending.current) throw new Error('Aguarde a confirmação da troca de cérebro.');
    const get = window.zaraIPC?.config?.get;
    if (!get) throw new Error('Não foi possível confirmar o cérebro da conversa.');
    const request = generation.current;
    const response = await get();
    if (response?.error || response?.success === false || !isKnownBrainId(response?.current_engine, options)) {
      throw new Error(typeof response?.current_engine === 'string' && response.current_engine
        ? 'Este modelo esta indisponivel. Atualize os cérebros e escolha outro.'
        : 'Não foi possível confirmar o cérebro da conversa. Atualize e tente novamente.');
    }
    if (request === generation.current) setSelected(response.current_engine);
    return response.current_engine as string;
  }

  const current = options.find(option => option.id === selected);
  const busy = loading || changing !== null;
  const available = !busy && !error && current?.status === 'AVAILABLE';
  const status = changing ? `Confirmando troca para ${options.find(option => option.id === changing)?.name ?? changing}…`
    : loading ? 'Verificando disponibilidade…'
    : error ? 'Atualização necessária' : statusLabel(current?.status ?? 'UNKNOWN');

  return { selected, options, busy, available, error, status, refresh, select, readCurrent };
}

interface BrainSelectorProps {
  selection: ReturnType<typeof useBrainSelection>;
  disabled: boolean;
}

/** A native select preserves keyboard navigation and avoids clipping inside drawers. */
export function BrainSelector({ selection, disabled }: BrainSelectorProps) {
  const current = selection.options.find(brain => brain.id === selection.selected);
  return (
    <div className="zh-brain-selector" aria-busy={selection.busy}>
      <div className="zh-brain-picker" data-available={selection.available} title={`${current?.name ?? 'Cérebro'} · ${selection.status}`}>
        <Brain aria-hidden="true" />
        <span className="zh-brain-name" aria-hidden="true">{current?.name ?? 'Cérebro'}</span>
        <ChevronDown className="zh-brain-chevron" aria-hidden="true" />
        <select
          aria-label={`Cérebro da conversa: ${current?.name ?? 'não confirmado'}. ${selection.status}`}
          value={selection.selected ?? ''}
          disabled={disabled || selection.busy || !window.zaraIPC?.engine?.change}
          onChange={event => { void selection.select(event.target.value); }}
        >
          <option value="" disabled>Escolha um cérebro</option>
          {selection.options.map(brain => (
            <option key={brain.id} value={brain.id} disabled={!canTryBrain(brain.status)}>
              {brain.name}{brain.id === 'gpt-5.6-luna' ? ' (padrão)' : ''} — {statusLabel(brain.status)}
            </option>
          ))}
        </select>
      </div>
      <button className="zh-brain-refresh" type="button" disabled={disabled || selection.busy} onClick={() => { void selection.refresh(); }} aria-label="Atualizar disponibilidade dos cérebros" title="Atualizar cérebros">
        <RefreshCw aria-hidden="true" />
      </button>
      <span className="zh-brain-announcement" role="status">{selection.status}</span>
    </div>
  );
}

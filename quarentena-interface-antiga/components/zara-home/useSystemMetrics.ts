import { useEffect, useState } from 'react';
import type { SystemMetricsData } from './types';

const POLL_MS = 5000;

/**
 * Usa `window.zaraIPC.system.metrics()` — canal já existente (main.ts já
 * expõe `system.metrics`/`system.info`, consumidos hoje pelo painel de
 * telemetria). Não cria nenhum canal novo.
 *
 * Se o canal não existir ou a chamada falhar, retorna nulls — o card
 * de sistema mostra "NOT_CONNECTED_YET" em vez de inventar número.
 */
export function useSystemMetrics(): SystemMetricsData {
  const [data, setData] = useState<SystemMetricsData>({ cpu: null, ram: null, disk: null });

  useEffect(() => {
    const fetchMetrics = window.zaraIPC?.system?.metrics;
    if (!fetchMetrics) return;

    let cancelled = false;
    let pending = false;

    async function poll() {
      if (pending) return;
      pending = true;
      try {
        const result = await fetchMetrics!();
        if (cancelled || !result) return;
        const cpu = typeof result.cpu === 'number' ? result.cpu
          : typeof result?.cpu?.total === 'number' ? result.cpu.total : null;
        const ram = typeof result.ram === 'number' ? result.ram
          : typeof result.memory_percent === 'number' ? result.memory_percent
          : typeof result?.memory?.percent === 'number' ? result.memory.percent : null;
        const disk = typeof result.disk === 'number' ? result.disk
          : typeof result.disk_percent === 'number' ? result.disk_percent
          : typeof result?.disk?.percent === 'number' ? result.disk.percent : null;
        const valid = (value: number | null) => value !== null && Number.isFinite(value) && value >= 0 && value <= 100 ? value : null;
        setData({ cpu: valid(cpu), ram: valid(ram), disk: valid(disk) });
      } catch {
        if (!cancelled) setData({ cpu: null, ram: null, disk: null });
      } finally {
        pending = false;
      }
    }

    poll();
    const interval = setInterval(poll, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  return data;
}

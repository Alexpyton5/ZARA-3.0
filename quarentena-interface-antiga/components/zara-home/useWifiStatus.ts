import { useEffect, useState } from 'react';
import type { WifiStatusData } from './types';

const POLL_MS = 15000;

/**
 * Usa `window.zaraIPC.action.execute('os_wifi_status', {})` — action real
 * já registrada em `core/actions/windows_radios.py`, lida via PowerShell/WinRT.
 * Sem canal novo. Se a action falhar ou o canal não existir, `supported`
 * fica false e a UI mostra "—" em vez de inventar estado.
 */
export function useWifiStatus(): WifiStatusData {
  const [data, setData] = useState<WifiStatusData>({ supported: false, on: null });

  useEffect(() => {
    const execute = window.zaraIPC?.action?.execute;
    if (!execute) return;

    let cancelled = false;

    async function poll() {
      try {
        const response = await execute!('os_wifi_status', {});
        if (cancelled) return;
        const result = response?.result;
        const after = result?.data?.after;
        if (result?.success && (after === 'On' || after === 'Off')) {
          setData({ supported: true, on: after === 'On' });
        } else {
          setData({ supported: false, on: null });
        }
      } catch {
        if (!cancelled) setData({ supported: false, on: null });
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

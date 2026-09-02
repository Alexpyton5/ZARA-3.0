import { useEffect, useState } from 'react';
import type { BatteryData } from './types';

/**
 * `navigator.getBattery()` é uma API real do Chromium/Electron — não é dado
 * inventado nem depende de nenhum canal IPC novo. Indisponível em alguns
 * builds/políticas de energia; nesse caso `supported: false` e o card usa
 * fallback visual.
 */
export function useBattery(): BatteryData {
  const [data, setData] = useState<BatteryData>({ supported: false, level: null, charging: null });

  useEffect(() => {
    const nav = navigator as Navigator & { getBattery?: () => Promise<any> };
    if (!nav.getBattery) return;

    let battery: any;
    let cancelled = false;

    function update() {
      if (cancelled || !battery) return;
      setData({ supported: true, level: battery.level, charging: battery.charging });
    }

    nav.getBattery().then((b) => {
      if (cancelled) return;
      battery = b;
      update();
      b.addEventListener('levelchange', update);
      b.addEventListener('chargingchange', update);
    }).catch(() => {});

    return () => {
      cancelled = true;
      battery?.removeEventListener?.('levelchange', update);
      battery?.removeEventListener?.('chargingchange', update);
    };
  }, []);

  return data;
}

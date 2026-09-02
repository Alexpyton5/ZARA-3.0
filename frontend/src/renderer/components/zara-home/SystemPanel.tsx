
import type { BatteryData, SystemMetricsData } from './types';

interface SystemPanelProps {
  metrics: SystemMetricsData;
  battery: BatteryData;
}

function pct(value: number | null): string {
  return value === null ? '—' : `${Math.round(value)}%`;
}

/**
 * Painel "Sistema" — CPU/RAM/Disco vêm de `window.zaraIPC.system.metrics()`
 * (canal real e já existente). Bateria vem de `navigator.getBattery()`
 * (API real do Chromium). Segurança/Energia/Manutenção do site de
 * referência não têm fonte real na ZARA hoje (nenhuma action de firewall,
 * antivírus ou plano de energia com leitura de estado) — mantidos como
 * estrutura visual real com rótulo NOT_CONNECTED_YET, sem inventar dado.
 */
export function SystemPanel({ metrics, battery }: SystemPanelProps) {
  return (
    <section className="zh-system-row zh-glass-panel" aria-label="Sistema">
      <div className="zh-system-col">
        <h2>Estado do dispositivo</h2>
        <div className="zh-metric-row">
          <span>CPU</span>
          <span>{pct(metrics.cpu)}</span>
        </div>
        <div className="zh-metric-row">
          <span>RAM</span>
          <span>{pct(metrics.ram)}</span>
        </div>
        <div className="zh-metric-row">
          <span>Disco</span>
          <span>{pct(metrics.disk)}</span>
        </div>
        <div className="zh-metric-row">
          <span>Bateria</span>
          <span>
            {battery.supported && battery.level !== null
              ? `${Math.round(battery.level * 100)}%${battery.charging ? ' ⚡' : ''}`
              : 'NOT_CONNECTED_YET'}
          </span>
        </div>
      </div>

      <div className="zh-system-col">
        <h2>Segurança</h2>
        <p className="zh-not-connected">NOT_CONNECTED_YET — sem leitura real de firewall/antivírus exposta.</p>
      </div>

      <div className="zh-system-col">
        <h2>Energia</h2>
        <p className="zh-not-connected">NOT_CONNECTED_YET — ação real existe (os_power_plan_list/set), não conectada nesta tela ainda.</p>
      </div>

      <div className="zh-system-col">
        <h2>Manutenção</h2>
        <p className="zh-not-connected">NOT_CONNECTED_YET — ações de limpeza ainda não expostas a esta tela.</p>
      </div>
    </section>
  );
}

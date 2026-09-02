import { Cpu, MemoryStick, HardDrive, BatteryFull, ShieldQuestion, Zap, Wrench } from 'lucide-react';
import type { BatteryData, SystemMetricsData } from './types';

interface SystemPanelProps {
  metrics: SystemMetricsData;
  battery: BatteryData;
}

function pct(value: number | null): string {
  return value === null ? '—' : `${Math.round(value)}%`;
}

// Cor semântica do projeto (ver .claude/rules): branco/titânio = neutro,
// esmeralda = ativo/saudável, âmbar = alerta, cinza = indisponível. Nenhum
// dado real de saúde (limiar de "alerta") existe ainda para CPU/RAM/Disco —
// então tudo fica neutro (titânio) até essa lógica existir de verdade, em
// vez de inventar limiares arbitrários de cor.
function metricColorClass(value: number | null): string {
  return value === null ? 'zh-metric-unknown' : 'zh-metric-neutral';
}

export function SystemPanel({ metrics, battery }: SystemPanelProps) {
  return (
    <section className="zh-system-row zh-glass-panel" aria-label="Sistema">
      <div className="zh-system-col">
        <h2><Cpu size={14} strokeWidth={1.8} /> Estado do dispositivo</h2>
        <div className="zh-metric-row">
          <span><Cpu size={13} strokeWidth={1.8} /> CPU</span>
          <span className={metricColorClass(metrics.cpu)}>{pct(metrics.cpu)}</span>
        </div>
        <div className="zh-metric-row">
          <span><MemoryStick size={13} strokeWidth={1.8} /> RAM</span>
          <span className={metricColorClass(metrics.ram)}>{pct(metrics.ram)}</span>
        </div>
        <div className="zh-metric-row">
          <span><HardDrive size={13} strokeWidth={1.8} /> Disco</span>
          <span className={metricColorClass(metrics.disk)}>{pct(metrics.disk)}</span>
        </div>
        <div className="zh-metric-row">
          <span><BatteryFull size={13} strokeWidth={1.8} /> Bateria</span>
          <span className={battery.supported ? 'zh-metric-active' : 'zh-metric-unknown'}>
            {battery.supported && battery.level !== null
              ? `${Math.round(battery.level * 100)}%${battery.charging ? ' ⚡' : ''}`
              : 'NOT_CONNECTED_YET'}
          </span>
        </div>
      </div>

      <div className="zh-system-col">
        <h2><ShieldQuestion size={14} strokeWidth={1.8} /> Segurança</h2>
        <p className="zh-not-connected">NOT_CONNECTED_YET — sem leitura real de firewall/antivírus exposta.</p>
      </div>

      <div className="zh-system-col">
        <h2><Zap size={14} strokeWidth={1.8} /> Energia</h2>
        <p className="zh-not-connected">NOT_CONNECTED_YET — ação real existe (os_power_plan_list/set), não conectada nesta tela ainda.</p>
      </div>

      <div className="zh-system-col">
        <h2><Wrench size={14} strokeWidth={1.8} /> Manutenção</h2>
        <p className="zh-not-connected">NOT_CONNECTED_YET — ações de limpeza ainda não expostas a esta tela.</p>
      </div>
    </section>
  );
}

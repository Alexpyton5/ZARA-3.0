import {
  Cpu, MemoryStick, HardDrive, MonitorCog, BatteryFull, Thermometer, Wifi,
  Database, Trash2, Power, ListChecks, RotateCw, Activity, Search, ShieldCheck, Shield, KeyRound, Gauge, SlidersHorizontal, Leaf, ChevronRight,
} from 'lucide-react';
import type { BatteryData, SystemMetricsData } from './types';

interface SystemPanelProps {
  metrics: SystemMetricsData;
  battery: BatteryData;
}

function pct(value: number | null): string {
  return value === null ? '—' : `${Math.round(value)}%`;
}

function metricColorClass(value: number | null): string {
  return value === null ? 'zh-metric-unknown' : 'zh-metric-neutral';
}

function ActionCard({ icon, label, sub }: { icon: React.ReactNode; label: string; sub: string }) {
  return (
    <button className="zh-action-card" type="button">
      <span className="zh-action-card-icon">{icon}</span>
      <span className="zh-action-card-text">
        <strong>{label}</strong>
        <span>{sub}</span>
      </span>
    </button>
  );
}

function ActionRow({ icon, label, sub }: { icon: React.ReactNode; label: string; sub: string }) {
  return (
    <div className="zh-action-row">
      <span className="zh-action-icon">{icon}</span>
      <span className="zh-action-text">
        <span className="zh-action-label">{label}</span>
        <span className="zh-action-sub">{sub}</span>
      </span>
    </div>
  );
}

export function SystemPanel({ metrics, battery }: SystemPanelProps) {
  return (
    <section className="zh-system-row zh-glass-panel" aria-label="Sistema">
      <h1 className="zh-system-title">Sistema</h1>
      <div className="zh-system-grid">
        <div className="zh-system-col zh-system-col--status">
          <div className="zh-device-card">
            <h2><Cpu size={14} strokeWidth={1.8} /> Estado do dispositivo</h2>
            <div className="zh-status-summary">
              <strong>Monitorando</strong>
              <span>Métricas reais do sistema</span>
            </div>
            <div className="zh-metric-row">
              <span><Cpu size={13} strokeWidth={1.8} /> CPU</span>
              <span className={metricColorClass(metrics.cpu)}>{pct(metrics.cpu)}</span>
            </div>
            <div className="zh-metric-row">
              <span><MemoryStick size={13} strokeWidth={1.8} /> RAM</span>
              <span className={metricColorClass(metrics.ram)}>{pct(metrics.ram)}</span>
            </div>
            <div className="zh-metric-row">
              <span><MonitorCog size={13} strokeWidth={1.8} /> GPU</span>
              <span className="zh-metric-unknown">—</span>
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
                  : '—'}
              </span>
            </div>
            <div className="zh-metric-row">
              <span><Thermometer size={13} strokeWidth={1.8} /> Temperatura</span>
              <span className="zh-metric-unknown">—</span>
            </div>
            <div className="zh-metric-row">
              <span><Wifi size={13} strokeWidth={1.8} /> Rede</span>
              <span className="zh-metric-unknown">—</span>
            </div>
          </div>
        </div>

        <div className="zh-system-col zh-system-col--maintenance">
          <h2><Database size={14} strokeWidth={1.8} /> Manutenção</h2>
          <div className="zh-action-grid">
            <ActionCard icon={<Database size={16} strokeWidth={1.7} />} label="Liberar espaço" sub="Indisponível" />
            <ActionCard icon={<Trash2 size={16} strokeWidth={1.7} />} label="Limpar temporários" sub="Indisponível" />
            <ActionCard icon={<Power size={16} strokeWidth={1.7} />} label="Gerenciar inicialização" sub="Indisponível" />
            <ActionCard icon={<ListChecks size={16} strokeWidth={1.7} />} label="Ver processos" sub="Indisponível" />
            <ActionCard icon={<RotateCw size={16} strokeWidth={1.7} />} label="Atualizar sistema" sub="Indisponível" />
            <ActionCard icon={<Activity size={16} strokeWidth={1.7} />} label="Diagnóstico ZARA" sub="Indisponível" />
          </div>
        </div>

        <div className="zh-system-col zh-system-col--security">
          <h2><Shield size={14} strokeWidth={1.8} /> Segurança</h2>
          <ActionRow icon={<Search size={14} strokeWidth={1.7} />} label="Verificação rápida" sub="Indisponível" />
          <ActionRow icon={<ShieldCheck size={14} strokeWidth={1.7} />} label="Verificação completa" sub="Indisponível" />
          <ActionRow icon={<Shield size={14} strokeWidth={1.7} />} label="Firewall" sub="Indisponível" />
          <ActionRow icon={<KeyRound size={14} strokeWidth={1.7} />} label="Permissões" sub="Indisponível" />
          <ActionRow icon={<Activity size={14} strokeWidth={1.7} />} label="Ameaças" sub="Indisponível" />
        </div>

        <div className="zh-system-col zh-system-col--energy">
          <h2><Gauge size={14} strokeWidth={1.8} /> Energia</h2>
          <button className="zh-energy-card" type="button">
            <Gauge size={15} strokeWidth={1.7} />
            <span className="zh-energy-text">
              <strong>Performance</strong>
              <span>Máximo desempenho</span>
            </span>
            <span className="zh-energy-dot" data-active="true" />
          </button>
          <button className="zh-energy-card" type="button">
            <SlidersHorizontal size={15} strokeWidth={1.7} />
            <span className="zh-energy-text">
              <strong>Equilibrado</strong>
              <span>Balanceado</span>
            </span>
            <span className="zh-energy-dot" />
          </button>
          <button className="zh-energy-card" type="button">
            <Leaf size={15} strokeWidth={1.7} />
            <span className="zh-energy-text">
              <strong>Economia</strong>
              <span>Economia de energia</span>
            </span>
            <span className="zh-energy-dot" />
          </button>
        </div>

        <div className="zh-system-col zh-diagnostic-col">
          <h2><Activity size={14} strokeWidth={1.8} /> Diagnóstico inteligente</h2>
          <svg className="zh-diagnostic-wave" viewBox="0 0 200 40" aria-hidden="true">
            <path
              className="zh-diagnostic-wave-ghost"
              d="M0 26 C 18 26, 24 12, 40 12 S 62 30, 80 30 S 104 8, 122 8 S 146 26, 164 26 S 184 16, 200 16"
            />
            <path
              className="zh-diagnostic-wave-line"
              d="M0 24 C 18 24, 24 10, 40 10 S 62 28, 80 28 S 104 6, 122 6 S 146 24, 164 24 S 184 14, 200 14"
            />
          </svg>
          <p className="zh-diagnostic-title">Por que meu PC está lento?</p>
          <p className="zh-not-connected">
            ZARA pode analisar quando o diagnóstico real estiver conectado.
          </p>
          <button className="zh-diagnostic-btn" type="button" disabled>
            Analisar agora
            <ChevronRight size={14} strokeWidth={2} />
          </button>
        </div>
      </div>
    </section>
  );
}

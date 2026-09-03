import { Cpu, MemoryStick, HardDrive, BatteryFull, Database, Trash2, Power, ListChecks, RotateCw, Activity, Search, ShieldCheck, Shield, KeyRound, Gauge, SlidersHorizontal, Leaf } from 'lucide-react';
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

/**
 * Linha de ação por item, no formato do MASTER (ícone + rótulo), mas SEM
 * inventar a subtitulo/status que o backend não tem ("2,1 GB disponível",
 * "128 ativos" etc. no site são dados de demonstração). O ícone e o rótulo
 * já vêm do MASTER; o texto secundário mostra honestamente "Indisponível"
 * em vez de fabricar um número. Isso preserva a densidade/estrutura visual
 * real do site sem inventar dado.
 */
function ActionRow({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <div className="zh-action-row">
      <span className="zh-action-icon">{icon}</span>
      <span className="zh-action-text">
        <span className="zh-action-label">{label}</span>
        <span className="zh-action-sub">Indisponível</span>
      </span>
    </div>
  );
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
              : 'Indisponível'}
          </span>
        </div>
      </div>

      <div className="zh-system-col">
        <h2><Database size={14} strokeWidth={1.8} /> Manutenção</h2>
        <ActionRow icon={<Database size={14} strokeWidth={1.7} />} label="Liberar espaço" />
        <ActionRow icon={<Trash2 size={14} strokeWidth={1.7} />} label="Limpar temporários" />
        <ActionRow icon={<Power size={14} strokeWidth={1.7} />} label="Gerenciar inicialização" />
        <ActionRow icon={<ListChecks size={14} strokeWidth={1.7} />} label="Ver processos" />
        <ActionRow icon={<RotateCw size={14} strokeWidth={1.7} />} label="Atualizar sistema" />
        <ActionRow icon={<Activity size={14} strokeWidth={1.7} />} label="Diagnóstico ZARA" />
      </div>

      <div className="zh-system-col">
        <h2><Shield size={14} strokeWidth={1.8} /> Segurança</h2>
        <ActionRow icon={<Search size={14} strokeWidth={1.7} />} label="Verificação rápida" />
        <ActionRow icon={<ShieldCheck size={14} strokeWidth={1.7} />} label="Verificação completa" />
        <ActionRow icon={<Shield size={14} strokeWidth={1.7} />} label="Firewall" />
        <ActionRow icon={<KeyRound size={14} strokeWidth={1.7} />} label="Permissões" />
      </div>

      <div className="zh-system-col">
        <h2><Gauge size={14} strokeWidth={1.8} /> Energia</h2>
        <ActionRow icon={<Gauge size={14} strokeWidth={1.7} />} label="Performance" />
        <ActionRow icon={<SlidersHorizontal size={14} strokeWidth={1.7} />} label="Equilibrado" />
        <ActionRow icon={<Leaf size={14} strokeWidth={1.7} />} label="Economia" />
      </div>

      <div className="zh-system-col zh-diagnostic-col">
        <h2><Activity size={14} strokeWidth={1.8} /> Diagnóstico inteligente</h2>
        {/* Onda ambiente puramente decorativa — não representa nenhuma
         * métrica real (CPU/rede/etc.). É um acento visual do "estado de
         * prontidão para analisar", não um gráfico de telemetria fabricado. */}
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
        <p style={{ fontSize: 13, fontWeight: 600, margin: '2px 0 4px' }}>Por que meu PC está lento?</p>
        <p className="zh-not-connected">
          ZARA pode analisar quando o diagnóstico real estiver conectado.
        </p>
      </div>
    </section>
  );
}

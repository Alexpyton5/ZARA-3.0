import type { ReactNode } from 'react';
import {
  Cpu, MemoryStick, HardDrive, BatteryFull, Thermometer, Wifi as WifiIcon,
  Database, Trash2, Power, ListChecks, RotateCw, Activity,
  Search, ShieldCheck, Shield, KeyRound, Bug,
  Gauge, SlidersHorizontal, Leaf,
} from 'lucide-react';
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

/**
 * Linha genérica de item "ainda não conectado" — mesmo padrão visual das
 * métricas reais (`.zh-metric-row`), só que o valor da direita é sempre
 * "Indisponível" em vez de inventar um número/estado que o backend não
 * expõe. Usada em Manutenção/Segurança/Energia: os ícones abaixo mapeiam
 * 1:1 com a ação real que ELES REPRESENTAM (ver `core/actions/*.py`), mas
 * nenhuma dessas ações tem hoje uma superfície nesta tela para mostrar o
 * resultado — então preferimos "honesto e sem função" a "botão morto que
 * parece fazer algo".
 */
function UnconnectedRow({ icon, label }: { icon: ReactNode; label: string }) {
  return (
    <div className="zh-metric-row">
      <span>{icon} {label}</span>
      <span className="zh-metric-unknown">Indisponível</span>
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
        <div className="zh-metric-row">
          <span><Thermometer size={13} strokeWidth={1.8} /> Temperatura</span>
          <span className="zh-metric-unknown">—</span>
        </div>
        <div className="zh-metric-row">
          <span><WifiIcon size={13} strokeWidth={1.8} /> Rede</span>
          <span className="zh-metric-unknown">—</span>
        </div>
      </div>

      <div className="zh-system-col">
        <h2><Database size={14} strokeWidth={1.8} /> Manutenção</h2>
        <UnconnectedRow icon={<Database size={13} strokeWidth={1.8} />} label="Liberar espaço" />
        <UnconnectedRow icon={<Trash2 size={13} strokeWidth={1.8} />} label="Limpar temporários" />
        <UnconnectedRow icon={<Power size={13} strokeWidth={1.8} />} label="Gerenciar inicialização" />
        <UnconnectedRow icon={<ListChecks size={13} strokeWidth={1.8} />} label="Ver processos" />
        <UnconnectedRow icon={<RotateCw size={13} strokeWidth={1.8} />} label="Atualizar sistema" />
        <UnconnectedRow icon={<Activity size={13} strokeWidth={1.8} />} label="Diagnóstico ZARA" />
      </div>

      <div className="zh-system-col">
        <h2><Shield size={14} strokeWidth={1.8} /> Segurança</h2>
        <UnconnectedRow icon={<Search size={13} strokeWidth={1.8} />} label="Verificação rápida" />
        <UnconnectedRow icon={<ShieldCheck size={13} strokeWidth={1.8} />} label="Verificação completa" />
        <UnconnectedRow icon={<Shield size={13} strokeWidth={1.8} />} label="Firewall" />
        <UnconnectedRow icon={<KeyRound size={13} strokeWidth={1.8} />} label="Permissões" />
        <div className="zh-metric-row">
          <span><Bug size={13} strokeWidth={1.8} /> Ameaças</span>
          <span className="zh-metric-unknown">Sem leitura real</span>
        </div>
      </div>

      <div className="zh-system-col">
        <h2><Gauge size={14} strokeWidth={1.8} /> Energia</h2>
        <UnconnectedRow icon={<Gauge size={13} strokeWidth={1.8} />} label="Performance" />
        <UnconnectedRow icon={<SlidersHorizontal size={13} strokeWidth={1.8} />} label="Equilibrado" />
        <UnconnectedRow icon={<Leaf size={13} strokeWidth={1.8} />} label="Economia" />
        <p className="zh-not-connected" style={{ marginTop: 4 }}>
          Ação real existe (os_power_plan_list/set), não conectada nesta tela ainda.
        </p>
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
          ZARA pode analisar e sugerir melhorias quando o diagnóstico real estiver conectado.
        </p>
        <button className="zh-tool-open" type="button" disabled style={{ marginTop: 8, opacity: 0.5, cursor: 'default' }}>
          Analisar agora — indisponível
        </button>
      </div>
    </section>
  );
}

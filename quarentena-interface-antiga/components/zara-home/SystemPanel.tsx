import { useEffect, useState, type ReactNode } from 'react';
import {
  Cpu, MemoryStick, HardDrive, MonitorCog, BatteryFull, Thermometer, Wifi,
  Database, Trash2, Power, ListChecks, RotateCw, Activity, Search, ShieldCheck, Shield, KeyRound, Gauge, SlidersHorizontal, Leaf, ChevronRight,
} from 'lucide-react';
import { useHomeFeedback } from './useHomeFeedback';
import type { BatteryData, PowerPlansData, SystemMetricsData, WifiStatusData } from './types';

interface SystemPanelProps {
  metrics: SystemMetricsData;
  battery: BatteryData;
  wifi: WifiStatusData;
  power: PowerPlansData;
}

const ENERGY_ICONS = [Gauge, SlidersHorizontal, Leaf];

function pct(value: number | null): string {
  return value === null ? '—' : `${Math.round(value)}%`;
}

function metricColorClass(value: number | null): string {
  return value === null ? 'zh-metric-unknown' : 'zh-metric-neutral';
}

function ActionCard({
  icon, label, sub, onClick, disabled,
}: { icon: ReactNode; label: string; sub: string; onClick?: () => void; disabled?: boolean }) {
  return (
    <button className="zh-action-card" type="button" onClick={onClick} disabled={disabled}>
      <span className="zh-action-card-icon">{icon}</span>
      <span className="zh-action-card-text">
        <strong>{label}</strong>
        <span>{sub}</span>
      </span>
    </button>
  );
}

function ActionRow({ icon, label, sub, onClick }: { icon: ReactNode; label: string; sub: string; onClick?: () => void }) {
  return (
    <button type="button" className="zh-action-row" onClick={onClick}>
      <span className="zh-action-icon">{icon}</span>
      <span className="zh-action-text">
        <span className="zh-action-label">{label}</span>
        <span className="zh-action-sub">{sub}</span>
      </span>
    </button>
  );
}

export function SystemPanel({ metrics, battery, wifi, power }: SystemPanelProps) {
  const [processSub, setProcessSub] = useState('Indisponível');
  const [processLoading, setProcessLoading] = useState(false);
  const [diagnosticSummary, setDiagnosticSummary] = useState<string | null>(null);
  const [diagnosticLoading, setDiagnosticLoading] = useState(false);

  const feedback = useHomeFeedback();
  const [samples, setSamples] = useState<number[]>([]);
  useEffect(() => {
    if (metrics.cpu !== null) setSamples(values => [...values.slice(-39), metrics.cpu!]);
  }, [metrics.cpu]);
  function settings(id: 'storage'|'temporary'|'startup'|'update'|'security'|'firewall'|'privacy'|'power') {
    void feedback.run(() => window.zaraIPC?.desktop?.openSettings?.(id), 'Configurações abertas no Windows.');
  }
  async function handleAnalisarAgora() {
    if (diagnosticLoading) return;
    setDiagnosticLoading(true);
    try {
      const readings = [metrics.cpu, metrics.ram, metrics.disk];
      if (readings.every(value => value === null)) { setDiagnosticSummary('Métricas indisponíveis. Verifique a conexão com a ZARA.'); return; }
      const findings = [];
      if ((metrics.cpu ?? 0) >= 80) findings.push('CPU elevada. Consulte os processos.');
      if ((metrics.ram ?? 0) >= 80) findings.push('Memória ocupada. Feche aplicativos sem uso.');
      if ((metrics.disk ?? 0) >= 90) findings.push('Disco quase cheio. Revise o armazenamento.');
      setDiagnosticSummary(findings.join(' ') || 'CPU, memória e disco sem uso elevado nesta leitura.');
    } finally { setDiagnosticLoading(false); }
  }

  function handleVerProcessos() {
    const execute = window.zaraIPC?.action?.execute;
    if (!execute || processLoading) return;
    setProcessLoading(true);
    execute('system_processes', { limit: 500 })
      .then((response: { result?: { success?: boolean; data?: { count?: number } } }) => {
        const result = response?.result;
        const count = result?.data?.count;
        setProcessSub(result?.success && typeof count === 'number' ? `${count} processos` : 'Indisponível');
      })
      .catch(() => setProcessSub('Indisponível'))
      .finally(() => setProcessLoading(false));
  }

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
              <span className={wifi.supported ? 'zh-metric-active' : 'zh-metric-unknown'}>
                {wifi.supported ? (wifi.on ? 'Ligado' : 'Desligado') : '—'}
              </span>
            </div>
          </div>
        </div>

        <div className="zh-system-col zh-system-col--maintenance">
          <h2><Database size={14} strokeWidth={1.8} /> Manutenção</h2>
          <div className="zh-action-grid">
            <ActionCard icon={<Database size={16} strokeWidth={1.7} />} label="Liberar espaço" sub="Ver armazenamento" onClick={() => settings('storage')} />
            <ActionCard icon={<Trash2 size={16} strokeWidth={1.7} />} label="Limpar temporários" sub="Revisar no Windows" onClick={() => settings('temporary')} />
            <ActionCard icon={<Power size={16} strokeWidth={1.7} />} label="Gerenciar inicialização" sub="Gerenciar aplicativos" onClick={() => settings('startup')} />
            <ActionCard
              icon={<ListChecks size={16} strokeWidth={1.7} />}
              label="Ver processos"
              sub={processLoading ? 'Consultando…' : processSub}
              onClick={handleVerProcessos}
              disabled={processLoading}
            />
            <ActionCard icon={<RotateCw size={16} strokeWidth={1.7} />} label="Atualizar sistema" sub="Windows Update" onClick={() => settings('update')} />
            <ActionCard icon={<Activity size={16} strokeWidth={1.7} />} label="Diagnóstico ZARA" sub="Verificar agora" onClick={() => void handleAnalisarAgora()} />
          </div>
        </div>

        <div className="zh-system-col zh-system-col--security">
          <h2><Shield size={14} strokeWidth={1.8} /> Segurança</h2>
          <ActionRow icon={<Search size={14} strokeWidth={1.7} />} label="Verificação rápida" sub="Abrir Segurança" onClick={() => settings('security')} />
          <ActionRow icon={<ShieldCheck size={14} strokeWidth={1.7} />} label="Verificação completa" sub="Revisar no Windows" onClick={() => settings('security')} />
          <ActionRow icon={<Shield size={14} strokeWidth={1.7} />} label="Firewall" sub="Abrir proteção" onClick={() => settings('firewall')} />
          <ActionRow icon={<KeyRound size={14} strokeWidth={1.7} />} label="Permissões" sub="Gerenciar apps" onClick={() => settings('privacy')} />
          <ActionRow icon={<Activity size={14} strokeWidth={1.7} />} label="Ameaças" sub="Consultar proteção" onClick={() => settings('security')} />
        </div>

        <div className="zh-system-col zh-system-col--energy">
          <h2><Gauge size={14} strokeWidth={1.8} /> Energia</h2>
          {[
            { name: 'Performance', match: /high|alto|desempenho|performance/i, guid: '8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c' },
            { name: 'Equilibrado', match: /balanced|equilibr/i, guid: '381b4222-f694-41f0-9685-ff5bb260df2e' },
            { name: 'Economia', match: /saver|econom/i, guid: 'a1841308-3541-4fab-bc81-f71556f20b4a' },
          ].map((mode, index) => {
            const plan = power.plans.find(plan => plan.guid.toLowerCase() === mode.guid || mode.match.test(plan.name));
            const Icon = ENERGY_ICONS[index];
            return <button key={mode.name} className="zh-energy-card" type="button" disabled={power.pending} onClick={() => plan ? power.setPlan(plan.guid) : settings('power')} aria-pressed={Boolean(plan?.active)}>
              <Icon size={23} strokeWidth={1.5} /><span className="zh-energy-text"><strong>{mode.name}</strong><span>{plan?.active ? 'Plano ativo' : plan ? 'Clique para ativar' : 'Configurar no Windows'}</span></span>
              <span className="zh-energy-dot" data-active={plan?.active ? 'true' : undefined} />
            </button>;
          })}
        </div>

        <div className="zh-system-col zh-diagnostic-col">
          <h2><Activity size={14} strokeWidth={1.8} /> Diagnóstico inteligente</h2>
          <svg className="zh-diagnostic-wave" viewBox="0 0 200 70" preserveAspectRatio="none" aria-label="Histórico de uso da CPU">
            <path className="zh-diagnostic-wave-ghost" d="M0 65H200" />
            {samples.length > 1 && <path className="zh-diagnostic-wave-line" d={samples.map((value, index) => `${index ? 'L' : 'M'}${index * 200 / (samples.length - 1)},${65 - value * .6}`).join(' ')} />}
          </svg>
          <p className="zh-diagnostic-title">Por que meu PC está lento?</p>
          <p className={diagnosticSummary ? undefined : 'zh-not-connected'}>
            {diagnosticLoading
              ? 'Analisando…'
              : diagnosticSummary ?? 'ZARA pode analisar e sugerir melhorias.'}
          </p>
          <button
            className="zh-diagnostic-btn"
            type="button"
            onClick={handleAnalisarAgora}
            disabled={diagnosticLoading}
          >
            Analisar agora
            <ChevronRight size={14} strokeWidth={2} />
          </button>
        </div>
      </div>
      {(feedback.feedback || power.error) && <div className="zh-system-feedback" role={power.error ? 'alert' : 'status'}>{feedback.feedback || power.error}</div>}
    </section>
  );
}

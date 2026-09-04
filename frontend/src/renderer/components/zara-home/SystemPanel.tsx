import { useState, type ReactNode } from 'react';
import {
  Cpu, MemoryStick, HardDrive, MonitorCog, BatteryFull, Thermometer, Wifi,
  Database, Trash2, Power, ListChecks, RotateCw, Activity, Search, ShieldCheck, Shield, KeyRound, Gauge, SlidersHorizontal, Leaf, ChevronRight,
} from 'lucide-react';
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

function ActionRow({ icon, label, sub }: { icon: ReactNode; label: string; sub: string }) {
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

export function SystemPanel({ metrics, battery, wifi, power }: SystemPanelProps) {
  const [processSub, setProcessSub] = useState('Indisponível');
  const [processLoading, setProcessLoading] = useState(false);
  const [diagnosticSummary, setDiagnosticSummary] = useState<string | null>(null);
  const [diagnosticLoading, setDiagnosticLoading] = useState(false);

  function handleAnalisarAgora() {
    const selfStatus = window.zaraIPC?.system?.selfStatus;
    if (!selfStatus || diagnosticLoading) return;
    setDiagnosticLoading(true);
    selfStatus()
      .then((snapshot: { capabilities?: Array<{ status?: string }> } | null) => {
        const capabilities = snapshot?.capabilities;
        if (!Array.isArray(capabilities) || capabilities.length === 0) {
          setDiagnosticSummary('Diagnóstico indisponível agora.');
          return null;
        }
        const available = capabilities.filter((c) => c.status === 'AVAILABLE').length;
        setDiagnosticSummary(`${available}/${capabilities.length} capacidades disponíveis agora.`);
        return null;
      })
      .catch(() => setDiagnosticSummary('Diagnóstico indisponível agora.'))
      .finally(() => setDiagnosticLoading(false));

    // Lembrar: acrescenta a contagem real de fatos guardados, sem novo
    // painel -- reusa o mesmo card de diagnóstico. Canal já testado nesta
    // madrugada (ver .ceo/NIGHT_LOG.md); sem consumidor até este ponto.
    const listMemory = window.zaraIPC?.userMemory?.list;
    if (listMemory) {
      listMemory()
        .then((res: { success?: boolean; facts?: unknown[] }) => {
          if (res?.success && Array.isArray(res.facts)) {
            setDiagnosticSummary((prev) => `${prev ?? ''} ${res.facts!.length} fatos na memória.`.trim());
          }
        })
        .catch(() => {
          // Silencioso: a memoria e um extra sobre o diagnostico principal,
          // nao pode derrubar o resumo de capacidades se falhar.
        });
    }
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
            <ActionCard icon={<Database size={16} strokeWidth={1.7} />} label="Liberar espaço" sub="Indisponível" />
            <ActionCard icon={<Trash2 size={16} strokeWidth={1.7} />} label="Limpar temporários" sub="Indisponível" />
            <ActionCard icon={<Power size={16} strokeWidth={1.7} />} label="Gerenciar inicialização" sub="Indisponível" />
            <ActionCard
              icon={<ListChecks size={16} strokeWidth={1.7} />}
              label="Ver processos"
              sub={processLoading ? 'Consultando…' : processSub}
              onClick={handleVerProcessos}
              disabled={processLoading}
            />
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
          {power.supported && power.plans.length > 0 ? (
            power.plans.map((plan, index) => {
              const Icon = ENERGY_ICONS[index % ENERGY_ICONS.length];
              return (
                <button
                  key={plan.guid}
                  className="zh-energy-card"
                  type="button"
                  disabled={power.pending || plan.active}
                  onClick={() => power.setPlan(plan.guid)}
                  aria-pressed={plan.active}
                >
                  <Icon size={15} strokeWidth={1.7} />
                  <span className="zh-energy-text">
                    <strong>{plan.name}</strong>
                    <span>{plan.active ? 'Plano ativo' : 'Clique para ativar'}</span>
                  </span>
                  <span className="zh-energy-dot" data-active={plan.active ? 'true' : undefined} />
                </button>
              );
            })
          ) : (
            <ActionRow icon={<Gauge size={14} strokeWidth={1.7} />} label="Planos de energia" sub="Indisponível" />
          )}
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
          <p className={diagnosticSummary ? undefined : 'zh-not-connected'}>
            {diagnosticLoading
              ? 'Analisando…'
              : diagnosticSummary ?? 'ZARA pode analisar as próprias capacidades agora.'}
          </p>
          <button
            className="zh-diagnostic-btn"
            type="button"
            onClick={handleAnalisarAgora}
            disabled={diagnosticLoading || !window.zaraIPC?.system?.selfStatus}
          >
            Analisar agora
            <ChevronRight size={14} strokeWidth={2} />
          </button>
        </div>
      </div>
    </section>
  );
}

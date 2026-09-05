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

function ActionRow({
  icon, label, sub, onClick, disabled,
}: { icon: ReactNode; label: string; sub: string; onClick?: () => void; disabled?: boolean }) {
  // Sem `onClick` continua sendo uma linha de leitura, não um botão morto.
  if (!onClick) {
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
  return (
    <button className="zh-action-row zh-action-row--btn" type="button" onClick={onClick} disabled={disabled}>
      <span className="zh-action-icon">{icon}</span>
      <span className="zh-action-text">
        <span className="zh-action-label">{label}</span>
        <span className="zh-action-sub">{sub}</span>
      </span>
    </button>
  );
}

/**
 * Card do painel Sistema que roda uma leitura REAL sob demanda.
 *
 * A regra é a mesma dos outros: o texto de resultado vem do executor
 * (`result.output` / `result.error`), nunca de string fixa. Card sem action
 * por trás continua "Indisponível" e desabilitado — é honesto e é a maioria
 * deles hoje.
 */
function useLeituraSobDemanda(
  action: string,
  ler: (data: unknown, output: string) => string,
) {
  const execute = window.zaraIPC?.action?.execute;
  const [sub, setSub] = useState('Indisponível');
  const [carregando, setCarregando] = useState(false);

  function rodar() {
    if (!execute || carregando) return;
    setCarregando(true);
    execute(action, {})
      .then((res: { result?: { success?: boolean; data?: unknown; output?: string; error?: string } }) => {
        const r = res?.result;
        setSub(r?.success ? ler(r.data, String(r.output ?? '')) : (r?.error || 'Indisponível'));
      })
      .catch((e: unknown) => setSub(e instanceof Error ? e.message : 'Indisponível'))
      .finally(() => setCarregando(false));
  }

  return { sub: carregando ? 'Consultando…' : sub, rodar, carregando, disponivel: Boolean(execute) };
}

export function SystemPanel({ metrics, battery, wifi, power }: SystemPanelProps) {
  const [processSub, setProcessSub] = useState('Indisponível');
  const [processLoading, setProcessLoading] = useState(false);
  const [diagnosticSummary, setDiagnosticSummary] = useState<string | null>(null);
  const [diagnosticLoading, setDiagnosticLoading] = useState(false);

  // Lixeira: o que dá para dizer com honestidade é QUANTOS itens existem.
  // `os_recycle_bin_list` não devolve tamanho, então nada de "2,1 GB".
  const lixeira = useLeituraSobDemanda('os_recycle_bin_list', (data) => {
    const n = Array.isArray(data) ? data.length : 0;
    return n === 0 ? 'Lixeira vazia' : `${n} ${n === 1 ? 'item' : 'itens'} na Lixeira`;
  });

  // Firewall: o que se pode ler é o ESTADO DO SERVIÇO (mpssvc), e é isso que
  // a tela diz. Não vira "você está protegido".
  const firewall = useLeituraSobDemanda('os_service_list', (data) => {
    const servicos = Array.isArray(data) ? (data as Array<{ Name?: string; Status?: unknown }>) : [];
    const mpssvc = servicos.find((x) => String(x?.Name || '').toLowerCase() === 'mpssvc');
    if (!mpssvc) return 'Serviço do firewall não encontrado';
    const estado = String(mpssvc.Status ?? '');
    return estado === '4' || estado.toLowerCase() === 'running'
      ? 'Serviço em execução'
      : `Serviço: ${estado || 'estado desconhecido'}`;
  });

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
          // Só acrescenta quando HÁ fatos: "0 fatos na memória" é ruído, não
          // informação.
          if (res?.success && Array.isArray(res.facts) && res.facts.length > 0) {
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
            <h2>Estado do dispositivo</h2>
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
          <h2>Manutenção</h2>
          <div className="zh-action-grid">
            <ActionCard
              icon={<Database size={16} strokeWidth={1.7} />}
              label="Liberar espaço"
              sub={lixeira.sub}
              onClick={lixeira.rodar}
              disabled={!lixeira.disponivel || lixeira.carregando}
            />
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
            <ActionCard
              icon={<Activity size={16} strokeWidth={1.7} />}
              label="Diagnóstico ZARA"
              sub={diagnosticLoading ? 'Analisando…' : diagnosticSummary ?? 'Verificar agora'}
              onClick={handleAnalisarAgora}
              disabled={diagnosticLoading || !window.zaraIPC?.system?.selfStatus}
            />
          </div>
        </div>

        <div className="zh-system-col zh-system-col--security">
          <h2>Segurança</h2>
          <ActionRow icon={<Search size={14} strokeWidth={1.7} />} label="Verificação rápida" sub="Indisponível" />
          <ActionRow icon={<ShieldCheck size={14} strokeWidth={1.7} />} label="Verificação completa" sub="Indisponível" />
          <ActionRow
            icon={<Shield size={14} strokeWidth={1.7} />}
            label="Firewall"
            sub={firewall.sub}
            onClick={firewall.rodar}
            disabled={!firewall.disponivel || firewall.carregando}
          />
          <ActionRow icon={<KeyRound size={14} strokeWidth={1.7} />} label="Permissões" sub="Indisponível" />
          <ActionRow icon={<Activity size={14} strokeWidth={1.7} />} label="Ameaças" sub="Indisponível" />
        </div>

        <div className="zh-system-col zh-system-col--energy">
          <h2>Energia</h2>
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
          <h2>Diagnóstico inteligente</h2>
          <p className="zh-diagnostic-title">Por que meu PC está lento?</p>
          <p className={diagnosticSummary ? 'zh-diagnostic-body' : 'zh-diagnostic-body zh-not-connected'}>
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
          {/* A onda vive no rodapé do card, como na MASTER — decoração que
            * fecha o card, não cabeçalho que empurra o título para baixo. */}
          <svg className="zh-diagnostic-wave" viewBox="0 0 200 40" preserveAspectRatio="none" aria-hidden="true">
            <path
              className="zh-diagnostic-wave-ghost"
              d="M0 34 C 30 34, 46 30, 66 26 S 104 22, 124 16 S 158 12, 200 2"
            />
            <path
              className="zh-diagnostic-wave-line"
              d="M0 36 C 30 36, 46 32, 66 28 S 104 24, 124 18 S 158 14, 200 4"
            />
          </svg>
        </div>
      </div>
    </section>
  );
}

import { useEffect, useState } from 'react';
import { Wifi, BatteryCharging, Battery, BatteryWarning } from 'lucide-react';
import '../../styles/zara-home.css';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { ForYouCard } from './ForYouCard';
import { CommunicationsCard } from './CommunicationsCard';
import { ActiveProjectCard } from './ActiveProjectCard';
import { ToolsCard } from './ToolsCard';
import { SystemPanel } from './SystemPanel';
import { ZaraCore } from './ZaraCore';
import { VoiceDock } from './VoiceDock';
import { useZaraCoreState } from './useZaraCoreState';
import { useSystemMetrics } from './useSystemMetrics';
import { useBattery } from './useBattery';
import auroraBackground from '../../../assets/zara-home/aurora-master-refined.png';

/**
 * Home real da ZARA (Titanium Emerald), renderizada como componentes React
 * de verdade — não um iframe apontando para um build estático separado.
 *
 * Composição (linhas/colunas) alinhada à referência real do Sites:
 * topo = coluna principal (saudação + comando + Para você + Comunicações)
 * ao lado de uma coluna direita ESTREITA (Projeto ativo + Ferramentas);
 * Core grande e centralizado entre as duas; Sistema como FAIXA HORIZONTAL
 * de largura total no rodapé (não empilhado dentro da coluna direita).
 *
 * Ver ZARA_HOME_UI_INTEGRATION.md para a auditoria completa de onde cada
 * cor/asset veio e o que ainda está NOT_CONNECTED_YET.
 */
export function ZaraHome() {
  const [activeNav, setActiveNav] = useState('Hoje');
  const coreState = useZaraCoreState();
  const metrics = useSystemMetrics();
  const battery = useBattery();
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);

  // TODO: nome/foto reais dependem de uma integração de conta ainda não
  // construída (Google/Microsoft) — fora do escopo desta missão, per
  // instrução explícita de não criar autenticação nova agora.
  const userName = 'Alex Silva';

  return (
    <div className="zh-root">
      <div
        className="zh-bg-glass"
        style={{ backgroundImage: `url(${auroraBackground})` }}
        aria-hidden="true"
      />
      <Sidebar active={activeNav} onSelect={setActiveNav} userName={userName} />

      <div className="zh-status-row" aria-label="Status">
        <Wifi size={15} strokeWidth={1.8} aria-label="Wi-Fi" />
        {battery.supported ? (
          battery.charging
            ? <BatteryCharging size={15} strokeWidth={1.8} aria-label={`Bateria ${Math.round((battery.level ?? 0) * 100)}%, carregando`} />
            : <Battery size={15} strokeWidth={1.8} aria-label={`Bateria ${Math.round((battery.level ?? 0) * 100)}%`} />
        ) : (
          <BatteryWarning size={15} strokeWidth={1.8} aria-label="Bateria não conectada" />
        )}
        <span>{now.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })}</span>
      </div>

      <div className="zh-content">
        <div className="zh-content-top">
          <main className="zh-main">
            <Header userFirstName={userName.split(' ')[0] ?? userName} />
            <ForYouCard />
            <CommunicationsCard />
          </main>

          <div className="zh-core-column">
            <ZaraCore state={coreState} />
            <VoiceDock coreState={coreState} />
          </div>

          <aside className="zh-right">
            <ActiveProjectCard />
            <ToolsCard />
          </aside>
        </div>

        <SystemPanel metrics={metrics} battery={battery} />
      </div>
    </div>
  );
}

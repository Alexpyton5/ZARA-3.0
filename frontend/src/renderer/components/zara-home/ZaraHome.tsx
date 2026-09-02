import { useState } from 'react';
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
import coreGlass from '../../../assets/zara-home/core-glass.png';

/**
 * Home real da ZARA (Titanium Emerald), renderizada como componentes React
 * de verdade — não um iframe apontando para um build estático separado.
 *
 * Ver ZARA_HOME_UI_INTEGRATION.md para a auditoria completa de onde cada
 * cor/asset veio e o que ainda está NOT_CONNECTED_YET.
 */
export function ZaraHome() {
  const [activeNav, setActiveNav] = useState('Hoje');
  const coreState = useZaraCoreState();
  const metrics = useSystemMetrics();
  const battery = useBattery();

  // TODO: nome/foto reais dependem de uma integração de conta ainda não
  // construída (Google/Microsoft) — fora do escopo desta missão, per
  // instrução explícita de não criar autenticação nova agora.
  const userName = 'Alex Silva';

  return (
    <div className="zh-root">
      <div
        className="zh-bg-glass"
        style={{ backgroundImage: `url(${coreGlass})` }}
        aria-hidden="true"
      />
      <Sidebar active={activeNav} onSelect={setActiveNav} userName={userName} />

      <main className="zh-main">
        <Header userFirstName={userName.split(' ')[0] ?? userName} />
        <ForYouCard />
        <CommunicationsCard />
        <ZaraCore state={coreState} />
      </main>

      <aside className="zh-right">
        <ActiveProjectCard />
        <ToolsCard />
        <SystemPanel metrics={metrics} battery={battery} />
      </aside>

      <VoiceDock coreState={coreState} />
    </div>
  );
}

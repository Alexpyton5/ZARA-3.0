import { useCallback, useState } from 'react';
import { Wifi, Shield, Cloud, Zap, Link2 } from 'lucide-react';
import '../../styles/zara-home.css';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { TextCommandInput } from './TextCommandInput';
import { ForYouCard } from './ForYouCard';
import { CommunicationsCard } from './CommunicationsCard';
import { ActiveProjectCard } from './ActiveProjectCard';
import { LabHomeCard } from './LabHomeCard';
import { SystemPanel } from './SystemPanel';
import { WindowControls } from './WindowControls';
import { ZaraCore } from './ZaraCore';
import { VoiceDock } from './VoiceDock';
import { useZaraCoreState } from './useZaraCoreState';
import { useSystemMetrics } from './useSystemMetrics';
import { useBattery } from './useBattery';
import { useWifiStatus } from './useWifiStatus';
import { usePowerPlans } from './usePowerPlans';
import { useClock } from './useClock';
import { HomeDrawer } from './HomeDrawer';
import { LabRoom } from '../zara-lab-v2/LabRoom';
import { ZoeAppPanel } from '../zara/ZoeAppPanel';
import auroraBackground from '../../../assets/zara-home/aurora-master-refined.png';

/** MASTER composition with connected data and the Lab product direction. */
export function ZaraHome() {
  const [activeNav, setActiveNav] = useState('Zoe');
  const closePanel = useCallback(() => setActiveNav('Hoje'), []);
  const navigate = useCallback((section: string) => setActiveNav(section), []);
  const coreState = useZaraCoreState();
  const metrics = useSystemMetrics();
  const battery = useBattery();
  const wifi = useWifiStatus();
  const power = usePowerPlans();
  const clock = useClock();

  // TODO: nome/foto reais dependem de uma integração de conta ainda não
  // construída (Google/Microsoft) — fora do escopo desta missão, per
  // instrução explícita de não criar autenticação nova agora.
  const userName = 'Alex';

  return (
    <div className="zh-root">
      <div
        className="zh-bg-glass"
        style={{ backgroundImage: `url(${auroraBackground})` }}
        aria-hidden="true"
      />
      <Sidebar active={activeNav} onSelect={navigate} userName={userName} />

      <div className="zh-status-row" aria-label="Status">
        <Shield size={15} strokeWidth={1.8} aria-label="Segurança — não conectada" data-unavailable="true" />
        <Wifi
          size={15}
          strokeWidth={1.8}
          aria-label={wifi.supported ? `Wi-Fi ${wifi.on ? 'ligado' : 'desligado'}` : 'Wi-Fi'}
          data-unavailable={wifi.supported ? undefined : 'true'}
          data-off={wifi.supported && !wifi.on ? 'true' : undefined}
        />
        <Cloud size={15} strokeWidth={1.8} aria-label="Nuvem — não conectada" data-unavailable="true" />
        <Link2 size={15} strokeWidth={1.8} aria-label="Conectividade — não conectada" data-unavailable="true" />
        {battery.supported ? (
          <span
            className="zh-battery-capsule"
            aria-label={`Bateria ${Math.round((battery.level ?? 0) * 100)}%${battery.charging ? ', carregando' : ''}`}
          >
            <span
              className="zh-battery-fill"
              data-low={battery.level !== null && battery.level <= 0.2 && !battery.charging ? 'true' : undefined}
              style={{ width: `${Math.max(6, Math.round((battery.level ?? 0) * 100))}%` }}
            />
            {battery.charging ? <Zap size={9} strokeWidth={3} className="zh-battery-bolt" /> : null}
          </span>
        ) : (
          <span className="zh-battery-capsule" data-unavailable="true" aria-label="Bateria não conectada" />
        )}
        <span className="zh-clock">
          <span className="zh-clock-time">
            {clock.time}
          </span>
          <span className="zh-clock-date">
            {clock.date}
          </span>
        </span>
        <WindowControls />
      </div>

      <div className="zh-zoe-workspace" hidden={activeNav !== 'Zoe'}><ZoeAppPanel visible={activeNav === 'Zoe'} /></div>
      {activeNav !== 'Zoe' && <div className="zh-content">
        <div className="zh-top-bar">
          <Header userFirstName={userName.split(' ')[0] ?? userName} />
          <div className="zh-top-bar-center">
            <TextCommandInput onSent={() => navigate('Conversas')} />
          </div>
          <div />
        </div>

        <div className="zh-content-top">
          <main className="zh-main">
            <ForYouCard onNavigate={navigate} />
            <CommunicationsCard onNavigate={navigate} />
          </main>

          <div className="zh-core-column">
            <ZaraCore state={coreState} />
            <VoiceDock coreState={coreState} onNavigate={navigate} />
          </div>

          <aside className="zh-right">
            <ActiveProjectCard onNavigate={navigate} />
            <LabHomeCard onNavigate={navigate} />
          </aside>
        </div>

        <SystemPanel metrics={metrics} battery={battery} wifi={wifi} power={power} />
      </div>}
      {activeNav === 'ZARA Lab' ? <LabRoom onClose={closePanel} /> : activeNav !== 'Hoje' && activeNav !== 'Zoe' && <HomeDrawer key={activeNav} section={activeNav} onClose={closePanel} onNavigate={navigate} />}
    </div>
  );
}

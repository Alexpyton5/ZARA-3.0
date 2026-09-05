import { useState } from 'react';
import { Wifi, Shield, Cloud, Zap, Link2 } from 'lucide-react';
import '../../styles/zara-home.css';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { TextCommandInput } from './TextCommandInput';
import { ForYouCard } from './ForYouCard';
import { CommunicationsCard } from './CommunicationsCard';
import { ActiveProjectCard } from './ActiveProjectCard';
import { ToolsCard } from './ToolsCard';
import { SystemPanel } from './SystemPanel';
import { WindowControls } from './WindowControls';
import { ZaraCore } from './ZaraCore';
import { VoiceDock } from './VoiceDock';
import { SectionView } from './SectionView';
import { ConversationStrip, useConversationFeed } from './ConversationStrip';
import { useZaraCoreState } from './useZaraCoreState';
import { useSystemMetrics } from './useSystemMetrics';
import { useBattery } from './useBattery';
import { useWifiStatus } from './useWifiStatus';
import { usePowerPlans } from './usePowerPlans';
import { useClock } from './useClock';
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
  const wifi = useWifiStatus();
  const power = usePowerPlans();
  const clock = useClock();
  const feed = useConversationFeed();
  const [awaitingReply, setAwaitingReply] = useState(false);

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

      <div className="zh-content">
        <div className="zh-top-bar">
          <Header userFirstName={userName.split(' ')[0] ?? userName} />
          <div className="zh-top-bar-center">
            <TextCommandInput
              onSent={(message) => { feed.push('user', message); setAwaitingReply(true); }}
              onReply={(reply) => {
                setAwaitingReply(false);
                if ('error' in reply) feed.push('system', reply.error);
                else feed.push('assistant', reply.content, reply.engine);
              }}
            />
            <ConversationStrip
              turns={feed.turns}
              pending={awaitingReply}
              onClear={feed.clear}
              onSeeAll={() => setActiveNav('Conversas')}
            />
          </div>
          <div />
        </div>

        {/* Cada item da Sidebar leva a algum lugar de verdade. "Hoje" é a Home
          * completa; "Sistema" é o mesmo painel de Sistema ocupando a tela; o
          * resto é a seção correspondente. Antes disso, 10 dos 11 itens só
          * trocavam o destaque e não mudavam nada na tela. */}
        {activeNav === 'Hoje' ? (
          <>
            <div className="zh-content-top">
              <main className="zh-main">
                <ForYouCard />
                <CommunicationsCard onSeeAll={() => setActiveNav('Conversas')} />
              </main>

              <div className="zh-core-column">
                <ZaraCore state={coreState} />
                <VoiceDock coreState={coreState} onNavigate={setActiveNav} />
              </div>

              <aside className="zh-right">
                <ActiveProjectCard />
                <ToolsCard />
              </aside>
            </div>

            <SystemPanel metrics={metrics} battery={battery} wifi={wifi} power={power} />
          </>
        ) : activeNav === 'Sistema' ? (
          <SystemPanel metrics={metrics} battery={battery} wifi={wifi} power={power} />
        ) : (
          <SectionView section={activeNav} />
        )}
      </div>
    </div>
  );
}

import { useEffect, useState } from 'react';
import { useTheme } from './theme/ThemeContext';
import { usePilotSession } from '../../lib/PilotSession';
import { PILOTS } from '../../lib/pilotConversation';
import { useZoeBridgeStatus } from '../../lib/zaraNovaIpc';

function saved(key: string, fallback: string) {
  try { return localStorage.getItem(key) || fallback; } catch { return fallback; }
}

export function Configuracoes({ onTrocar }: { onTrocar: () => void }) {
  const pilot = usePilotSession();
  const { theme, availableThemes } = useTheme();
  const bridge = useZoeBridgeStatus();
  const [density, setDensity] = useState(() => saved('zara-density', 'comfortable'));
  const [motion, setMotion] = useState(() => saved('zara-motion', 'system'));
  useEffect(() => {
    document.documentElement.dataset.density = density;
    document.documentElement.dataset.motion = motion;
    try { localStorage.setItem('zara-density', density); localStorage.setItem('zara-motion', motion); } catch { /* session preference remains applied */ }
  }, [density, motion]);
  return <section className="settings-grid" aria-label="Configurações">
    <section className="confidence-card">
      <h2>Seu piloto</h2>
      <p>{PILOTS[pilot.provider].nome} · {pilot.loading ? 'Conferindo a conta…' : pilot.connected ? 'Conversa disponível' : pilot.error || 'Conta ainda não conectada'}</p>
      <div className="settings-actions">
        <button className="primary-button" onClick={() => pilot.connect()}>{pilot.connected ? 'Abrir minha conta' : 'Conectar conta'}</button>
        <button className="secondary-button" onClick={onTrocar}>Trocar piloto e avatar</button>
      </div>
    </section>
    <section className="confidence-card">
      <h2>Do seu jeito</h2>
      <div className="pilot-theme-choice"><strong>{availableThemes.find(item => item.id === theme)?.rotulo || theme}</strong><span>O visual e os avatares acompanham o piloto selecionado.</span></div>
      <label>Espaçamento <select value={density} onChange={event => setDensity(event.target.value)}><option value="comfortable">Confortável</option><option value="compact">Compacto</option></select></label>
      <label>Movimento <select value={motion} onChange={event => setMotion(event.target.value)}><option value="system">Seguir o computador</option><option value="reduced">Reduzir animações</option></select></label>
    </section>
    <section className="confidence-card">
      <h2>Voz</h2>
      <label>Quem fala com você <select value={pilot.voice.engine} onChange={event => void pilot.voice.changeEngine(event.target.value === 'omnivoice' ? 'omnivoice' : 'kore')}><option value="kore">Kore</option><option value="omnivoice" disabled={!pilot.voice.omnivoiceAvailable}>OmniVoice{pilot.voice.omnivoiceAvailable ? '' : ' · indisponível'}</option></select></label>
      {pilot.voice.error && <p role="alert">{pilot.voice.error}</p>}
      <p>Ao abrir a conversa com sua conta Muse conectada, a voz inicia automaticamente. Você pode desligar o microfone a qualquer momento.</p>
    </section>
    <section className="confidence-card">
      <h2>Seu computador</h2>
      <p role="status">{bridge.unknown ? 'Verificando o canal do motor…' : bridge.ready ? 'Canal do motor disponível.' : 'Canal do motor indisponível.'}</p>
      <p>Ações no PC mostram o resultado do executor. A pausa da equipe controla o trabalho automático; comandos diretos são separados.</p>
    </section>
  </section>;
}

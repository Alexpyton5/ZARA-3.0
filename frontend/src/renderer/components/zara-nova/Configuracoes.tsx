import { useEffect, useState } from 'react';
import { useTheme } from './theme/ThemeContext';
import { usePilotSession } from '../../lib/PilotSession';
import { PILOTS } from '../../lib/pilotConversation';
import { useZoeBridgeStatus } from '../../lib/zaraNovaIpc';

function saved(key: string, fallback: string) {
  try { return localStorage.getItem(key) || fallback; } catch { return fallback; }
}

export function Configuracoes({ onTrocar }: { onTrocar: () => void }) {
  const [whatsAppFeedback, setWhatsAppFeedback] = useState('');
  async function openWhatsApp() {
    setWhatsAppFeedback('Abrindo WhatsApp Web…');
    try {
      const result = await window.zaraIPC?.desktop?.openExternal?.('whatsapp');
      if (result?.success !== true) throw new Error('Não consegui abrir o atalho.');
      setWhatsAppFeedback('WhatsApp Web aberto. A integração remota continua pendente.');
    } catch {
      setWhatsAppFeedback('Não consegui abrir o atalho do WhatsApp Web.');
    }
  }
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
      <p>Quem fala com você: <strong>Kore</strong> (com reserva automática se ela falhar).</p>
      {pilot.voice.error && <p role="alert">{pilot.voice.error}</p>}
      <p>Ao abrir a conversa com sua conta Muse conectada, a voz inicia automaticamente. Você pode desligar o microfone a qualquer momento.</p>
    </section>
    <section className="confidence-card">
      <h2>WhatsApp</h2>
      <p>WhatsApp Web — atalho disponível; integração remota pendente.</p>
      <p>O envio de ordens e a confirmação de ações pelo WhatsApp ainda não foram verificados.</p>
      <button className="secondary-button" onClick={() => void openWhatsApp()}>Abrir WhatsApp Web</button>
      {whatsAppFeedback && <p role="status">{whatsAppFeedback}</p>}
    </section>
    <section className="confidence-card">
      <h2>Seu computador</h2>
      <p role="status">{bridge.unknown ? 'Verificando o canal do motor…' : bridge.ready ? 'Canal do motor disponível.' : 'Canal do motor indisponível.'}</p>
      <p>Ações no PC mostram o resultado do executor. A pausa da equipe controla o trabalho automático; comandos diretos são separados.</p>
    </section>
  </section>;
}

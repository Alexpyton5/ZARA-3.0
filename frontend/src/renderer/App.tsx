import { useEffect, useState } from 'react';
import type { AvatarInfo, NavKey, AtividadeItem } from './components/zara-nova/types';
import { ThemeProvider, AVATAR_STORAGE_KEY } from './components/zara-nova/theme/ThemeContext';
import { ZaraNovaShell } from './components/zara-nova/chrome/ZaraNovaShell';
import { Entrada } from './components/zara-nova/Entrada';
import { Inicio } from './components/zara-nova/Inicio';
import { Conversa } from './components/zara-nova/Conversa';
import { Voz, mapearEstadoVoz } from './components/zara-nova/Voz';
import { Atividade } from './components/zara-nova/Atividade';
import { Equipe } from './components/zara-nova/Equipe';
import { Lab } from './components/zara-nova/Lab';
import { pilotAvatar } from './lib/pilotAvatars';
import { BotaoOperarComputador } from './lib/zaraNovaIpc';
import { PilotSessionProvider, usePilotSession } from './lib/PilotSession';
import { PILOTS, isPilotProvider } from './lib/pilotConversation';
import { Configuracoes } from './components/zara-nova/Configuracoes';
import { useNovaUi } from './lib/useNovaUi';
import { requireActionResult } from './lib/novaUiState';
import { useVoiceAutoStart, type VoiceStartRequest } from './lib/useVoiceAutoStart';

function readAvatar(): AvatarInfo | null {
  try {
    const id = localStorage.getItem(AVATAR_STORAGE_KEY);
    if (!id) return null;
    const provider = localStorage.getItem('zara-pilot-provider');
    return pilotAvatar(id, isPilotProvider(provider) ? provider : 'muse');
  } catch { return null; }
}

function TelasLogadas({ avatar, onTrocar }: { avatar: AvatarInfo; onTrocar: () => void }) {
  const [nav, setNav] = useState<NavKey>('inicio');
  const [modoLab, setModoLab] = useState<'equipe' | 'escritorio'>('equipe');
  const [notice, setNotice] = useState('');
  const [creating, setCreating] = useState(false);
  const [objective, setObjective] = useState('');
  const [projectBusy, setProjectBusy] = useState(false);
  const [pendingVoice, setPendingVoice] = useState<VoiceStartRequest | null>(null);
  const pilot = usePilotSession();
  const live = useNovaUi(pilot.provider);
  const run = async (action: () => Promise<unknown>) => {
    setNotice('');
    try { await action(); }
    catch (cause) { setNotice(cause instanceof Error ? cause.message : 'Não consegui concluir essa ação.'); }
  };
  const markVoiceAttempted = useVoiceAutoStart(
    pilot.provider === 'muse' && pilot.connected, nav === 'conversa', pilot.voice.voiceState,
    () => run(pilot.voice.toggle),
    { provider: pilot.provider, page: nav, ready: pilot.connected, accountOpen: pilot.accountOpen,
      request: pendingVoice, consume: fulfilled => {
        setPendingVoice(null);
        if (fulfilled) pilot.closeAccount();
      } },
  );
  const mic = () => {
    if (!pilot.connected) {
      setPendingVoice({ provider: pilot.provider, page: nav });
      pilot.connect();
      return;
    }
    setPendingVoice(null);
    markVoiceAttempted();
    void run(pilot.voice.toggle);
  };
  const result = (item: AtividadeItem) => void run(async () => {
    if (!item.entregavelUrl || !window.zaraIPC?.novaUI) throw new Error('O resultado está indisponível.');
    requireActionResult(await window.zaraIPC.novaUI.openResult(item.entregavelUrl), 'Não consegui abrir o resultado.');
  });
  const newProject = async () => {
    if (!objective.trim() || projectBusy) return;
    setProjectBusy(true);
    await run(async () => {
      const create = window.zaraIPC?.labV1?.createSession;
      if (!create) throw new Error('A criação de projetos está indisponível.');
      const reply = await create(objective.trim());
      if (reply?.success === false || reply?.error) throw new Error(reply?.error || 'O projeto não foi criado.');
      if (!reply?.session?.id && !reply?.session_id && !reply?.id) throw new Error('O motor não confirmou o projeto.');
      setCreating(false); setObjective(''); await live.refresh();
      setNav('equipe');
    });
    setProjectBusy(false);
  };
  const actions = <div className="page-actions">
    {nav !== 'conversa' && nav !== 'configuracoes' ? <button className="secondary-button" onClick={() => pilot.connect()}>Minha conta {PILOTS[pilot.provider].nome}</button> : null}
    <button className="primary-button" onClick={() => setCreating(true)}>Novo projeto</button>
  </div>;
  const state = live.state;
  return <ZaraNovaShell active={nav} onNavigate={setNav} pageActions={actions} avatar={avatar} providerName={PILOTS[pilot.provider].nome}>
    {state?.warning && <p role="status">{state.warning}</p>}
    {(notice || live.error || ((nav === 'voz' || nav === 'conversa') && pilot.voice.error)) && <p role="alert" style={{ padding: 12, border: '1px solid currentColor', borderRadius: 12 }}>{notice || live.error || pilot.voice.error}</p>}
    {(nav === 'conversa' || nav === 'voz') && !pilot.connected && <div className="pilot-connection-notice" role={pilot.error ? 'alert' : 'status'}>
      <span>{pilot.error || (pilot.loading ? 'Conferindo sua conta…' : 'Conecte sua conta para conversar por texto ou voz.')}</span>
      <button className="secondary-button" onClick={() => pilot.connect()}>{pilot.loading ? 'Abrir minha conta' : 'Conectar conta'}</button>
    </div>}
    {nav === 'inicio' && <Inicio cuidando={{ avatar, supervisionado: false }}
      emAndamento={(state?.work || []).filter(item => item.estado !== 'entregue')}
      entregas={(state?.work || []).filter(item => item.estado === 'entregue')}
      decisoes={state?.decisions || []} pausado={state?.paused === true}
      pilotoConectado={pilot.connected} pilotoCarregando={pilot.loading} pilotoErro={Boolean(pilot.error)}
      pausando={live.busy} estadoConfirmado={!!state && !live.error && state.paused !== null}
      onPausar={() => void run(live.pause)} onDecidir={(id, option) => void run(() => live.decide(id, option))}
      onConversar={() => setNav('conversa')} onVerOffice={() => { setModoLab('escritorio'); setNav('lab'); }} />}
    <div hidden={nav !== 'conversa'}><Conversa avatar={avatar} onEnviar={pilot.send}
      providerLabel={PILOTS[pilot.provider].nome}
      voz={{ estado: pilot.voice.voiceState, erro: pilot.voice.error, motor: pilot.voice.engine, alternar: mic }}
      onAbrirVoz={() => setNav('voz')} /></div>
    {nav === 'voz' && <Voz avatar={avatar} state={mapearEstadoVoz(pilot.voice.voiceState)} onMicClick={mic}
      motor={pilot.voice.engine} erro={pilot.voice.error} omnivoiceAvailable={pilot.voice.omnivoiceAvailable}
      onTrocarMotor={pilot.voice.changeEngine} />}
    {nav === 'atividade' && <Atividade itens={state?.activity || []} carregando={!state && !live.error} onAbrirEntrega={result} />}
    {nav === 'equipe' && <Equipe projetos={state?.projects || []} onNovoProjeto={() => setCreating(true)} />}
    {nav === 'lab' && <Lab projetos={state?.projects || []} modo={modoLab} onMudarModo={setModoLab} provider={pilot.provider} onNovoProjeto={() => setCreating(true)} />}
    {nav === 'configuracoes' && <Configuracoes onTrocar={onTrocar} />}
    {creating && <div className="project-dialog"><section className="confidence-card" role="dialog" aria-modal="true" aria-label="Novo projeto" onKeyDown={event => { if (event.key === 'Escape' && !projectBusy) setCreating(false); }}>
      <h2>O que você quer realizar?</h2>
      <form onSubmit={event => { event.preventDefault(); void newProject(); }}>
        <label>Nome ou objetivo do projeto <textarea value={objective} onChange={event => setObjective(event.target.value)} required autoFocus /></label>
        {notice && <p role="alert">{notice}</p>}
        <button type="submit" className="primary-button" disabled={projectBusy || !objective.trim()}>{projectBusy ? 'Criando…' : 'Criar projeto'}</button>{' '}
        <button type="button" className="secondary-button" disabled={projectBusy} onClick={() => setCreating(false)}>Voltar</button>
      </form>
    </section></div>}
  </ZaraNovaShell>;
}

function AppConteudo() {
  const [avatar, setAvatar] = useState<AvatarInfo | null>(readAvatar);
  const pilot = usePilotSession();
  useEffect(() => {
    try {
      document.documentElement.dataset.density = localStorage.getItem('zara-density') === 'compact' ? 'compact' : 'comfortable';
      document.documentElement.dataset.motion = localStorage.getItem('zara-motion') === 'reduced' ? 'reduced' : 'system';
    } catch { /* defaults remain accessible */ }
  }, []);
  return <ThemeProvider avatar={avatar} provider={pilot.provider}>
    {avatar ? <div style={{ width: '100vw', height: '100vh', position: 'relative' }}>
      <TelasLogadas avatar={avatar} onTrocar={() => { void pilot.voice.stop(); setAvatar(null); }} />
      <div style={{ position: 'absolute', right: 18, bottom: 18 }}><BotaoOperarComputador /></div>
    </div> : <Entrada onConcluir={setAvatar} onConectar={pilot.connect} provedor={pilot.provider} conectado={pilot.connected} />}
  </ThemeProvider>;
}

export default function App() {
  return <PilotSessionProvider><AppConteudo /></PilotSessionProvider>;
}

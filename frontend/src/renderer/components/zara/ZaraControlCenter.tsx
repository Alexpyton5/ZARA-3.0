import React, { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import { MemoryGalaxyModal } from './MemoryGalaxyModal';
import { PainelConfiguracoes, aplicarAparencia, useAparencia } from './PainelConfiguracoes';
import { ZaraLab } from './ZaraLab';
import { normalizeReminderEvent } from '../../../reminderEvents';
import { ChatMessage, normalizeHistoryResponse } from '../../lib/chatHistory';
import { iniciarAudioAec, pararAudioAec, tocarKore, cortarKore } from '../../lib/aecAudio';

type VoiceState = 'STANDBY' | 'IDLE' | 'LISTENING' | 'THINKING' | 'SPEAKING' | 'PROCESSING' | 'SLEEPING' | 'MUTED';
type Theme = 'light' | 'dark';

interface Toast { id: number; text: string; kind?: 'ok' | 'warn' | 'error'; }
interface EngineOption { id: string; name: string; provider: string; status?: string; }
interface MiniLabMessage { id: string; author: string; content: string; createdAt: number; }

const initialMessages: ChatMessage[] = [];

// Os ícones são os mesmos traços do desenho do Alex, redesenhados como componentes
// para não depender de uma biblioteca que muda de forma entre versões.
const IconeHoje = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M5 17.5 3.8 21l3.8-1.5a8.4 8.4 0 1 0-2.6-2Z"/></svg>;
const IconeMemorias = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M20.8 5.9c-2.1-2.1-5.4-2.1-7.5 0L12 7.2l-1.3-1.3a5.3 5.3 0 0 0-7.5 7.5L12 22l8.8-8.6a5.3 5.3 0 0 0 0-7.5Z"/></svg>;
const IconeRotinas = () => <svg viewBox="0 0 24 24" aria-hidden="true"><rect fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" x="3.5" y="5.2" width="17" height="15" rx="2"/><path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M8 3v4M16 3v4M3.5 9.2h17"/></svg>;
const IconeLab = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M9 3h6M10 3v6l-5.5 9.4A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.5-2.6L14 9V3M7.3 16h9.4"/></svg>;
const IconeSino = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M18 8.5a6 6 0 1 0-12 0c0 6-2 7-2 7h16s-2-1-2-7M13.7 20a2 2 0 0 1-3.4 0"/></svg>;
const IconeEscrever = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>;
const IconeMic = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M12 3a3 3 0 0 1 3 3v6a3 3 0 0 1-6 0V6a3 3 0 0 1 3-3ZM5 11a7 7 0 0 0 14 0M12 18v3"/></svg>;
const IconeMicMudo = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M3 3l18 18M9 9v3a3 3 0 0 0 4.6 2.5M15 11.5V6a3 3 0 0 0-5.7-1.3M5 11a7 7 0 0 0 10.5 6M12 18v3"/></svg>;
const IconeAviao = () => (
  <svg viewBox="0 0 24 24" aria-hidden="true">
    {/* Aponta para a FRENTE: a ponta esta em x=21.5 na mesma altura do centro.
        As versoes anteriores apontavam para cima e para o alto. */}
    <path fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
          d="M2.4 5.2 21.6 12 2.4 18.8 5.9 12 2.4 5.2Z"/>
    <path fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
          d="M5.9 12h15.7"/>
  </svg>
);
const IconeSol = () => <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4" fill="none" stroke="currentColor" strokeWidth="1.6"/><path fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>;
const IconeTema = () => <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" d="M4 7h4M12 7h8M4 17h8M16 17h4M10 4v6M14 14v6"/></svg>;

const navegacao = [
  { key: 'HOME', label: 'Hoje', Icone: IconeHoje },
  { key: 'MEMORY CORE', label: 'Memórias', Icone: IconeMemorias },
  { key: 'AUTOMATIONS', label: 'Rotinas', Icone: IconeRotinas },
  { key: 'CONVERSATIONS', label: 'ZARA LAB', Icone: IconeLab },
] as const;

// A classe de estado do anel é a mesma que o CSS do Alex já espera.
function classeDoAnel(state: VoiceState): string {
  if (state === 'LISTENING') return 'orb-listening';
  if (state === 'SPEAKING') return 'orb-speaking';
  return 'orb-idle';
}

function horaCurta(timestamp: number) {
  return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function normalizeLabMessages(raw: unknown): MiniLabMessage[] {
  if (!Array.isArray(raw)) return [];
  return raw.slice(-8).flatMap((entry: any, index: number) => {
    const content = typeof entry?.content === 'string' ? entry.content.trim() : '';
    if (!content) return [];
    const epoch = Number(entry?.created_at ?? 0);
    return [{
      id: String(entry?.id ?? `${epoch}-${index}`),
      author: String(entry?.author ?? 'zara'),
      content,
      createdAt: epoch > 0 && epoch < 10_000_000_000 ? epoch * 1000 : (epoch || Date.now()),
    }];
  });
}

// As cores dos balões do Lab são as do desenho: vinho, dourado e cinza.
function tomDoAutor(author: string): string {
  const a = author.toLowerCase();
  if (a.includes('claude')) return 'wine';
  if (a.includes('openai') || a.includes('codex') || a.includes('gpt')) return 'gold';
  if (a.includes('alex')) return 'wine';
  return 'gray';
}

export const ZaraControlCenter: React.FC = () => {
  const [activeNav, setActiveNav] = useState('HOME');
  // O tema deixou de ser um interruptor: ele e uma consequencia da aparencia
  // escolhida em Configuracoes, que tambem guarda cores, brilhos e tamanhos.
  const { aparencia, setAparencia, tema, desfazer, refazer, temPassado, temFuturo } = useAparencia();
  const theme: Theme = tema === 'claro' ? 'light' : 'dark';
  const [configAberta, setConfigAberta] = useState(false);
  const raizRef = useRef<HTMLElement>(null);
  const [state, setState] = useState<VoiceState>('STANDBY');
  const [voiceLevel, setVoiceLevel] = useState(0.02);
  const [tomDaVoz, setTomDaVoz] = useState(0.45);
  const [mudo, setMudo] = useState(false);
  const [voiceOn, setVoiceOn] = useState(false);
  const [supercerebro, setSupercerebro] = useState(false);
  const [galaxyOpen, setGalaxyOpen] = useState(false);
  // O lugar da direita nao e do Lab: e do que Alex escolher. O Lab e so o
  // primeiro inquilino. Pelos tres pontos ele troca o inquilino ou esvazia.
  const [painel, setPainel] = useState<'lab' | 'conversa'>(() => (localStorage.getItem('zara-painel') as 'lab' | 'conversa') || 'lab');
  const [painelVisivel, setPainelVisivel] = useState(() => localStorage.getItem('zara-painel-visivel') !== 'nao');
  const [menuAberto, setMenuAberto] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [historyReady, setHistoryReady] = useState(false);
  const [clearingHistory, setClearingHistory] = useState(false);
  const [input, setInput] = useState('');
  const [metrics, setMetrics] = useState({ cpu: 0, memory: 0, network: 0, storage: 0 });
  const [backendOnline, setBackendOnline] = useState(false);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [busy, setBusy] = useState(false);
  const [engines, setEngines] = useState<EngineOption[]>([]);
  const [selectedEngine, setSelectedEngine] = useState('auto_smart');
  const [voiceLabel, setVoiceLabel] = useState('GEMINI LIVE • KORE');
  const [miniLabMessages, setMiniLabMessages] = useState<MiniLabMessage[]>([]);
  const [miniLabInput, setMiniLabInput] = useState('');
  const [miniLabBusy, setMiniLabBusy] = useState(false);
  const [miniLabOnline, setMiniLabOnline] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);
  const labFimRef = useRef<HTMLDivElement>(null);
  const toastIdRef = useRef(0);
  const historyReadyRef = useRef(false);
  const pendingHistoryMessagesRef = useRef<ChatMessage[]>([]);
  const autoVoiceStartedRef = useRef(false);
  const anelRef = useRef<HTMLDivElement>(null);
  const deslocamentoRef = useRef<SVGFEDisplacementMapElement>(null);
  const deslizeRef = useRef<SVGFEOffsetElement>(null);
  const faiscasRef = useRef<HTMLCanvasElement>(null);
  // O laco de animacao le daqui em vez de depender das props, senao ele se
  // reinicia a cada quadro de voz e a animacao engasga.
  const vivoRef = useRef({ estado: 'STANDBY' as VoiceState, nivel: 0.02, tom: 0.45 });

  const notify = useCallback((text: string, kind: Toast['kind'] = 'ok') => {
    toastIdRef.current += 1;
    const id = toastIdRef.current;
    setToasts((current) => [...current.slice(-2), { id, text, kind }]);
    window.setTimeout(() => setToasts((current) => current.filter((item) => item.id !== id)), 3200);
  }, []);

  // Toda mudanca de regulador cai aqui e vira variavel CSS na hora.
  useEffect(() => { aplicarAparencia(raizRef.current, aparencia); }, [aparencia]);
  useEffect(() => { localStorage.setItem('zara-painel', painel); }, [painel]);
  useEffect(() => { localStorage.setItem('zara-painel-visivel', painelVisivel ? 'sim' : 'nao'); }, [painelVisivel]);

  const escolherPainel = (qual: 'lab' | 'conversa') => { setPainel(qual); setPainelVisivel(true); setMenuAberto(false); };

  // ZARA-AEC-RENDERER-001. Só abre o microfone aqui quando o backend disser que
  // ele é o dono do áudio; no modo local o PortAudio já capturou, e duas capturas
  // concorrentes brigariam pelo dispositivo.
  const ligarAecSePreciso = useCallback(async (resultado: { audio_transport?: string } | null) => {
    if (resultado?.audio_transport !== 'renderer') return;
    const r = await iniciarAudioAec((pcm) => window.zaraIPC?.voice?.sendMicChunk?.(pcm));
    if (!r.ok) { notify('Não consegui abrir o microfone; a voz não vai ouvir você.', 'error'); return; }
    if (!r.aecAtivo) notify('Microfone aberto sem cancelamento de eco — ela pode se ouvir falar.', 'warn');
  }, [notify]);

  // ZARA-BOTAO-MUDO-005 — o backend guarda a escolha; o botão abre na cor certa.
  useEffect(() => {
    let vivo = true;
    window.zaraIPC?.voice?.mute?.()
      .then((r) => { if (vivo && r && typeof r.mudo === 'boolean') setMudo(r.mudo); })
      .catch(() => {});
    return () => { vivo = false; };
  }, []);

  useEffect(() => {
    const api = window.zaraIPC;
    if (!api) return;
    const offs: Array<() => void> = [];

    if (api.on?.stateChange) offs.push(api.on.stateChange((nextState: string) => setState(nextState as VoiceState)));
    // ZARA-AEC-RENDERER-001: a voz da Kore toca AQUI, no mesmo processo que captura
    // o microfone. É isso que dá ao AEC do Chromium o sinal de referência.
    if (api.on?.voiceOutputAudio) offs.push(api.on.voiceOutputAudio((data) => {
      if (data?.stop) { cortarKore(); return; }
      if (data?.pcm) tocarKore(data.pcm, data.sampleRate || 24000);
    }));
    if (api.on?.voiceLevel) offs.push(api.on.voiceLevel((level: number, tone: number, speaking: boolean) => {
      setVoiceLevel(Math.max(0, Math.min(1, level || 0)));
      if (typeof tone === 'number' && Number.isFinite(tone)) setTomDaVoz(Math.max(0, Math.min(1, tone)));
      if (speaking) setState('SPEAKING');
    }));
    if (api.on?.message) offs.push(api.on.message((message: { role: string; content: string }) => {
      if (!message?.content) return;
      const incoming: ChatMessage = {
        role: message.role === 'user' ? 'user' : message.role === 'system' ? 'system' : 'assistant',
        content: message.content,
        timestamp: Date.now(),
      };
      if (!historyReadyRef.current) pendingHistoryMessagesRef.current.push(incoming);
      else setMessages((current) => [...current, incoming]);
    }));
    if (api.on?.metrics) offs.push(api.on.metrics((nextMetrics: any) => {
      setMetrics((current) => ({
        cpu: Number(nextMetrics?.cpu ?? current.cpu),
        memory: Number(nextMetrics?.ram ?? nextMetrics?.memory ?? current.memory),
        network: Number(nextMetrics?.network ?? current.network),
        storage: Number(nextMetrics?.storage ?? nextMetrics?.disk ?? current.storage),
      }));
    }));
    if (api.on?.supercerebroChange) offs.push(api.on.supercerebroChange((active: boolean) => setSupercerebro(Boolean(active))));
    if (api.on?.reminderFired) offs.push(api.on.reminderFired((rawReminder: unknown) => {
      const reminder = normalizeReminderEvent(rawReminder);
      if (!reminder) return;
      const incoming: ChatMessage = { role: 'assistant', content: `🔔 Lembrete: ${reminder.text}`, timestamp: Date.now() };
      if (!historyReadyRef.current) pendingHistoryMessagesRef.current.push(incoming);
      else setMessages((current) => [...current, incoming]);
      notify(`🔔 ${reminder.text}`);
    }));

    const completeHistoryLoad = (persisted: ChatMessage[]) => {
      const pending = pendingHistoryMessagesRef.current;
      pendingHistoryMessagesRef.current = [];
      historyReadyRef.current = true;
      setMessages([...persisted, ...pending]);
      setHistoryReady(true);
    };

    const historyPromise = api.conversationHistory?.list?.(500);
    if (historyPromise) historyPromise.then((result: unknown) => completeHistoryLoad(normalizeHistoryResponse(result))).catch(() => completeHistoryLoad([]));
    else void Promise.resolve().then(() => completeHistoryLoad([]));

    const engineListPromise = api.engine?.list?.();
    if (engineListPromise) {
      engineListPromise.then((result: any) => {
        const list: EngineOption[] = Array.isArray(result?.engines) ? result.engines : [];
        setEngines(list);
        const ids = new Set(list.map((engine) => engine.id));
        const preferred = String(result?.current || localStorage.getItem('zara-ai-engine') || 'auto_smart');
        const next = ids.has(preferred) ? preferred : ids.has('auto_smart') ? 'auto_smart' : (list[0]?.id || 'auto_smart');
        setSelectedEngine(next);
        localStorage.setItem('zara-ai-engine', next);
        const changePromise = api.engine?.change?.(next);
        if (changePromise) void changePromise.catch(() => undefined);
        if (result?.voice?.voice) setVoiceLabel(`${result.voice.name || 'GEMINI LIVE'} • ${result.voice.voice}`.toUpperCase());
      }).catch(() => {
        setEngines([
          { id: 'auto_smart', name: 'AUTO • INTELIGENTE', provider: 'zara' },
          { id: 'auto_economy', name: 'AUTO • ECONÔMICO', provider: 'zara' },
        ]);
        setSelectedEngine('auto_smart');
      });
    }

    const refreshBackend = () => {
      api.system?.metrics?.().then((nextMetrics: any) => {
        setBackendOnline(true);
        setMetrics((current) => ({
          cpu: Number(nextMetrics?.cpu ?? current.cpu), memory: Number(nextMetrics?.ram ?? current.memory),
          network: Number(nextMetrics?.network ?? current.network), storage: Number(nextMetrics?.storage ?? nextMetrics?.disk ?? current.storage),
        }));
      }).catch(() => setBackendOnline(false));
      api.supercerebro?.status?.().then((result: any) => setSupercerebro(Boolean(result?.active && result?.connected))).catch(() => setSupercerebro(false));
    };

    refreshBackend();
    // A ZARA é voice-first: ela sobe ouvindo, sem Alex ter que clicar em nada.
    if (!autoVoiceStartedRef.current) {
      autoVoiceStartedRef.current = true;
      setState('PROCESSING');
      api.voice?.start?.().then(async (result: any) => {
        await ligarAecSePreciso(result);
        if (result?.mode === 'gemini_live') setVoiceLabel(`GEMINI LIVE • ${String(result?.voice || 'Kore').toUpperCase()}`);
        else if (result?.mode) setVoiceLabel(String(result.mode).toUpperCase());
        setVoiceOn(true);
        setState(result?.wake_mode ? 'IDLE' : 'LISTENING');
      }).catch(() => {
        setVoiceOn(false);
        setState('STANDBY');
        notify('Voz automática indisponível; o chat de texto continua ativo.', 'warn');
      });
    }
    const refreshTimer = window.setInterval(refreshBackend, 5000);
    return () => {
      window.clearInterval(refreshTimer);
      offs.forEach((off) => off());
    };
  }, [notify, ligarAecSePreciso]);

  useEffect(() => { vivoRef.current = { estado: state, nivel: voiceLevel, tom: tomDaVoz }; }, [state, voiceLevel, tomDaVoz]);

  // ZARA-ANEL-VIVO-001
  // O anel do Alex nao "gira": ele TREME. Tres coisas fazem isso, e nenhuma
  // delas eu tinha: o deslocamento em pixel (--jitter-x/y), a frequencia da
  // turbulencia acompanhando o tom da voz, e os pontinhos de luz no canvas.
  // Sem elas o desenho parece um GIF girando.
  useEffect(() => {
    const anel = anelRef.current;
    const canvas = faiscasRef.current;
    if (!anel || !canvas) return;
    const contexto = canvas.getContext('2d');
    const semMovimento = Boolean(window.matchMedia?.('(prefers-reduced-motion: reduce)')?.matches);

    // Brilhos que VIAJAM pela circunferencia, como no video que Alex mandou:
    // pontos de luz concentrada que percorrem o anel acendendo e apagando. Sao
    // desenhados em vetor no canvas, entao ficam nitidos em qualquer tamanho —
    // e por isso nao granulam a imagem, que era o medo dele.
    const corDoAnel = () => getComputedStyle(anel).getPropertyValue('--ring').trim() || '#a8c3a0';

    const faiscas = Array.from({ length: 30 }, (_, i) => {
      const r = (n: number) => { const v = Math.sin((i + 1) * (12.9898 + n * 7.233)) * 43758.5453; return v - Math.floor(v); };
      return {
        angulo: r(0.11) * Math.PI * 2,
        velocidade: (r(0.37) > 0.5 ? 1 : -1) * (0.04 + r(0.53) * 0.16),
        raio: 0.298 + r(0.71) * 0.062,
        tamanho: 0.7 + r(0.89) * 1.5,
        fase: r(1.13) * Math.PI * 2,
        cintilar: 1.1 + r(1.31) * 2.4,
      };
    });

    let jx = 0, jy = 0, alvoX = 0, alvoY = 0, energia = 0.02, deriva = 0;
    let quadro = 0, anterior = performance.now();

    const passo = (agora: number) => {
      const dt = Math.min(0.05, Math.max(0.001, (agora - anterior) / 1000));
      anterior = agora;
      const { estado, nivel, tom } = vivoRef.current;
      const ativo = estado === 'SPEAKING' || estado === 'LISTENING';
      const mudo = estado === 'MUTED' || estado === 'SLEEPING';
      const alvo = mudo ? 0.012 : ativo ? Math.max(nivel, 0.08) : 0.045;
      energia += (alvo - energia) * Math.min(1, dt * 6);

      if (!semMovimento) {
        // Tremor: um alvo novo de vez em quando e o anel perseguindo ele. Sorteio
        // a cada quadro daria chiado de TV, nao vibracao de corda.
        if (Math.random() < 0.22) {
          // Este tremor move o anel INTEIRO, entao ele agora e discreto: quem
          // carrega a vida e o movimento fio a fio, nao o bloco balancando.
          const amplitude = 0.18 + energia * 1.3;   // piso pequeno: vivo mesmo calada
          alvoX = (Math.random() * 2 - 1) * amplitude;
          alvoY = (Math.random() * 2 - 1) * amplitude;
        }
        jx += (alvoX - jx) * Math.min(1, dt * 14);
        jy += (alvoY - jy) * Math.min(1, dt * 14);
      }

      anel.style.setProperty('--audio-level', energia.toFixed(3));
      anel.style.setProperty('--audio-tone', tom.toFixed(3));
      anel.style.setProperty('--jitter-x', `${jx.toFixed(2)}px`);
      anel.style.setProperty('--jitter-y', `${jy.toFixed(2)}px`);

      // ---- cada fio com o seu proprio movimento ----
      // A causa do "lencol" era a frequencia horizontal do ruido: 0.0132 e uma
      // onda de ~76px num anel onde um fio esta a ~7px do outro. Todos pegavam
      // o MESMO empurrao. Agora o ruido e fino e igual nos dois eixos: ele muda
      // dentro do vao entre um fio e o vizinho, entao cada um recebe um
      // deslocamento diferente. O campo de ruido tambem passeia (feOffset), e e
      // isso que faz a vibracao correr ao longo do fio em vez de ferver parada.
      // A DISTANCIA media nao muda: o deslocamento e centrado em zero e a
      // amplitude fica bem abaixo do espaco entre os fios.
      const escala = (ativo ? 2.2 + energia * 4.6 : 1.3 + energia * 2.4) * (0.9 + tom * 0.2);
      anel.setAttribute('data-cord-scale', escala.toFixed(2));
      deslocamentoRef.current?.setAttribute('scale', escala.toFixed(2));
      // Passeio acumulado em vez de multiplicar o relogio: mudar a velocidade
      // no meio do caminho daria um salto de fase, e o salto aparece como tranco.
      deriva += dt * (0.58 + energia * 1.15 + tom * 0.25);
      deslizeRef.current?.setAttribute('dx', (Math.sin(deriva * 0.83) * 17 + Math.sin(deriva * 1.47 + 1.7) * 9).toFixed(2));
      deslizeRef.current?.setAttribute('dy', (Math.sin(deriva * 0.71 + 0.6) * 15 + Math.sin(deriva * 1.29 + 2.9) * 8).toFixed(2));

      if (contexto) {
        const lado = canvas.clientWidth || 214;
        const dpr = window.devicePixelRatio || 1;
        if (canvas.width !== Math.round(lado * dpr)) {
          canvas.width = Math.round(lado * dpr);
          canvas.height = Math.round(lado * dpr);
        }
        contexto.setTransform(dpr, 0, 0, dpr, 0, 0);
        contexto.clearRect(0, 0, lado, lado);
        const cx = lado / 2, cy = lado / 2;
        const segundos = agora / 1000;
        const claro0 = anel.closest('.theme-light') !== null;

        // O canvas volta a fazer so o que ele fazia no desenho do Alex: as
        // faiscas. O giro e a vibracao sao do PROPRIO anel — giro por CSS,
        // vibracao pelo filtro de turbulencia. Nada e desenhado por cima dele.
        const cor = corDoAnel();
        const claro = claro0;
        for (const f of faiscas) {
          if (!semMovimento) f.angulo += f.velocidade * dt;
          const pulsa = 0.5 + 0.5 * Math.sin(segundos * f.cintilar + f.fase);
          const alfa = mudo ? 0.05 : (0.12 + energia * 0.75) * pulsa;
          if (alfa < 0.02) continue;
          const raio = lado * (f.raio + Math.sin(segundos * 0.4 + f.fase) * 0.006);
          const x = cx + Math.cos(f.angulo) * raio;
          const y = cy + Math.sin(f.angulo) * raio;
          const tamanho = f.tamanho * (0.75 + energia * 0.9);
          // No claro a faisca branca sumia no creme e sobrava so a sombra em
          // volta: viravam argolinhas, que Alex viu como sujeira. La ela e
          // escura, da cor do anel, e sem halo.
          contexto.globalAlpha = Math.min(1, claro ? alfa * 0.75 : alfa);
          contexto.fillStyle = claro ? cor : '#f3f7ef';
          contexto.shadowColor = claro ? 'transparent' : 'rgba(214,235,205,.9)';
          contexto.shadowBlur = claro ? 0 : 5 + energia * 9;
          contexto.beginPath();
          contexto.arc(x, y, tamanho, 0, Math.PI * 2);
          contexto.fill();
        }
        contexto.globalAlpha = 1;
        contexto.shadowBlur = 0;
      }

      quadro = window.requestAnimationFrame(passo);
    };

    quadro = window.requestAnimationFrame(passo);
    return () => window.cancelAnimationFrame(quadro);
  }, []);

  const refreshMiniLab = useCallback(async () => {
    try {
      const snapshot: any = await window.zaraIPC?.lab?.state?.();
      if (!snapshot || !Array.isArray(snapshot.messages)) throw new Error('Estado do Lab indisponível');
      setMiniLabMessages(normalizeLabMessages(snapshot.messages));
      setMiniLabOnline(true);
    } catch {
      setMiniLabOnline(false);
    }
  }, []);

  useEffect(() => {
    // A primeira busca sai da pilha do efeito de propósito: chamada direto ali,
    // ela dispara setState durante a montagem e cascateia render.
    const primeira = window.setTimeout(() => void refreshMiniLab(), 0);
    const timer = window.setInterval(() => void refreshMiniLab(), 3000);
    return () => { window.clearTimeout(primeira); window.clearInterval(timer); };
  }, [refreshMiniLab]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    labFimRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [miniLabMessages]);

  // Este botão controla se ela OUVE. O da onda controla se ela FALA.
  const toggleVoice = async () => {
    try {
      if (voiceOn) {
        await window.zaraIPC?.voice?.stop?.();
        pararAudioAec();
        setVoiceOn(false); setState('MUTED'); setVoiceLevel(0.02);
      } else {
        setState('PROCESSING');
        const result: any = await window.zaraIPC?.voice?.start?.();
        await ligarAecSePreciso(result);
        if (result?.mode === 'gemini_live') setVoiceLabel(`GEMINI LIVE • ${String(result?.voice || 'Kore').toUpperCase()}`);
        else if (result?.mode) setVoiceLabel(String(result.mode).toUpperCase());
        setVoiceOn(true); setState('LISTENING');
      }
    } catch {
      setVoiceOn(false); setState('STANDBY');
      notify('O módulo de voz ainda não está disponível.', 'error');
    }
  };

  // ZARA-BOTAO-MUDO-001 / 003 — calar a voz sem desligar a ZARA. Ela continua
  // ouvindo, entendendo e executando; só para de falar.
  const alternarMudo = async () => {
    const desejado = !mudo;
    setMudo(desejado);
    try {
      const r = await window.zaraIPC?.voice?.mute?.(desejado);
      if (r && typeof r.mudo === 'boolean' && r.mudo !== desejado) setMudo(r.mudo);
      notify(desejado ? 'Ela parou de falar. Continua ouvindo e executando.' : 'Ela voltou a falar.');
    } catch {
      setMudo(!desejado);
      notify('Não consegui mudar isso agora.', 'error');
    }
  };

  const send = async (event?: FormEvent) => {
    event?.preventDefault();
    const text = input.trim();
    if (!text || busy) return;
    if (!historyReady) { notify('A conversa ainda está sendo carregada.', 'warn'); return; }
    const userMessage: ChatMessage = { role: 'user', content: text, timestamp: Date.now() };
    setMessages((current) => [...current, userMessage]);
    setInput('');
    setBusy(true);
    setState('THINKING');
    try {
      const history = [...messages, userMessage]
        .filter((message) => message.role !== 'system')
        .slice(-16)
        .map((message) => ({ role: message.role === 'assistant' ? 'assistant' : 'user', content: message.content }));
      const response: any = await window.zaraIPC?.message?.send?.({ message: text, engine: selectedEngine, history });
      const content = String(response?.content ?? response?.response ?? response?.message ?? response ?? '').trim();
      if (content) setMessages((current) => [...current, { role: 'assistant', content, timestamp: Date.now() }]);
    } catch {
      setMessages((current) => [...current, { role: 'system', content: 'Backend indisponível para esta solicitação.', timestamp: Date.now() }]);
    } finally {
      setBusy(false);
      setState(voiceOn ? 'LISTENING' : 'STANDBY');
    }
  };

  const sendMiniLab = async (event?: FormEvent) => {
    event?.preventDefault();
    const content = miniLabInput.trim();
    if (!content || miniLabBusy) return;
    setMiniLabBusy(true);
    setMiniLabInput('');
    try {
      const sender = window.zaraIPC?.lab?.send;
      if (!sender) throw new Error('IPC do Lab indisponível');
      await sender({ author: 'alex', target: 'zara', content });
      await refreshMiniLab();
    } catch {
      setMiniLabInput(content);
      notify('Não foi possível participar do ZARA Lab agora.', 'error');
    } finally {
      setMiniLabBusy(false);
    }
  };

  const clearConversationHistory = async () => {
    if (clearingHistory || busy || voiceOn || !historyReady) return;
    if (!window.confirm('Apagar definitivamente o histórico de conversas desta ZARA?')) return;
    setClearingHistory(true);
    try {
      const clear = window.zaraIPC?.conversationHistory?.clear;
      if (!clear) throw new Error('IPC de histórico indisponível');
      const result: any = await clear();
      if (!result?.success) throw new Error('Limpeza não confirmada');
      setMessages([]);
      notify('Histórico de conversas apagado.');
    } catch {
      notify('Não foi possível apagar o histórico.', 'error');
    } finally {
      setClearingHistory(false);
    }
  };

  const changeEngine = async (engine: string) => {
    const previous = selectedEngine;
    setSelectedEngine(engine);
    try {
      const result: any = await window.zaraIPC?.engine?.change?.(engine);
      if (!result?.success) throw new Error('Engine não confirmado pelo backend');
      localStorage.setItem('zara-ai-engine', engine);
    } catch {
      setSelectedEngine(previous);
      notify('Este motor não está disponível com as chaves atuais.', 'error');
    }
  };

  const toggleSuper = async () => {
    const next = !supercerebro;
    try {
      const toggle = window.zaraIPC?.supercerebro?.toggle;
      if (!toggle) throw new Error('IPC do Supercérebro indisponível');
      const result: any = await toggle(next);
      if (!result || typeof result.active !== 'boolean') throw new Error('Resposta inválida do backend');
      const actual = Boolean(result.active && (next ? result.connected : true));
      setSupercerebro(actual);
      notify(`Supercérebro ${actual ? 'ativado' : 'desativado'}.`);
    } catch {
      setSupercerebro(false);
      notify('O gateway Hermes não confirmou a ativação.', 'error');
    }
  };

  const runDiagnostics = async () => {
    try {
      const nextMetrics: any = await window.zaraIPC?.system?.metrics?.();
      if (nextMetrics) {
        setBackendOnline(true);
        setMetrics((current) => ({
          cpu: Number(nextMetrics.cpu ?? current.cpu), memory: Number(nextMetrics.ram ?? current.memory),
          network: Number(nextMetrics.network ?? current.network), storage: Number(nextMetrics.storage ?? nextMetrics.disk ?? current.storage),
        }));
      }
      notify('Métricas atualizadas.');
    } catch {
      setBackendOnline(false);
      notify('Diagnóstico indisponível no backend atual.', 'error');
    }
  };

  const handleNavigation = (key: string) => {
    if (key === 'MEMORY CORE') { setGalaxyOpen(true); return; }
    if (key === 'AUTOMATIONS') { notify('Rotinas aparecerão aqui quando o módulo estiver disponível.', 'warn'); return; }
    setActiveNav(key);
  };


  return (
    <main ref={raizRef} className={`zara-preview theme-${theme} ${classeDoAnel(state)}`}>
      <section className="desktop-frame" aria-label="Interface da ZARA">
        <section className="main-window">
          <aside className="sidebar">
            <button type="button" className="brand" aria-label="ZARA" onClick={() => setActiveNav('HOME')}>
              <img className="brand-light" src="./zara-brand-light.png?v=6" alt="ZARA"/>
              <img className="brand-dark" src="./zara-brand-dark.png?v=6" alt="ZARA"/>
            </button>

            <nav aria-label="Navegação principal">
              {navegacao.map(({ key, label, Icone }) => (
                <button type="button" key={key} className={activeNav === key ? 'active' : ''} onClick={() => handleNavigation(key)}>
                  <Icone/><span>{label}</span>
                </button>
              ))}
            </nav>

            <footer>
              <div className="online-row">
                <i className={backendOnline ? 'online' : ''}/>
                <span>{backendOnline ? 'ONLINE' : 'OFFLINE'}</span>
                <button type="button" aria-label="Configurações de aparência" title="Aparência" onClick={() => setConfigAberta(true)}><IconeTema/></button>
              </div>
              <div className="user-row">
                <img src="./avatar-alex.png?v=6" alt=""/>
                <span>⌄</span>
              </div>
            </footer>
          </aside>

          <div className="main-actions">
            <button type="button" aria-label="Diagnóstico" onClick={() => void runDiagnostics()} title={`CPU ${metrics.cpu.toFixed(0)}% • Memória ${metrics.memory.toFixed(0)}%`}><IconeSino/></button>
            <button type="button" aria-label="Limpar conversa" disabled={clearingHistory || busy || voiceOn || !historyReady} onClick={() => void clearConversationHistory()}><IconeEscrever/></button>
          </div>

          {activeNav === 'CONVERSATIONS' ? (
            <section className="home-stage"><div className="lab-cheio"><ZaraLab /></div></section>
          ) : (
            <section className="home-stage">
              <div className="presence-stage">
                <div
                  ref={anelRef}
                  className="orb"
                  aria-label={`Estado do anel: ${state.toLowerCase()}`}
                >
                  <svg className="orb-filter-defs" width="0" height="0" aria-hidden="true">
                    <defs>
                      <filter id="zara-cord-vibration" x="-24%" y="-24%" width="148%" height="148%" colorInterpolationFilters="sRGB">
                        {/* Ruido fino e igual nos dois eixos: como ele varia dentro do
                            vao entre um fio e o vizinho, cada fio recebe um empurrao
                            diferente. Grosso demais e o anel vira um lencol so. */}
                        <feTurbulence type="fractalNoise" baseFrequency="0.055 0.059"
                                      numOctaves={2} seed={7} result="cordNoise"/>
                        {/* O campo de ruido passeia; e o passeio que faz a onda CORRER
                            pelo fio. A borda descoberta pelo deslize cai fora do anel,
                            porque a regiao do filtro sobra 24% de cada lado. */}
                        <feOffset ref={deslizeRef} in="cordNoise" dx="0" dy="0" result="cordNoiseDrift"/>
                        <feDisplacementMap ref={deslocamentoRef} in="SourceGraphic" in2="cordNoiseDrift"
                                           scale="0" xChannelSelector="R" yChannelSelector="G"/>
                      </filter>
                    </defs>
                  </svg>
                  <canvas ref={faiscasRef} className="spectrum-canvas" aria-hidden="true" width={214} height={214}/>
                  <img className="ring-light ring-base" src="./zara-ring-light.png?v=6" alt="Presença luminosa da ZARA"/>
                  <img className="ring-dark ring-base" src="./zara-ring-dark.png?v=6" alt=""/>
                </div>

                <form className="command-bar" onSubmit={send}>
                  <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Como posso pensar com você hoje?" aria-label="Mensagem para ZARA"/>
                  {/* microfone = ela OUVE; onda = ela FALA. Duas coisas diferentes. */}
                  <button
                    type="button"
                    className={`mic-button ${voiceOn ? 'ligado' : 'desligado'}`}
                    onClick={() => void toggleVoice()}
                    aria-pressed={voiceOn}
                    aria-label={voiceOn ? 'Microfone ligado — clique para travar' : 'Microfone travado — clique para ela ouvir'}
                    title={voiceOn ? `Ela está te ouvindo (${voiceLabel}). Clique para travar o microfone.` : 'Microfone travado. Ela não ouve nada.'}
                  >
                    {voiceOn ? <IconeMic/> : <IconeMicMudo/>}
                  </button>
                  <button
                    type="button"
                    className={`voice-button ${mudo ? 'desligado' : 'ligado'}`}
                    onClick={() => void alternarMudo()}
                    aria-pressed={!mudo}
                    aria-label={mudo ? 'Voz silenciada — clique para ela voltar a falar' : 'Silenciar a voz dela'}
                    title={mudo ? 'Calada. Clique para ela voltar a falar.' : 'Ela fala. Clique para calar (continua ouvindo e executando).'}
                  >
                    <span className="voice-bars"><i/><i/><i/><i/><i/></span>
                  </button>
                </form>

              </div>

              <aside className="today-card">
                <header>
                  <div><IconeSol/><strong>Hoje</strong></div>
                  <div className="menu-painel">
                    <button type="button" aria-haspopup="menu" aria-expanded={menuAberto} aria-label="Escolher o que aparece no painel" onClick={() => setMenuAberto((v) => !v)}>•••</button>
                    {menuAberto && (
                      <div className="menu-opcoes" role="menu">
                        <button type="button" role="menuitem" className={painelVisivel && painel === 'lab' ? 'marcado' : ''} onClick={() => escolherPainel('lab')}>ZARA Lab</button>
                        <button type="button" role="menuitem" className={painelVisivel && painel === 'conversa' ? 'marcado' : ''} onClick={() => escolherPainel('conversa')}>Conversa com a ZARA</button>
                        <button type="button" role="menuitem" onClick={() => { setPainelVisivel(false); setMenuAberto(false); }}>Ocultar o painel</button>
                      </div>
                    )}
                  </div>
                </header>
                <article><span className="agenda-symbol">▣</span><div><strong>Reunião de projeto</strong><small>10:00</small></div></article>
                <article><span className="agenda-symbol plane">⌁</span><div><strong>Viagem</strong><small>15:30&nbsp; · &nbsp;Guarulhos</small></div></article>
                <article className="priority"><span className="agenda-symbol">☆</span><div><strong>Prioridade do dia</strong><small>Preparar relatório<br/>estratégico</small></div></article>
                <label className="motor-de-ia">
                  Motor de IA
                  <select value={selectedEngine} disabled={supercerebro || engines.length === 0} onChange={(e) => void changeEngine(e.target.value)}>
                    {engines.map((engine) => <option key={engine.id} value={engine.id}>{engine.name}</option>)}
                  </select>
                </label>
              </aside>
            </section>
          )}
        </section>

        {painelVisivel ? (
        <aside className="lab-window">
          {/* Os tres eram caracteres de texto — travessao, quadrado e xis — cada um
              com peso e altura propria da fonte. Desenhados na mesma caixa de
              12px e na mesma espessura de traco, eles finalmente combinam. */}
          <div className="window-controls">
            <button type="button" aria-label="Minimizar" onClick={() => window.zaraIPC?.window?.minimize?.()}>
              <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M1.5 6h9" fill="none" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/></svg>
            </button>
            <button type="button" aria-label="Maximizar" onClick={() => window.zaraIPC?.window?.maximize?.()}>
              <svg viewBox="0 0 12 12" aria-hidden="true"><rect x="1.7" y="1.7" width="8.6" height="8.6" rx="1.3" fill="none" stroke="currentColor" strokeWidth="1.1"/></svg>
            </button>
            <button type="button" aria-label="Fechar" onClick={() => window.zaraIPC?.window?.close?.()}>
              <svg viewBox="0 0 12 12" aria-hidden="true"><path d="M2.2 2.2 9.8 9.8M9.8 2.2 2.2 9.8" fill="none" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/></svg>
            </button>
          </div>
          {painel === 'lab' ? (<>
          {/* A marca d'agua e a MESMA logo da barra lateral, so que apagada em preto
              fosco pelo CSS. O arquivo separado que veio pronto era outro desenho e
              ainda por cima vinha cortado. */}
          <img className="lab-watermark" src="./zara-brand-dark.png?v=6" alt=""/>
          <div className="participants">
            <div><span className="foto-claude"><img src="./avatar-claude.png?v=6" alt="Claude"/></span><small>Claude</small></div>
            <div><img src="./avatar-openai.png?v=6" alt="OpenAI"/><small>OpenAI</small></div>
            <div><span className="avatar-marca zara" role="img" aria-label="ZARA"/><small>ZARA</small></div>
          </div>
          <div className="lab-messages">
            {miniLabMessages.length === 0 ? (
              <article className="gray"><p>{miniLabOnline ? 'O laboratório aguarda mensagens reais.' : 'ZARA Lab indisponível.'}</p></article>
            ) : miniLabMessages.map((message) => (
              <article key={message.id} className={tomDoAutor(message.author)}>
                <strong>{message.author === 'alex' ? 'Alex' : message.author.toUpperCase()}</strong>
                <p>{message.content}</p>
              </article>
            ))}
            <div ref={labFimRef}/>
          </div>
          <form className="lab-composer" onSubmit={sendMiniLab}>
            <input value={miniLabInput} onChange={(e) => setMiniLabInput(e.target.value)} placeholder="Participar da conversa..." aria-label="Mensagem para o ZARA Lab"/>
            <button type="submit" disabled={miniLabBusy || !miniLabInput.trim()} aria-label="Enviar">
              {miniLabBusy ? <LoaderCircle className="spin" size={15}/> : <IconeAviao/>}
            </button>
          </form>
          <button type="button" className={`hermes ${supercerebro ? 'ativo' : ''}`} onClick={() => void toggleSuper()}>
            {supercerebro ? 'Hermes conectado' : 'Conectar Hermes'}
          </button>
          </>) : (
            <div className="painel-conversa">
              <header><strong>Conversa com a ZARA</strong>
                <button type="button" disabled={clearingHistory || busy || voiceOn || !historyReady} onClick={() => void clearConversationHistory()} aria-label="Limpar conversa">limpar</button>
              </header>
              <div className="painel-conversa-lista" ref={logRef}>
                {messages.length === 0 ? (
                  <p className="vazio">{historyReady ? 'Ainda não conversamos hoje.' : 'Carregando a conversa...'}</p>
                ) : messages.map((message, index) => (
                  <article key={message.id || `${message.timestamp}-${index}`} className={message.role}>
                    <strong>{message.role === 'assistant' ? 'ZARA' : message.role === 'system' ? 'Sistema' : 'Você'}</strong>
                    <p>{message.content}</p>
                    <time>{horaCurta(message.timestamp)}</time>
                  </article>
                ))}
              </div>
            </div>
          )}
        </aside>
        ) : (
          <button type="button" className="painel-oculto" onClick={() => setPainelVisivel(true)} aria-label="Mostrar o painel">‹</button>
        )}
      </section>

      <div className="zara-toasts">{toasts.map((t) => <div key={t.id} className={`zara-toast ${t.kind || 'ok'}`}>{t.text}</div>)}</div>
      <PainelConfiguracoes
        aberto={configAberta}
        onFechar={() => setConfigAberta(false)}
        aparencia={aparencia}
        onMudar={setAparencia}
        onDesfazer={desfazer}
        onRefazer={refazer}
        temPassado={temPassado}
        temFuturo={temFuturo}
      />
      {galaxyOpen && <MemoryGalaxyModal onClose={() => setGalaxyOpen(false)}/>}
    </main>
  );
};

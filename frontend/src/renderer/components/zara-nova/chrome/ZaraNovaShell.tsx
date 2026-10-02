/** Shell da interface da TROPA DEV. — rail lateral + header global + page-head + toast.
 *  Visual segue o molde (zara-ui-lab): classes e estrutura idênticas,
 *  cores só por variáveis CSS (contrato da frente TEMA). */

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { Clock3, House, MessageCircle, Mic, Users, Settings } from 'lucide-react';
import type { AvatarInfo, NavKey } from '../types';
import tropaLogoNova from '../../../assets/tropa-logo-nova.png';

/* ------------------------------------------------------------------ */
/* Toast: contexto exposto para as telas mostrarem avisos curtos.      */
/* ------------------------------------------------------------------ */

const ToastContext = createContext<(mensagem: string) => void>(() => {});

/** Hook para qualquer tela dentro do shell exibir um aviso curto. */
export function useToast(): (mensagem: string) => void {
  return useContext(ToastContext);
}

/* ------------------------------------------------------------------ */
/* Navegação                                                            */
/* ------------------------------------------------------------------ */

const NAV: Array<{ key: NavKey; rotulo: string; Icon: typeof House }> = [
  { key: 'inicio', rotulo: 'Painel de confiança', Icon: House },
  { key: 'conversa', rotulo: 'Conversa', Icon: MessageCircle },
  { key: 'voz', rotulo: 'Falar por voz', Icon: Mic },
  { key: 'atividade', rotulo: 'Enquanto você estava fora', Icon: Clock3 },
  { key: 'lab', rotulo: 'Equipe & escritório', Icon: Users },
];

const CABECALHO: Record<NavKey, { eyebrow: string; titulo: string }> = {
  inicio: { eyebrow: 'SEU TEMPO, DE VOLTA PARA VOCÊ', titulo: 'Início' },
  conversa: { eyebrow: 'SEU PILOTO PENSA. A TROPA DEV. FAZ.', titulo: 'Conversa' },
  voz: { eyebrow: 'A SUA VOZ É O COMANDO', titulo: 'Voz' },
  atividade: { eyebrow: 'O TRABALHO CONTINUA', titulo: 'Enquanto você estava fora' },
  equipe: { eyebrow: 'CADA AVATAR, UMA ESPECIALIDADE', titulo: 'Minha equipe' },
  lab: { eyebrow: 'A SUA EQUIPE, EM UM SÓ LUGAR', titulo: 'Escritório' },
  configuracoes: { eyebrow: 'DO SEU JEITO', titulo: 'Configurações' },
};

/** Saudação honesta pelo horário real (America/Bahia). */
function saudacao(): string {
  const hora = Number(
    new Date().toLocaleTimeString('pt-BR', { timeZone: 'America/Bahia', hour: '2-digit', hour12: false }),
  );
  if (hora >= 5 && hora < 12) return 'Bom dia, Alex.';
  if (hora >= 12 && hora < 18) return 'Boa tarde, Alex.';
  return 'Boa noite, Alex.';
}

function Relogio() {
  const [agora, setAgora] = useState(() => new Date());
  useEffect(() => {
    const id = window.setInterval(() => setAgora(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);
  return (
    <div className="clock" aria-label="Hora atual">
      <strong>
        {agora.toLocaleTimeString('pt-BR', { timeZone: 'America/Bahia', hour: '2-digit', minute: '2-digit' })}
      </strong>
      <span>
        {agora.toLocaleDateString('pt-BR', { timeZone: 'America/Bahia', day: 'numeric', month: 'short' })}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Shell                                                                */
/* ------------------------------------------------------------------ */

export interface ZaraNovaShellProps {
  active: NavKey;
  onNavigate: (key: NavKey) => void;
  /** Ações à direita do page-head (ex.: botão "Falar com a TROPA DEV."). */
  pageActions?: ReactNode;
  children: ReactNode;
  avatar?: AvatarInfo;
  providerName?: string;
}

export function ZaraNovaShell({ active, onNavigate, pageActions, children, avatar, providerName }: ZaraNovaShellProps) {
  const [toast, setToast] = useState<string | null>(null);
  const [tituloInicio] = useState(saudacao);

  const mostrarToast = useCallback((mensagem: string) => {
    setToast(mensagem);
    window.setTimeout(() => {
      setToast((atual) => (atual === mensagem ? null : atual));
    }, 3500);
  }, []);

  const { eyebrow, titulo } = CABECALHO[active];
  const tituloVisivel = active === 'inicio' ? tituloInicio : active === 'lab' && providerName === 'OpenAI' ? 'Seu espaço de trabalho' : titulo;

  return (
    <ToastContext.Provider value={mostrarToast}>
      <div className="app-shell">
        <aside className="app-rail">
          <button className="brand" onClick={() => onNavigate('inicio')} aria-label="Ir para o Início">
            <img className="brand-symbol" src={tropaLogoNova} alt="" width={48} height={48} />
            <span className="brand-wordmark"><b className="brand-tropa">TROPA</b> <b className="brand-dev">dev.</b></span>
          </button>

          <nav className="main-nav" aria-label="Navegação principal">
            {NAV.map(({ key, rotulo, Icon }) => (
              <button
                key={key}
                type="button"
                className={`nav-item${active === key || (key === 'lab' && active === 'equipe') ? ' active' : ''}`}
                aria-current={active === key || (key === 'lab' && active === 'equipe') ? 'page' : undefined}
                onClick={() => onNavigate(key)}
              >
                {key === 'conversa' && avatar?.imagemUrl ? <img className="nav-avatar" src={avatar.imagemUrl} alt="" /> : <Icon size={20} strokeWidth={2} aria-hidden="true" />}
                <span>{key === 'conversa' && avatar ? avatar.nome : key === 'lab' && providerName === 'OpenAI' ? 'Equipe' : rotulo}</span>
              </button>
            ))}
          </nav>

          <div className="rail-note">
            <span className="rail-line" aria-hidden="true" />
            <span>
              Seu comando.
              <br />
              Sua equipe.
            </span>
          </div>

          <div className="user-profile">
            <span className="user-letter" aria-hidden="true">
              A
            </span>
            <div>
              <strong>Alex</strong>
              <small>Administrador</small>
            </div>
          </div>
          <button className="nav-item rail-settings" type="button" onClick={() => onNavigate('configuracoes')} aria-current={active === 'configuracoes' ? 'page' : undefined}><Settings size={20} aria-hidden="true" /><span>Configurações</span></button>
        </aside>

        <div className="main-surface">
          <header className="global-header">
            <div className="breadcrumb">
              <span className="brand-wordmark breadcrumb-brand"><b className="brand-tropa">TROPA</b> <b className="brand-dev">dev.</b></span>
              {providerName && <span className="pilot-provider-chip"><span className="pilot-provider-dot" aria-hidden="true" />{providerName}</span>}
              <span className="breadcrumb-divider" aria-hidden="true">
                /
              </span>
              <strong>{tituloVisivel}</strong>
            </div>
            <div className="global-right">
              <Relogio />
            </div>
          </header>

          <div className="page-head">
            <div>
              <p className="eyebrow">{eyebrow}</p>
              <h1>{tituloVisivel}</h1>
            </div>
            {pageActions ? <div>{pageActions}</div> : null}
          </div>

          <div className="page-content">{children}</div>

          <div className={`toast${toast ? ' show' : ''}`} role="status" aria-live="polite">
            {toast}
          </div>
        </div>
      </div>
    </ToastContext.Provider>
  );
}

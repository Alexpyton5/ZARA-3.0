/** Shell da interface nova da ZARA — rail lateral + header global + page-head + toast.
 *  Visual segue o molde (zara-ui-lab): classes e estrutura idênticas,
 *  cores só por variáveis CSS (contrato da frente TEMA). */

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { Clock3, House, MessageCircle, Mic, Users, FlaskConical } from 'lucide-react';
import type { NavKey } from '../types';

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
  { key: 'inicio', rotulo: 'Início', Icon: House },
  { key: 'conversa', rotulo: 'Conversa', Icon: MessageCircle },
  { key: 'voz', rotulo: 'Voz', Icon: Mic },
  { key: 'atividade', rotulo: 'Atividade', Icon: Clock3 },
  { key: 'equipe', rotulo: 'Equipe', Icon: Users },
  { key: 'lab', rotulo: 'Lab', Icon: FlaskConical },
];

const CABECALHO: Record<NavKey, { eyebrow: string; titulo: string }> = {
  inicio: { eyebrow: 'SEU TEMPO, DE VOLTA PARA VOCÊ', titulo: 'Início' },
  conversa: { eyebrow: 'O MUSE PENSA. A ZARA FAZ.', titulo: 'Conversa' },
  voz: { eyebrow: 'A SUA VOZ É O COMANDO', titulo: 'Voz' },
  atividade: { eyebrow: 'O TRABALHO CONTINUA', titulo: 'Enquanto você estava fora' },
  equipe: { eyebrow: 'CADA AVATAR, UMA ESPECIALIDADE', titulo: 'Minha equipe' },
  lab: { eyebrow: 'A SUA EQUIPE, EM UM SÓ LUGAR', titulo: 'ZARA Lab' },
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
  /** Ações à direita do page-head (ex.: botão "Falar com a ZARA"). */
  pageActions?: ReactNode;
  children: ReactNode;
}

export function ZaraNovaShell({ active, onNavigate, pageActions, children }: ZaraNovaShellProps) {
  const [toast, setToast] = useState<string | null>(null);
  const [tituloInicio] = useState(saudacao);

  const mostrarToast = useCallback((mensagem: string) => {
    setToast(mensagem);
    window.setTimeout(() => {
      setToast((atual) => (atual === mensagem ? null : atual));
    }, 3500);
  }, []);

  const { eyebrow, titulo } = CABECALHO[active];
  const tituloVisivel = active === 'inicio' ? tituloInicio : titulo;

  return (
    <ToastContext.Provider value={mostrarToast}>
      <div className="app-shell">
        <aside className="app-rail">
          <button className="brand" onClick={() => onNavigate('inicio')} aria-label="Ir para o Início">
            <span className="brand-mark">ZA</span>
            <span>ZARA</span>
          </button>

          <nav className="main-nav" aria-label="Navegação principal">
            {NAV.map(({ key, rotulo, Icon }) => (
              <button
                key={key}
                type="button"
                className={`nav-item${active === key ? ' active' : ''}`}
                aria-current={active === key ? 'page' : undefined}
                onClick={() => onNavigate(key)}
              >
                <Icon size={20} strokeWidth={2} aria-hidden="true" />
                <span>{rotulo}</span>
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
        </aside>

        <div className="main-surface">
          <header className="global-header">
            <div className="breadcrumb">
              <span>ZARA</span>
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

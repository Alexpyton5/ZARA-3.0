/**
 * ThemeContext.tsx — o motor de temas da interface nova da ZARA.
 *
 * O ThemeProvider aplica o tema no <html> via `document.documentElement.dataset.theme`
 * (sem reload) e persiste a escolha em localStorage. Regra do Alex: trocar o avatar
 * ativo troca o tema do app INTEIRO, e a escolha persiste entre sessões.
 *
 * Uso:
 *   <ThemeProvider>
 *     <App />
 *   </ThemeProvider>
 *
 *   const { theme, setTheme, availableThemes } = useTheme();      // tema atual
 *   const { activeAvatar, setActiveAvatar } = useAvatar();        // avatar ativo
 *   // Contrato FIAÇÃO (App.tsx): useAvatar() também devolve
 *   // { avatar, escolherAvatar, limparAvatar }.
 *
 * Prova de aceite (para a FRENTE PORTÃO conferir no PC):
 *   1. Alternar o tema via setTheme muda o visual na hora, sem reload.
 *   2. setActiveAvatar('levi') => visual dots; setActiveAvatar('zoe') => visual claro.
 *   3. Recarregar o app mantém o último tema/avatar escolhidos (localStorage).
 *   4. Contrato FIAÇÃO (substituto TODO(TEMA) do App.tsx): este módulo exporta
 *      os MESMOS nomes — <ThemeProvider avatar={...}> aceita a prop `avatar`,
 *      e useAvatar() devolve { avatar, escolherAvatar, limparAvatar } além de
 *      { activeAvatar, setActiveAvatar }. O PORTÃO pode apagar o bloco
 *      substituto e importar daqui; a única adaptação é que o estado do avatar
 *      passa a viver no provider (a prop `avatar` espelha o estado do App).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import type { ReactElement, ReactNode } from 'react';
import type { AvatarId, AvatarInfo, ThemeId } from '../types';
import {
  AVAILABLE_THEMES,
  DEFAULT_AVATAR_ID,
  avatarInfoPara,
  isKnownTheme,
  themeForAvatar,
} from '../../../lib/avatarTheme';
import type { ThemeOption } from '../../../lib/avatarTheme';

/** Chave do localStorage onde o tema escolhido é persistido. */
export const THEME_STORAGE_KEY = 'zara-avatar-theme';

/** Chave do localStorage onde o avatar ativo é persistido. */
export const AVATAR_STORAGE_KEY = 'zara-active-avatar';

export interface ThemeState {
  /** Tema aplicado agora no <html>. */
  theme: ThemeId;
  /** Troca o tema na hora, sem reload, e persiste a escolha. */
  setTheme: (theme: ThemeId) => void;
  /** Os 3 temas disponíveis, com rótulos em pt-BR. */
  availableThemes: ThemeOption[];
}

export interface AvatarState {
  /** Id do avatar ativo (a presença com quem o usuário conversa). Nunca vazio. */
  activeAvatar: AvatarId;
  /**
   * Troca o avatar ativo. Pela regra do Alex, isso troca o tema do app
   * INTEIRO para o tema do avatar, sem reload, e persiste as duas escolhas.
   */
  setActiveAvatar: (avatarId: AvatarId) => void;
  /**
   * Contrato da FRENTE FIAÇÃO (substituto TODO(TEMA) do App.tsx).
   * `avatar` é null quando nenhum avatar foi escolhido (portão de entrada);
   * no modo não-controlado, deriva do avatar ativo e nunca é null.
   */
  avatar: AvatarInfo | null;
  /** Mesmo que setActiveAvatar(a.id), recebendo o AvatarInfo inteiro. */
  escolherAvatar: (avatar: AvatarInfo) => void;
  /** Volta ao estado "nenhum avatar" (o App mostra a Entrada). O tema atual é mantido. */
  limparAvatar: () => void;
}

type ThemeContextValue = ThemeState & AvatarState;

const ThemeContext = createContext<ThemeContextValue | null>(null);

function readStored(key: string): string | null {
  try {
    if (typeof localStorage === 'undefined') return null;
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function store(key: string, value: string): void {
  try {
    if (typeof localStorage === 'undefined') return;
    localStorage.setItem(key, value);
  } catch {
    /* Armazenamento indisponível: o app segue funcionando nesta sessão. */
  }
}

function applyThemeToDocument(theme: ThemeId): void {
  if (typeof document === 'undefined') return;
  document.documentElement.dataset.theme = theme;
}

// Aplica antes da pintura no navegador; no servidor, vira um efeito comum.
const useIsomorphicLayoutEffect = typeof window !== 'undefined' ? useLayoutEffect : useEffect;

export interface ThemeProviderProps {
  children: ReactNode;
  /** Avatar inicial quando não há escolha salva. Padrão: 'zoe'. */
  initialAvatar?: AvatarId;
  /**
   * Modo controlado — contrato da FRENTE FIAÇÃO (App.tsx: <ThemeProvider avatar={avatar}>).
   * Quando fornecida, o avatar do provider espelha esta prop (inclusive null,
   * que mantém o portão de entrada). Sem a prop, o provider gerencia sozinho.
   */
  avatar?: AvatarInfo | null;
}

export function ThemeProvider({
  children,
  initialAvatar = DEFAULT_AVATAR_ID,
  avatar: avatarProp,
}: ThemeProviderProps): ReactElement {
  const controlado = avatarProp !== undefined;

  const [avatarInfo, setAvatarInfoState] = useState<AvatarInfo | null>(() => {
    if (controlado) return avatarProp;
    const saved = readStored(AVATAR_STORAGE_KEY);
    return avatarInfoPara(saved !== null && saved.length > 0 ? saved : initialAvatar);
  });

  const [theme, setThemeState] = useState<ThemeId>(() => {
    const savedTheme = readStored(THEME_STORAGE_KEY);
    if (isKnownTheme(savedTheme)) return savedTheme;
    if (controlado && avatarProp) return themeForAvatar(avatarProp.id);
    const savedAvatar = readStored(AVATAR_STORAGE_KEY);
    return themeForAvatar(
      savedAvatar !== null && savedAvatar.length > 0 ? savedAvatar : initialAvatar,
    );
  });

  // Evita reaplicar o tema quando a prop controlada re-renderiza com o mesmo id.
  const ultimoIdAplicado = useRef<string | null>(null);

  const aplicarTemaDoAvatar = useCallback((id: AvatarId) => {
    const nextTheme = themeForAvatar(id);
    ultimoIdAplicado.current = id;
    setThemeState(nextTheme);
    store(AVATAR_STORAGE_KEY, id);
    store(THEME_STORAGE_KEY, nextTheme);
  }, []);

  // Modo controlado: a prop manda. Trocar o id aplica o tema na hora, sem reload.
  useEffect(() => {
    if (!controlado) return;
    setAvatarInfoState(avatarProp);
    if (avatarProp && avatarProp.id !== ultimoIdAplicado.current) {
      aplicarTemaDoAvatar(avatarProp.id);
    }
  }, [controlado, avatarProp, aplicarTemaDoAvatar]);

  useIsomorphicLayoutEffect(() => {
    applyThemeToDocument(theme);
  }, [theme]);

  const setTheme = useCallback((next: ThemeId) => {
    if (!isKnownTheme(next)) return;
    setThemeState(next);
    store(THEME_STORAGE_KEY, next);
  }, []);

  const escolherAvatar = useCallback(
    (avatar: AvatarInfo) => {
      if (!avatar || avatar.id.length === 0) return;
      setAvatarInfoState(avatar);
      aplicarTemaDoAvatar(avatar.id);
    },
    [aplicarTemaDoAvatar],
  );

  const setActiveAvatar = useCallback(
    (avatarId: AvatarId) => {
      if (avatarId.length === 0) return;
      escolherAvatar(avatarInfoPara(avatarId));
    },
    [escolherAvatar],
  );

  const limparAvatar = useCallback(() => {
    ultimoIdAplicado.current = null;
    setAvatarInfoState(null);
    try {
      if (typeof localStorage !== 'undefined') localStorage.removeItem(AVATAR_STORAGE_KEY);
    } catch {
      /* Armazenamento indisponível: o app segue funcionando nesta sessão. */
    }
  }, []);

  // Contrato TEMA: activeAvatar nunca é vazio (cai no padrão quando null).
  const activeAvatar: AvatarId = avatarInfo ? avatarInfo.id : DEFAULT_AVATAR_ID;

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme,
      setTheme,
      availableThemes: AVAILABLE_THEMES,
      activeAvatar,
      setActiveAvatar,
      avatar: avatarInfo,
      escolherAvatar,
      limparAvatar,
    }),
    [theme, setTheme, activeAvatar, setActiveAvatar, avatarInfo, escolherAvatar, limparAvatar],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

function useThemeContext(): ThemeContextValue {
  const context = useContext(ThemeContext);
  if (context === null) {
    throw new Error('useTheme/useAvatar precisam estar dentro de um <ThemeProvider>.');
  }
  return context;
}

/** Tema atual + troca manual + lista de temas (para seletores de tema). */
export function useTheme(): ThemeState {
  const { theme, setTheme, availableThemes } = useThemeContext();
  return useMemo(
    () => ({ theme, setTheme, availableThemes }),
    [theme, setTheme, availableThemes],
  );
}

/**
 * Avatar ativo + troca de avatar (trocar o avatar troca o tema do app inteiro).
 * Inclui o contrato da FRENTE FIAÇÃO: { avatar, escolherAvatar, limparAvatar }.
 */
export function useAvatar(): AvatarState {
  const { activeAvatar, setActiveAvatar, avatar, escolherAvatar, limparAvatar } =
    useThemeContext();
  return useMemo(
    () => ({ activeAvatar, setActiveAvatar, avatar, escolherAvatar, limparAvatar }),
    [activeAvatar, setActiveAvatar, avatar, escolherAvatar, limparAvatar],
  );
}

// ============================================================
// ZARA DESIGN SYSTEM — Barrel Exports
// ============================================================
// Importação única: import { Orb, Waveform, Chat, HUD } from '@/components/zara'
// Estilos: import '@/styles/tokens.css' (deve vir primeiro no app)
// ============================================================

// ===== TYPES =====
// Orb
export type { OrbProps, OrbState, OrbTheme, OrbSize } from './Orb';

// Waveform
export type { WaveformProps, WaveformMode, WaveformDirection } from './Waveform';

// Chat
export type { 
  ChatProps, 
  ChatMessage, 
  MessageRole, 
  ToolCall,
  ChatInputProps 
} from './Chat';

// HUD
export type { 
  HUDProps, 
  HUDVariant, 
  SystemMetrics, 
  ConnectionInfo, 
  VoiceInfo, 
  EngineInfo,
  ConnectionStatus,
  VoiceStatus 
} from './HUD';

// ===== COMPONENTS =====
export { Orb, default as OrbDefault } from './Orb';
export { Waveform, default as WaveformDefault } from './Waveform';
export { Chat, default as ChatDefault } from './Chat';
export { HUD, default as HUDDefault } from './HUD';

// ===== STYLES (side-effect imports) =====
// Ordem importa: tokens.css primeiro, depois componentes
import '../styles/tokens.css';
import './Orb.css';
import './Waveform.css';
import './Chat.css';
import './HUD.css';

// ===== DESIGN TOKENS (para uso em CSS-in-JS ou runtime) =====
// Estes são re-exportados como objeto para uso programático
export const designTokens = {
  // Cores primitivas
  color: {
    military: {
      50: '#f0f5ee', 100: '#dcead8', 200: '#b9d5b1', 300: '#8fc17f',
      400: '#73a662', 500: '#5f8354', 600: '#4a6642', 700: '#374931',
      800: '#262f22', 900: '#161a15', 950: '#0b0f0b',
    },
    terracotta: {
      50: '#fdf3ef', 100: '#fadfd7', 200: '#f3b9a6', 300: '#e88d6b',
      400: '#df6b43', 500: '#d9a441', 600: '#c0392b', 700: '#972d21',
      800: '#73241c', 900: '#5d1f19', 950: '#32100d',
    },
    pearl: {
      50: '#faf9f6', 100: '#f3eeea', 200: '#e6ded5', 300: '#d4c8ba',
      400: '#b8a791', 500: '#9a866d', 600: '#7d6a54', 700: '#635242',
      800: '#4f4135', 900: '#42362d', 950: '#242321',
    },
    slate: {
      50: '#f0f2ed', 100: '#e4e9e2', 200: '#c8d2c9', 300: '#a1a9a0',
      400: '#8d9a88', 500: '#6e7d6b', 600: '#566355', 700: '#444d42',
      800: '#373e34', 900: '#2f352c', 950: '#121313',
    },
    // Semânticas
    success: '#8fc17f',
    warning: '#d9b45e',
    danger: '#e0705f',
    info: '#7fb3ff',
  },

  // Espaçamento
  space: {
    0: '0', 1: '4px', 2: '8px', 3: '12px', 4: '16px', 5: '20px',
    6: '24px', 8: '32px', 10: '40px', 12: '48px', 16: '64px',
    20: '80px', 24: '96px',
  },

  // Tipografia
  font: {
    ui: '"Segoe UI Variable Text", "Segoe UI", "Helvetica Neue", Arial, sans-serif',
    display: '"Segoe UI Variable Display", "Segoe UI", "Helvetica Neue", Arial, sans-serif',
    mono: 'ui-monospace, "Cascadia Mono", "Segoe UI Mono", Consolas, monospace',
    serif: '"Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif',
    brand: '"Bodoni 72", Didot, "Times New Roman", serif',
  },

  fontSize: {
    xs: 'clamp(10px, 0.75rem, 11px)',
    sm: 'clamp(11px, 0.8125rem, 12px)',
    base: 'clamp(13px, 0.875rem, 14px)',
    lg: 'clamp(14px, 0.9375rem, 16px)',
    xl: 'clamp(16px, 1.125rem, 18px)',
    '2xl': 'clamp(20px, 1.375rem, 24px)',
    '3xl': 'clamp(28px, 1.75rem, 36px)',
    '4xl': 'clamp(36px, 2.25rem, 48px)',
  },

  fontWeight: {
    normal: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
  },

  lineHeight: {
    tight: 1.2,
    snug: 1.35,
    normal: 1.5,
    relaxed: 1.65,
    loose: 1.8,
  },

  letterSpacing: {
    tight: '-0.02em',
    normal: '0',
    wide: '0.02em',
    wider: '0.08em',
    widest: '0.16em',
    brand: '0.32em',
    mono: '0.04em',
    upper: '0.14em',
  },

  // Motion
  duration: {
    instant: '0ms',
    fast: '100ms',
    normal: '180ms',
    slow: '280ms',
    slower: '400ms',
    ambient: '6800ms',
    orbListen: '3400ms',
    orbSpeak: '720ms',
    orbThink: '4000ms',
    haloListen: '1900ms',
    haloSpeak: '580ms',
  },

  easing: {
    linear: 'linear',
    in: 'cubic-bezier(0.4, 0, 1, 1)',
    out: 'cubic-bezier(0, 0, 0.2, 1)',
    inOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
    spring: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
    orbThink: 'cubic-bezier(0.62, 0.08, 0.31, 0.92)',
    gentle: 'cubic-bezier(0.25, 0.46, 0.45, 0.94)',
  },

  // Z-index
  zIndex: {
    base: 0,
    dropdown: 100,
    sticky: 200,
    modalBackdrop: 400,
    modal: 500,
    popover: 600,
    tooltip: 700,
    toast: 800,
    max: 9999,
  },

  // Breakpoints
  breakpoint: {
    sm: '640px',
    md: '768px',
    lg: '1024px',
    xl: '1280px',
    '2xl': '1536px',
  },

  // Border radius
  borderRadius: {
    none: '0',
    sm: '4px',
    md: '8px',
    lg: '12px',
    xl: '16px',
    '2xl': '20px',
    pill: '9999px',
    full: '50%',
  },

  // Shadows
  shadow: {
    sm: '0 1px 2px rgba(0, 0, 0, 0.3)',
    md: '0 4px 12px rgba(0, 0, 0, 0.35)',
    lg: '0 16px 40px rgba(0, 0, 0, 0.4)',
    xl: '0 26px 70px rgba(0, 0, 0, 0.48)',
    inner: 'inset 0 1px 0 rgba(255, 255, 255, 0.035)',
  },

  // Opacidades
  opacity: {
    disabled: 0.36,
    muted: 0.58,
    subtle: 0.12,
    overlay: 0.68,
  },
} as const;

// ===== HELPER: Aplicar tokens via CSS custom properties =====
export function applyDesignTokens(root: HTMLElement = document.documentElement, overrides: Partial<typeof designTokens> = {}): void {
  const tokens = { ...designTokens, ...overrides };
  
  // Cores
  Object.entries(tokens.color).forEach(([key, value]) => {
    if (typeof value === 'string') {
      root.style.setProperty(`--color-${key}`, value);
    } else if (typeof value === 'object') {
      Object.entries(value).forEach(([shade, hex]) => {
        root.style.setProperty(`--color-${key}-${shade}`, hex);
      });
    }
  });

  // Espaçamento
  Object.entries(tokens.space).forEach(([key, value]) => {
    root.style.setProperty(`--space-${key}`, value);
  });

  // Tipografia
  Object.entries(tokens.font).forEach(([key, value]) => {
    root.style.setProperty(`--font-${key}`, value);
  });

  Object.entries(tokens.fontSize).forEach(([key, value]) => {
    root.style.setProperty(`--text-${key}`, value);
  });

  Object.entries(tokens.fontWeight).forEach(([key, value]) => {
    root.style.setProperty(`--font-weight-${key}`, String(value));
  });

  Object.entries(tokens.lineHeight).forEach(([key, value]) => {
    root.style.setProperty(`--leading-${key}`, String(value));
  });

  Object.entries(tokens.letterSpacing).forEach(([key, value]) => {
    root.style.setProperty(`--tracking-${key}`, value);
  });

  // Motion
  Object.entries(tokens.duration).forEach(([key, value]) => {
    root.style.setProperty(`--duration-${key}`, value);
  });

  Object.entries(tokens.easing).forEach(([key, value]) => {
    root.style.setProperty(`--ease-${key}`, value);
  });

  // Z-index
  Object.entries(tokens.zIndex).forEach(([key, value]) => {
    root.style.setProperty(`--z-${key}`, String(value));
  });

  // Border radius
  Object.entries(tokens.borderRadius).forEach(([key, value]) => {
    root.style.setProperty(`--radius-${key}`, value);
  });

  // Shadows
  Object.entries(tokens.shadow).forEach(([key, value]) => {
    root.style.setProperty(`--shadow-${key}`, value);
  });

  // Opacidades
  Object.entries(tokens.opacity).forEach(([key, value]) => {
    root.style.setProperty(`--opacity-${key}`, String(value));
  });
}

// ===== HELPER: Toggle tema =====
export function setTheme(theme: 'light' | 'dark' | 'system', root: HTMLElement = document.documentElement): void {
  if (theme === 'system') {
    const prefersLight = window.matchMedia('(prefers-color-scheme: light)').matches;
    root.dataset.theme = prefersLight ? 'light' : 'dark';
  } else {
    root.dataset.theme = theme;
  }
}

export function watchSystemTheme(root: HTMLElement = document.documentElement): () => void {
  const mediaQuery = window.matchMedia('(prefers-color-scheme: light)');
  const handler = (e: MediaQueryListEvent) => {
    if (root.dataset.theme === 'system') {
      root.dataset.theme = e.matches ? 'light' : 'dark';
    }
  };
  mediaQuery.addEventListener?.('change', handler);
  return () => mediaQuery.removeEventListener?.('change', handler);
}

// ===== VERSION =====
export const DESIGN_SYSTEM_VERSION = '1.0.0';
export const DESIGN_SYSTEM_BUILD_DATE = '2026-08-18';
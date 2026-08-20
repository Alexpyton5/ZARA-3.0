# ZARA DESIGN SYSTEM — Prototyping Specs

> **Versão:** 1.0  
> **Data:** 2026-08-18  
> **Autor:** DESIGNER_UI_UX  
> **Base:** Consolidação de `tokens.css`, `Orb.tsx`, `Waveform.tsx`, `Chat.tsx`, `HUD.tsx`

---

## 1. VISÃO GERAL

Este documento define as especificações para prototipagem da interface da ZARA. Todos os componentes usam **design tokens** centralizados em `tokens.css` — nada é hardcoded. Isso garante consistência entre temas (claro/escuro), tamanhos e variantes.

### Princípios Fundamentais

| Princípio | Descrição |
|-----------|-----------|
| **Token-first** | Cores, espaçamento, tipografia, motion → só via CSS custom properties |
| **Semântico, não decorativo** | Tokens nomeados por propósito (`--accent-primary`, não `--green-300`) |
| **Acessível por padrão** | `prefers-reduced-motion`, `focus-visible`, ARIA, contraste WCAG AA |
| **Tema como consequência** | `data-theme="light|dark"` no `:root` muda tudo — sem CSS duplicado |
| **Componente = API + CSS** | Cada componente exporta TypeScript types + CSS modular |

---

## 2. TOKENS DE DESIGN (Resumo)

### 2.1 Cores — Primitivas

```css
/* Verde militar — assinatura ZARA */
--color-military-300: #8FC17F;  /* PRIMARY ACCENT */
--color-military-500: #5F8354;  /* ACCENT MUTED */
--color-military-950: #0B0F0B;  /* BASE DARK */

/* Terracota — segundo fio */
--color-terracotta-500: #D9A441; /* WARM ACCENT */
--color-terracotta-600: #C0392B; /* SEGUNDO FIO */

/* Neutros Pearl (claro) */
--color-pearl-50: #FAF9F6;
--color-pearl-950: #242321;

/* Neutros Slate (escuro) */
--color-slate-100: #E4E9E2;
--color-slate-950: #121313;
```

### 2.2 Cores — Semânticas (usar nos componentes)

```css
/* Superfícies */
--surface-base       /* fundo principal */
--surface-raised     /* cards, modais */
--surface-panel      /* painéis laterais */
--surface-input      /* inputs, textareas */
--surface-overlay    /* backdrops, modais */

/* Bordas */
--border-subtle      /* divisores sutis */
--border-default     /* bordas padrão */
--border-focus       /* foco / accent */
--border-accent      /* destaque ativo */

/* Texto */
--text-primary       /* título, corpo principal */
--text-secondary     /* labels, metadata */
--text-muted         /* placeholders, hints */
--text-faint         /* timestamps, disabled */

/* Accent */
--accent-primary     /* cor de ação principal */
--accent-soft        /* accent com 18% opacidade */
--accent-muted       /* accent para estados sutis */
--accent-glow        /* para sombras/glow do orb */

/* Estados */
--color-success      /* #8FC17F */
--color-warning      /* #D9B45E */
--color-danger       /* #E0705F */
--color-info         /* #7FB3FF */
```

### 2.3 Espaçamento

```css
--space-1: 4px   --space-2: 8px   --space-3: 12px
--space-4: 16px  --space-5: 20px  --space-6: 24px
--space-8: 32px  --space-10: 40px --space-12: 48px
--space-16: 64px --space-20: 80px --space-24: 96px

/* Semânticos */
--space-xs: var(--space-1)
--space-sm: var(--space-2)
--space-md: var(--space-4)
--space-lg: var(--space-6)
--space-xl: var(--space-8)
--space-2xl: var(--space-12)
```

### 2.4 Tipografia

```css
/* Famílias */
--font-ui:      "Segoe UI Variable Text", system-ui, sans-serif
--font-display: "Segoe UI Variable Display", system-ui, sans-serif
--font-mono:    ui-monospace, "Cascadia Mono", Consolas, monospace
--font-serif:   "Iowan Old Style", Palatino, Georgia, serif
--font-brand:   "Bodoni 72", Didot, serif

/* Tamanhos (clamp responsivo) */
--text-xs: 10-11px    --text-sm: 11-12px   --text-base: 13-14px
--text-lg: 14-16px    --text-xl: 16-18px   --text-2xl: 20-24px
--text-3xl: 28-36px   --text-4xl: 36-48px

/* Semânticos */
--font-size-caption:    var(--text-xs)
--font-size-body:       var(--text-base)
--font-size-body-lg:    var(--text-lg)
--font-size-heading:    var(--text-xl)
--font-size-title:      var(--text-2xl)
--font-size-display:    var(--text-3xl)
--font-size-brand:      clamp(24px, 2vw, 32px)

/* Line height */
--leading-tight: 1.2    --leading-snug: 1.35    --leading-normal: 1.5
--leading-relaxed: 1.65 --leading-loose: 1.8

/* Tracking */
--tracking-tight: -0.02em   --tracking-normal: 0
--tracking-wide: 0.02em     --tracking-wider: 0.08em
--tracking-widest: 0.16em   --tracking-brand: 0.32em
--tracking-upper: 0.14em    --tracking-mono: 0.04em
```

### 2.5 Motion

```css
/* Durações */
--duration-instant: 0ms
--duration-fast: 100ms
--duration-normal: 180ms
--duration-slow: 280ms
--duration-slower: 400ms

/* Orb específico */
--duration-ambient: 6800ms      /* idle cycle */
--duration-orb-listen: 3400ms   /* rotação listening */
--duration-orb-speak: 720ms     /* pulso speaking */
--duration-orb-think: 4000ms    /* ciclo thinking */
--duration-halo-listen: 1900ms
--duration-halo-speak: 580ms

/* Easings */
--ease-linear: linear
--ease-in: cubic-bezier(0.4, 0, 1, 1)
--ease-out: cubic-bezier(0, 0, 0.2, 1)
--ease-in-out: cubic-bezier(0.4, 0, 0.2, 1)
--ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1)
--ease-orb-think: cubic-bezier(0.62, 0.08, 0.31, 0.92)
--ease-gentle: cubic-bezier(0.25, 0.46, 0.45, 0.94)

/* Orb physics */
--orb-energy-response-rise: 8.4
--orb-energy-response-fall: 4.6
--orb-vibration-speed-speak: 2.04
--orb-vibration-speed-listen: 1.12
--orb-vibration-speed-think: 0.58
--orb-vibration-speed-idle: 0.32
--orb-vibration-speed-muted: 0.08
```

### 2.6 Z-Index

```css
--z-base: 0
--z-dropdown: 100
--z-sticky: 200
--z-modal-backdrop: 400
--z-modal: 500
--z-popover: 600
--z-tooltip: 700
--z-toast: 800
--z-max: 9999
```

### 2.7 Breakpoints (referência JS)

```css
--bp-sm: 640px
--bp-md: 768px
--bp-lg: 1024px
--bp-xl: 1280px
--bp-2xl: 1536px
```

---

## 3. COMPONENTES — ESPECIFICAÇÕES

### 3.1 Orb (`Orb.tsx` + `Orb.css`)

**Propósito:** Identidade visual central da ZARA — estado de voz visualizado.

#### Props

```typescript
interface OrbProps {
  state: 'STANDBY' | 'IDLE' | 'LISTENING' | 'THINKING' 
       | 'PROCESSING' | 'SPEAKING' | 'SLEEPING' | 'MUTED';
  level?: number;           // 0-1 audio level
  theme?: 'light' | 'dark'; // auto-detect se omitido
  size?: 'sm' | 'md' | 'lg' | 'xl';
  showStateLabel?: boolean;
  onCycleComplete?: () => void;
  className?: string;
  style?: React.CSSProperties;
}
```

#### Tamanhos

| Size | Min | Max | Uso |
|------|-----|-----|-----|
| `sm` | 160px | 200px | HUD, notificações |
| `md` | 260px | 340px | Padrão (center stage) |
| `lg` | 340px | 420px | Destaque, landing |
| `xl` | 420px | 520px | Fullscreen, hero |

#### Estados Visuais (via `data-state`)

| Estado | Energia | Rotação | Vibração | Partículas |
|--------|---------|---------|----------|------------|
| `STANDBY` | 0.045 | 0.052 | 0.32 | Idle |
| `IDLE` | 0.045 | 0.052 | 0.32 | Idle |
| `LISTENING` | 0.10-0.58* | 0.064-0.082* | 0.64-1.12* | Ativas |
| `SPEAKING` | 0.16-1.0* | 0.075-0.11* | 0.86-2.04* | Intensas |
| `THINKING` | 0.25 | 0.07 | 0.58 | Moderadas |
| `PROCESSING` | 0.25 | 0.07 | 0.58 | Moderadas |
| `MUTED` | 0.012 | 0.026 | 0.08 | Mínimas |
| `SLEEPING` | 0.012 | 0.026 | 0.08 | Mínimas |

*Reativo ao `level` (áudio)

#### CSS Custom Properties (para override)

```css
.orb {
  --orb-primary:   /* cor filamentos internos */
  --orb-secondary: /* cor filamentos externos */
  --orb-glow:      /* cor glow/sombra */
  --orb-particle:  /* cor partículas */
}
```

#### Acessibilidade

- `role="img"` + `aria-label="ZARA {estado}"`
- Canvas `aria-hidden="true"`
- `prefers-reduced-motion`: para animações, mantém frame estático
- `focus-visible` no container

---

### 3.2 Waveform (`Waveform.tsx` + `Waveform.css`)

**Propósito:** Visualização de áudio em tempo real (microfone/TTS).

#### Props

```typescript
interface WaveformProps {
  level: number | number[];     // 0-1 ou array de bandas
  mode?: 'bars' | 'wave' | 'ring';
  direction?: 'up' | 'down' | 'center' | 'mirror';
  barCount?: number;            // default 32
  accentColor?: string;         // token se omitido
  trackColor?: string;          // token se omitido
  height?: number | string;     // default 60px
  width?: number | string;      // default 100%
  smoothing?: number;           // 0-1, default 0.85
  showGrid?: boolean;           // default false
  live?: boolean;               // anima sintético
  liveSpeed?: number;           // ms/frame, default 50
  onThreshold?: (exceeded: boolean) => void;
  threshold?: number;           // 0-1, default 0.7
}
```

#### Modos

| Modo | Descrição | Uso |
|------|-----------|-----|
| `bars` | Barras verticais equalizador | Padrão, command bar |
| `wave` | Linha contínua osciloscópio | Detalhado, full HUD |
| `ring` | Anel radial | Compacto, orb companion |

#### Direções (apenas `bars`)

| Direção | Visual |
|---------|--------|
| `up` | Barras crescem para cima (padrão) |
| `down` | Barras crescem para baixo |
| `center` | Crescem do centro |
| `mirror` | Espelhado vintage |

#### Variantes CSS

```css
.waveform--compact   { height: 24px; }
.waveform--large     { height: 120px; }
.waveform--command-bar { height: 36px; max-width: 200px; }
```

#### Estados

- `.waveform--peak` — level > threshold (glow + pulse)
- `.waveform--muted` — opacity 0.4, grayscale
- `.waveform--loading` — shimmer skeleton

---

### 3.3 Chat (`Chat.tsx` + `Chat.css`)

**Propósito:** Interface de conversação completa.

#### Props

```typescript
interface ChatProps {
  messages: ChatMessage[];
  onSend: (content: string) => void;
  onRegenerate?: () => void;
  onCopy?: (messageId: string, content: string) => void;
  placeholder?: string;
  disabled?: boolean;
  showTimestamps?: boolean;
  groupConsecutive?: boolean;   // default true
  maxMessages?: number;         // default 100
  autoScroll?: boolean;         // default true
  maxHeight?: number | string;  // default 60vh
  renderMessage?: (msg, idx) => ReactNode;
  renderInput?: (props) => ReactNode;
}
```

#### Message Structure

```typescript
interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system' | 'tool';
  content: string;              // suporta markdown ```code```
  timestamp: number;
  metadata?: {
    model?: string;
    tokens?: number;
    duration?: number;
    error?: boolean;
    toolCalls?: ToolCall[];
  };
}
```

#### Estilos por Role

| Role | Fonte | Cor | Background | Border Radius |
|------|-------|-----|------------|---------------|
| `user` | Serif (`--font-serif`) | `--text-primary` | `--accent-soft` | Bottom-right: 4px |
| `assistant` | UI (`--font-ui`) | `--text-secondary` | Transparente | Padrão |
| `system` | Mono (`--font-mono`) | `--text-muted` | `--surface-panel` | Input radius |
| `tool` | Mono | `--text-secondary` | Transparente | Padrão |

#### Features

- **Code blocks**: Syntax highlighting básico, botão copy
- **Streaming**: Cursor piscando (`▊`), indicador "ZARA está pensando..."
- **Tool calls**: `<details>` expansível com args/result
- **Virtualização**: Renderiza últimas `maxMessages`
- **Auto-scroll**: Com botão "novas mensagens" se user scrollou
- **Regenerate**: Botão na última resposta do assistant

#### Acessibilidade

- `role="log"` + `aria-live="polite"` na área de mensagens
- `aria-label` em cada mensagem
- Focus management no input
- `prefers-reduced-motion`: desabilita animações de entrada/cursor

---

### 3.4 HUD (`HUD.tsx` + `HUD.css`)

**Propósito:** Painel de métricas, conexões, voz, engine.

#### Props

```typescript
interface HUDProps {
  variant?: 'compact' | 'full' | 'minimal' | 'sidebar';
  metrics?: SystemMetrics;
  metricsHistory?: SystemMetrics[];
  connections?: ConnectionInfo[];
  voice?: VoiceInfo;
  engine?: EngineInfo;
  engines?: EngineInfo[];
  onEngineChange?: (id) => void;
  onVoiceToggle?: () => void;
  onMuteToggle?: () => void;
  onSupercerebroToggle?: () => void;
  supercerebroActive?: boolean;
}
```

#### Variantes

| Variante | Largura | Conteúdo | Uso |
|----------|---------|----------|-----|
| `minimal` | Auto | Voice badge + CPU + conexão ativa | Status bar |
| `compact` | 200px+ | Voice + 2 métricas + conexões | Sidebar/header |
| `sidebar` | 280px max | Todas seções colapsáveis | Painel lateral |
| `full` | 320-640px | Grid 2-col, painéis expansíveis | Modal, página dedicada |

#### Métricas (Sparkline)

```typescript
interface SystemMetrics {
  cpu: number;        // 0-100
  memory: number;     // 0-100
  network: number;    // 0-100
  storage: number;    // 0-100
  timestamp: number;
}
```

- Histórico renderizado como `<canvas>` sparkline
- Thresholds: Warning 70%, Danger 85% (cores mudam)
- Contador animado (500ms ease-out)

#### Voice Info

```typescript
interface VoiceInfo {
  status: 'standby' | 'idle' | 'listening' | 'speaking' 
        | 'thinking' | 'processing' | 'muted' | 'sleeping';
  level: number;        // 0-1
  wakeWordActive: boolean;
  ttsActive: boolean;
  engine?: string;      // "Gemini Live • Kore"
}
```

#### Conexões

```typescript
interface ConnectionInfo {
  id: string;
  label: string;
  status: 'connected' | 'connecting' | 'disconnected' | 'error';
  latency?: number;
  details?: string;
}
```

#### Engine Selector

- `<select>` nativo estilizado
- Mostra provider + status
- Callback `onEngineChange`

#### Supercérebro Toggle

- Switch estilizado (slider animado)
- Badge de status ao lado
- Callback `onSupercerebroToggle`

---

## 4. PROTOTIPAGEM — FLUXOS E ESTADOS

### 4.1 Fluxo de Voz Completo

```
STANDBY → (auto-start) → PROCESSING → LISTENING
                                    ↓
                          [audio level > 0] → SPEAKING
                                    ↓
                          [fim fala] → LISTENING/IDLE
                                    ↓
                          [mute toggle] → MUTED
                                    ↓
                          [sleep timeout] → SLEEPING
```

**Transições de UI:**
- Orb: animação contínua entre estados (energy damping)
- Waveform: `live=true` em LISTENING/SPEAKING
- HUD: badge pulsa em LISTENING/SPEAKING, estático nos outros
- Chat: input disabled em SPEAKING, streaming indicator em THINKING

### 4.2 Fluxo de Conexão

```
DISCONNECTED → CONNECTING → CONNECTED
                    ↓
                ERROR (retry)
```

**UI:**
- HUD: StatusBadge pulsa em CONNECTING
- Orb: STATE=STANDBY se backend offline
- Chat: placeholder muda para "Backend indisponível"

### 4.3 Troca de Tema

```javascript
// Único ponto de mutação
document.documentElement.dataset.theme = 'light' | 'dark';
// OU
document.documentElement.dataset.theme = 'system'; // segue OS
```

**Efeito:** Todos os tokens semânticos atualizam instantaneamente via CSS. Zero JS re-render.

### 4.4 Responsividade

| Breakpoint | Chat | HUD | Orb | Waveform |
|------------|------|-----|-----|----------|
| `< 640px` | Max-width 95%, input 16px | Stack vertical, full width | `md` → `sm` | `compact` |
| `640-1024` | Side-by-side | Grid 2-col | `md` | `default` |
| `> 1024` | Full layout | Grid 2-col expandido | `lg` | `large` |

---

## 5. INTEGRAÇÃO — COMO USAR

### 5.1 Importar Tokens

```css
/* No seu CSS global ou App.css */
@import './styles/tokens.css';
```

Ou no JS/TS:
```typescript
import './styles/tokens.css';
```

### 5.2 Usar Componentes

```tsx
import { Orb } from './components/zara/Orb';
import { Waveform } from './components/zara/Waveform';
import { Chat } from './components/zara/Chat';
import { HUD } from './components/zara/HUD';

// Orb
<Orb state="LISTENING" level={0.7} size="md" />

// Waveform
<Waveform level={audioLevel} mode="bars" live={isListening} />

// Chat
<Chat 
  messages={messages} 
  onSend={handleSend}
  onRegenerate={handleRegenerate}
  maxHeight="70vh"
/>

// HUD
<HUD 
  variant="sidebar"
  metrics={metrics}
  metricsHistory={history}
  connections={connections}
  voice={voice}
  engine={currentEngine}
  engines={availableEngines}
  onEngineChange={setEngine}
  onVoiceToggle={toggleVoice}
  onMuteToggle={toggleMute}
  supercerebroActive={superActive}
  onSupercerebroToggle={toggleSuper}
/>
```

### 5.3 Temas

```tsx
// App.tsx
function App() {
  const [theme, setTheme] = useState<'light'|'dark'|'system'>('system');
  
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'system') {
      root.dataset.theme = window.matchMedia('(prefers-color-scheme: light)').matches 
        ? 'light' : 'dark';
    } else {
      root.dataset.theme = theme;
    }
  }, [theme]);
  
  return <ZaraInterface />;
}
```

### 5.4 Customização de Cores (Runtime)

```typescript
// Via CSS custom properties no :root ou container
const customTheme = {
  '--accent-primary': '#FF6B35',      // laranja
  '--accent-soft': 'rgba(255,107,53,0.18)',
  '--surface-base': '#0A0A0A',
  '--font-ui': '"Inter", system-ui',
};

// Aplicar
Object.entries(customTheme).forEach(([prop, val]) => {
  document.documentElement.style.setProperty(prop, val);
});
```

---

## 6. CHECKLIST DE QUALIDADE

### Acessibilidade (WCAG 2.1 AA)

- [x] Contraste texto/fundo ≥ 4.5:1 (tokens garantem)
- [x] Contraste UI elements ≥ 3:1 (bordas, badges)
- [x] `focus-visible` em todos interativos
- [x] `prefers-reduced-motion` respeitado
- [x] ARIA labels/roles/live regions
- [x] Navegação por teclado completa
- [x] Screen reader testado (NVDA, VoiceOver)

### Performance

- [x] Canvas `contain: layout paint style`
- [x] `requestAnimationFrame` com cleanup
- [x] Virtualização em Chat (`maxMessages`)
- [x] Sparkline canvas reusado (não recriado)
- [x] Tokens CSS = zero runtime overhead
- [x] Lazy load componentes pesados (Orb canvas)

### Consistência

- [x] Todos componentes usam tokens (sem hardcode)
- [x] Tema claro/escuro funcional
- [x] Espaçamento na escala 4px
- [x] Tipografia semântica
- [x] Motion tokens unificados
- [x] Z-index scale respeitado

### Developer Experience

- [x] TypeScript types exportados
- [x] Props documentadas com JSDoc
- [x] CSS modular (sem conflitos)
- [x] Componentes controlados + uncontrolled
- [x] Render props para customização
- [x] Storybook-ready (stories não inclusas)

---

## 7. ROADMAP / PRÓXIMOS PASSOS

| Item | Prioridade | Esforço |
|------|------------|---------|
| Storybook stories para todos componentes | Alta | Médio |
| Testes visuais (Chromatic/Percy) | Alta | Médio |
| Componente `Tooltip` / `Popover` | Média | Baixo |
| Componente `Modal` / `Drawer` | Média | Baixo |
| Componente `Tabs` / `SegmentedControl` | Média | Baixo |
| Animações de transição de página (view transitions) | Baixa | Médio |
| Tokens para Figma (via Figma Tokens plugin) | Baixa | Baixo |
| Documentação interativa (MDX) | Baixa | Médio |

---

## 8. ARQUIVOS DO DESIGN SYSTEM

```
frontend/src/renderer/
├── styles/
│   ├── tokens.css              # 🎯 FONTE DE VERDADE — importar primeiro
│   ├── PROTOTYPING_SPECS.md    # Este documento
│   └── (legacy: pearl.css, aparencia.css, padroes.css, pele-instrumento.css)
└── components/zara/
    ├── Orb.tsx + Orb.css       # Identidade visual
    ├── Waveform.tsx + Waveform.css  # Audio viz
    ├── Chat.tsx + Chat.css     # Conversação
    ├── HUD.tsx + HUD.css       # Métricas/status
    └── index.ts                # Barrel export (criar)
```

---

## 9. BARREL EXPORT (`index.ts`)

```typescript
// frontend/src/renderer/components/zara/index.ts

// Types
export type { OrbProps, OrbState, OrbTheme, OrbSize } from './Orb';
export type { WaveformProps, WaveformMode, WaveformDirection } from './Waveform';
export type { 
  ChatProps, 
  ChatMessage, 
  MessageRole, 
  ToolCall,
  ChatInputProps 
} from './Chat';
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

// Components
export { Orb, default as OrbDefault } from './Orb';
export { Waveform, default as WaveformDefault } from './Waveform';
export { Chat, default as ChatDefault } from './Chat';
export { HUD, default as HUDDefault } from './HUD';

// Styles (side-effect imports)
import './Orb.css';
import './Waveform.css';
import './Chat.css';
import './HUD.css';
```

---

## 10. MIGRAÇÃO DE CÓDIGO LEGADO

### Substituições Recomendadas

| Legado | Novo | Notas |
|--------|------|-------|
| `ZaraVoiceOrb` | `Orb` | API simplificada, tokens, a11y |
| CSS `.pearl-*` | Tokens `--surface-*`, `--text-*` | Mapear 1:1 |
| CSS `.zara-shell` | Tokens + componentes | Decompor em partes |
| `VoiceOrb` inline no ControlCenter | `<Orb />` | Isolar responsabilidade |
| Audio bars custom | `<Waveform mode="bars" />` | Reutilizável |
| Conversation panel | `<Chat />` | Virtualizado, streaming |
| Metrics panel | `<HUD variant="sidebar" />` | Sparkline, thresholds |

### Mapeamento de Cores (Legado → Tokens)

```css
/* Pearl → Tokens */
--pearl-bg         → --surface-base (dark) / --surface-base (light)
--pearl-window     → --surface-overlay
--pearl-sidebar    → --surface-panel
--pearl-card       → --surface-raised
--pearl-ink        → --text-primary
--pearl-muted      → --text-secondary
--pearl-faint      → --text-muted
--pearl-line       → --border-subtle
--pearl-line-strong → --border-default
--pearl-accent     → --accent-primary
--pearl-accent-soft → --accent-soft
--pearl-green      → --color-success
--pearl-ring       → --accent-primary
--pearl-off        → --color-terracotta-500
--pearl-shadow     → --shadow-xl

/* Aparência → Tokens */
--t-fundo          → --surface-base
--t-destaque       → --accent-primary
--t-segundo        → --color-terracotta-600
--t-texto          → --text-primary
--t-fraco          → --text-muted
--t-borda          → --border-subtle

/* Pele Instrumento → Tokens */
--bg               → --surface-base
--panel            → --surface-panel
--line             → --border-subtle
--green            → --accent-primary
--text             → --text-primary
--muted            → --text-muted
--danger           → --color-danger
--warn             → --color-warning
```

---

---

**Fim do documento.**  
Para dúvidas ou contribuições, consulte o `DESIGNER_UI_UX` ou abra issue no repositório ZARA.
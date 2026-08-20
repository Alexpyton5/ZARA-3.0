# ZARA DESIGN SYSTEM — Guia de Integração

> **Versão:** 1.0  
> **Para:** Desenvolvedores integrando o design system no ZARA 3.0  
> **Pré-requisito:** React 18+, TypeScript 5+, Vite/ESBuild

---

## 1. INSTALAÇÃO RÁPIDA

### 1.1 Importar Tokens (obrigatório, primeiro)

```tsx
// main.tsx ou App.tsx — ANTES de qualquer componente
import '@/styles/tokens.css';
```

### 1.2 Importar Componentes

```tsx
// Barrel export (recomendado)
import { Orb, Waveform, Chat, HUD } from '@/components/zara';

// Ou individualmente
import { Orb } from '@/components/zara/Orb';
import { Waveform } from '@/components/zara/Waveform';
import { Chat } from '@/components/zara/Chat';
import { HUD } from '@/components/zara/HUD';
```

### 1.3 Configurar Tema

```tsx
// App.tsx
import { useEffect } from 'react';
import { setTheme, watchSystemTheme } from '@/components/zara';

function App() {
  useEffect(() => {
    // Opção 1: Tema fixo
    // setTheme('dark');
    
    // Opção 2: Segue sistema (recomendado)
    setTheme('system');
    const unwatch = watchSystemTheme();
    return unwatch;
  }, []);

  return <ZaraInterface />;
}
```

---

## 2. EXEMPLOS DE USO

### 2.1 Orb — Identidade Visual

```tsx
import { Orb, OrbState } from '@/components/zara';

function VoiceOrb({ state, level }: { state: OrbState; level: number }) {
  return (
    <Orb 
      state={state} 
      level={level} 
      size="md" 
      showStateLabel={import.meta.env.DEV}
    />
  );
}

// Estados possíveis:
// 'STANDBY' | 'IDLE' | 'LISTENING' | 'THINKING' | 'PROCESSING' | 'SPEAKING' | 'SLEEPING' | 'MUTED'
```

**Tamanhos disponíveis:** `sm` (160-200px), `md` (260-340px), `lg` (340-420px), `xl` (420-520px)

---

### 2.2 Waveform — Visualizador de Áudio

```tsx
import { Waveform } from '@/components/zara';

function MicVisualizer({ audioLevel, isListening }: { audioLevel: number; isListening: boolean }) {
  return (
    <Waveform 
      level={audioLevel}
      mode="bars"
      direction="up"
      barCount={32}
      height={60}
      live={isListening}
      smoothing={0.85}
      threshold={0.7}
      onThreshold={(exceeded) => console.log('Peak!', exceeded)}
    />
  );
}

// Modos: 'bars' | 'wave' | 'ring'
// Direções (bars): 'up' | 'down' | 'center' | 'mirror'
```

**Variantes CSS:**
```tsx
<Waveform className="waveform--compact" />      // 24px altura
<Waveform className="waveform--command-bar" />  // 36px, max-width 200px
<Waveform className="waveform--large" />        // 120px altura
```

---

### 2.3 Chat — Conversação Completa

```tsx
import { Chat, ChatMessage } from '@/components/zara';

function ConversationPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');

  const handleSend = (content: string) => {
    const userMsg: ChatMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content,
      timestamp: Date.now(),
    };
    setMessages(prev => [...prev, userMsg]);
    // Chamar API...
  };

  const handleRegenerate = () => {
    // Regenerar última resposta do assistant
  };

  return (
    <Chat
      messages={messages}
      onSend={handleSend}
      onRegenerate={handleRegenerate}
      placeholder="Como posso pensar com você hoje?"
      showTimestamps={true}
      groupConsecutive={true}
      maxMessages={100}
      maxHeight="70vh"
    />
  );
}

// Message com metadata:
const assistantMsg: ChatMessage = {
  id: crypto.randomUUID(),
  role: 'assistant',
  content: 'Resposta com **markdown** e ```typescript\ncode\n```',
  timestamp: Date.now(),
  metadata: {
    model: 'gpt-5.6-sol',
    tokens: 1247,
    duration: 2341,
    toolCalls: [
      { id: '1', name: 'web_search', args: { query: '...' }, result: '...' }
    ]
  }
};
```

**Features incluídas:**
- Streaming com cursor `▊`
- Code blocks com copy button
- Tool calls expansíveis (`<details>`)
- Auto-scroll + botão "novas mensagens"
- Virtualização (`maxMessages`)
- Regenerate última resposta

---

### 2.4 HUD — Painel de Métricas/Status

```tsx
import { HUD, SystemMetrics, ConnectionInfo, VoiceInfo, EngineInfo } from '@/components/zara';

function ZaraHUD() {
  const [metrics, setMetrics] = useState<SystemMetrics>({ cpu: 0, memory: 0, network: 0, storage: 0, timestamp: Date.now() });
  const [history, setHistory] = useState<SystemMetrics[]>([]);
  
  // Atualizar a cada 2s
  useEffect(() => {
    const interval = setInterval(async () => {
      const m = await fetchMetrics();
      setMetrics(m);
      setHistory(prev => [...prev.slice(-59), m]); // 60 pontos = 2min
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  return (
    <HUD
      variant="sidebar"  // 'compact' | 'full' | 'minimal' | 'sidebar'
      metrics={metrics}
      metricsHistory={history}
      connections={[
        { id: 'backend', label: 'Backend', status: 'connected', latency: 12 },
        { id: 'hermes', label: 'Hermes', status: 'connected', latency: 8 },
        { id: 'supercerebro', label: 'Supercérebro', status: 'disconnected' },
      ]}
      voice={{
        status: 'listening',
        level: 0.7,
        wakeWordActive: true,
        ttsActive: false,
        engine: 'Gemini Live • Kore',
      }}
      engine={currentEngine}
      engines={availableEngines}
      onEngineChange={setEngine}
      onVoiceToggle={toggleVoice}
      onMuteToggle={toggleMute}
      supercerebroActive={superActive}
      onSupercerebroToggle={toggleSuper}
    />
  );
}
```

**Variantes:**
| Variante | Uso | Largura |
|----------|-----|---------|
| `minimal` | Status bar | Auto |
| `compact` | Header/Sidebar | 200px+ |
| `sidebar` | Painel lateral | 280px max |
| `full` | Modal/Página | 320-640px |

---

## 3. PERSONALIZAÇÃO

### 3.1 Override de Cores (Runtime)

```tsx
// Em qualquer componente pai ou useEffect
import { designTokens, applyDesignTokens } from '@/components/zara';

function ThemeCustomizer() {
  useEffect(() => {
    const customColors = {
      '--accent-primary': '#FF6B35',           // Laranja ZARA
      '--accent-soft': 'rgba(255,107,53,0.18)',
      '--color-success': '#FF6B35',
      '--surface-base': '#0A0A0A',
      '--font-ui': '"Inter", system-ui, sans-serif',
    };
    
    Object.entries(customColors).forEach(([prop, val]) => {
      document.documentElement.style.setProperty(prop, val);
    });
  }, []);
  
  return null;
}
```

### 3.2 Override via designTokens Helper

```tsx
import { designTokens, applyDesignTokens } from '@/components/zara';

function App() {
  useEffect(() => {
    applyDesignTokens(document.documentElement, {
      color: {
        ...designTokens.color,
        military: {
          ...designTokens.color.military,
          300: '#FF6B35', // Accent laranja
        },
      },
      font: {
        ...designTokens.font,
        ui: '"Inter", system-ui, sans-serif',
      },
    });
  }, []);
  
  return <ZaraApp />;
}
```

### 3.3 CSS Custom Properties (Recomendado)

```css
/* No seu CSS global ou :root */
:root {
  /* Cores customizadas */
  --accent-primary: #FF6B35;
  --accent-soft: rgba(255, 107, 53, 0.18);
  --surface-base: #0A0A0A;
  
  /* Fonte customizada */
  --font-ui: "Inter", system-ui, sans-serif;
  
  /* Espaçamento customizado */
  --space-4: 20px;  /* 16px → 20px */
  
  /* Border radius customizado */
  --panel-radius: 24px;
  --input-radius: 10px;
}

/* Tema claro customizado */
[data-theme="light"] {
  --accent-primary: #E85D2A;
  --surface-base: #FAFAFA;
}
```

---

## 4. MIGRAÇÃO DO CÓDIGO LEGADO

### 4.1 Substituição Direta

| Componente Legado | Novo Componente | Props Principais |
|-------------------|-----------------|------------------|
| `ZaraVoiceOrb` | `Orb` | `state`, `level`, `size` |
| Voice bars inline | `Waveform mode="bars"` | `level`, `live` |
| Conversation panel | `Chat` | `messages`, `onSend` |
| Metrics panel | `HUD variant="sidebar"` | `metrics`, `connections` |

### 4.2 Mapeamento de Classes CSS

```css
/* ANTES (Pearl) → DEPOIS (Tokens) */
.pearl-desktop       → .token-surface-base + tokens
.pearl-window        → .token-surface-overlay
.pearl-sidebar       → .token-surface-panel
.pearl-card          → .token-surface-raised
.pearl-ink           → .token-text-primary
.pearl-muted         → .token-text-secondary
.pearl-line          → .token-border-subtle
.pearl-accent        → .token-accent-primary
.pearl-green         → var(--color-success)

/* ANTES (Aparência) → DEPOIS (Tokens) */
[data-zara-aparencia='ativa'] → [data-theme="dark"] (ou light)
--t-fundo           → --surface-base
--t-destaque        → --accent-primary
--t-texto           → --text-primary
--t-borda           → --border-subtle

/* ANTES (Pele Instrumento) → DEPOIS (Tokens) */
.zara-shell         → tokens no container raiz
--bg                → --surface-base
--panel             → --surface-panel
--line              → --border-subtle
--green             → --accent-primary
--text              → --text-primary
--muted             → --text-muted
```

### 4.3 Remoção Gradual

1. **Fase 1:** Importar `tokens.css` no `main.tsx`
2. **Fase 2:** Substituir `ZaraVoiceOrb` por `Orb` no `ZaraControlCenter`
3. **Fase 3:** Substituir audio bars por `Waveform`
4. **Fase 4:** Substituir conversation panel por `Chat`
5. **Fase 5:** Substituir metrics/status por `HUD`
6. **Fase 6:** Remover CSS legados (`pearl.css`, `aparencia.css`, `padroes.css`, `pele-instrumento.css`)

---

## 5. TROUBLESHOOTING

### 5.1 Tema não aplica

```tsx
// Verifique se tokens.css é importado ANTES de tudo
import '@/styles/tokens.css';  // ← PRIMEIRO
import '@/components/zara';    // ← DEPOIS

// Verifique data-theme no :root
console.log(document.documentElement.dataset.theme); // 'light' | 'dark'
```

### 5.2 Componentes não estilizam

```tsx // Verifique se CSS modular é importado (barrel export faz isso)
import '@/components/zara'; // Importa todos .css via side-effect

// Ou individualmente:
import '@/components/zara/Orb.css';
import '@/components/zara/Waveform.css';
import '@/components/zara/Chat.css';
import '@/components/zara/HUD.css';
```

### 5.3 Canvas do Orb não renderiza

```tsx // Orb precisa de tamanho definido no pai
<div style={{ width: 300, height: 300 }}>  // ou CSS
  <Orb state="LISTENING" level={0.5} />
</div>

// Ou use size prop
<Orb state="LISTENING" level={0.5} size="md" />
```

### 5.4 Waveform não anima

```tsx // Verifique prefers-reduced-motion
// No DevTools: Rendering → Emulate CSS media → prefers-reduced-motion: reduce

// Para testar live mode:
<Waveform level={0.5} live={true} mode="bars" />
```

### 5.5 Chat não faz auto-scroll

```tsx // Verifique maxHeight no container pai
<Chat 
  maxHeight="60vh"  // ou '500px'
  autoScroll={true}
/>

// Container deve ter altura definida
<div style={{ height: '60vh', display: 'flex', flexDirection: 'column' }}>
  <Chat maxHeight="100%" />
</div>
```

### 5.6 HUD sparklines não aparecem

```tsx // metricsHistory precisa ter pelo menos 2 pontos
<HUD 
  metrics={current}
  metricsHistory={history}  // Array com 2+ itens
  variant="full"
/>

// Cada item: { cpu, memory, network, storage, timestamp }
// Histórico é mantido pelo pai (useState + setInterval)
```

---

## 6. BOAS PRÁTICAS

### 6.1 Estrutura de Arquivos Recomendada

```
src/
├── styles/
│   └── tokens.css          # ← Importar primeiro no main.tsx
├── components/
│   └── zara/
│       ├── index.ts        # Barrel export
│       ├── Orb.tsx + .css
│       ├── Waveform.tsx + .css
│       ├── Chat.tsx + .css
│       ├── HUD.tsx + .css
│       └── ...
└── App.tsx
```

### 6.2 Estado de Voz — Fonte Única

```tsx // ÚNICA fonte de verdade para estado de voz
// Em context ou store global (Zustand/Redux/Jotai)
interface VoiceState {
  status: OrbState;
  level: number;
  engine: string;
}

// Componentes consomem via props
<Orb state={voice.status} level={voice.level} />
<Waveform level={voice.level} live={voice.status === 'LISTENING'} />
<HUD voice={{ status: voice.status, level: voice.level, engine: voice.engine }} />
```

### 6.3 Métricas — Atualização Controlada

```tsx // Pai gerencia histórico, filhos só recebem
function MetricsProvider() {
  const [history, setHistory] = useState<SystemMetrics[]>([]);
  
  useEffect(() => {
    const interval = setInterval(async () => {
      const m = await fetchMetrics();
      setHistory(prev => [...prev.slice(-119), m]); // 2min @ 1s
    }, 1000);
    return () => clearInterval(interval);
  }, []);
  
  return (
    <MetricsContext.Provider value={{ history }}>
      {children}
    </MetricsContext.Provider>
  );
}
```

### 6.4 Acessibilidade — Não Remova

```tsx // Estes props são obrigatórios para a11y
<Orb 
  state={state} 
  level={level}
  showStateLabel={true}  // Para screen readers
/>

<Chat
  messages={messages}
  onSend={send}
  // aria-live="polite" já no componente
/>

<HUD
  variant="sidebar"
  // role="region" + aria-label já no componente
/>
```

---

## 7. SCRIPTS ÚTEIS

### 7.1 Verificar Tokens Aplicados

```bash
# No console do navegador
console.table(
  Array.from(document.documentElement.style)
    .filter(k => k.startsWith('--'))
    .reduce((obj, k) => ({ ...obj, [k]: document.documentElement.style.getPropertyValue(k) }), {})
);
```

### 7.2 Testar Tema

```bash
# Toggle rápido no console
document.documentElement.dataset.theme = 'light'; // ou 'dark'
```

### 7.3 Build de Produção

```bash
# Vite/ESBuild já treeshakeia imports não usados
# Certifique-se de importar tokens.css no entry point
npm run build
```

---

## 8. SUPORTE

- **Documentação completa:** `PROTOTYPING_SPECS.md`
- **Tokens reference:** `tokens.css`
- **Exemplos:** Componentes em `components/zara/*.tsx`
- **Issues:** GitHub Issues do repositório ZARA

---

**Versão do Design System:** 1.0.0  
**Compatibilidade:** React 18+, TypeScript 5+, Vite 5+  
**Última atualização:** 2026-08-18
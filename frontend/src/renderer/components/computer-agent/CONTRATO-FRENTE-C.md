# Contrato do computer-agent — Frente B → Frente C (+ Frente A)

Borda colorida + selo "ZARA usando o PC…" + gatilho no chat. Missão do Alex (29/09 ~05:35).

## O que a Frente B entregou (tudo no renderer + 1 preload separado)

| Arquivo | O quê |
|---|---|
| `frontend/src/renderer/components/computer-agent/ComputerAgentOverlay.tsx` | Componente da janela de overlay: borda neon 6px (verde/roxo) + selo com o passo atual |
| `frontend/src/renderer/components/computer-agent/computer-agent-overlay.css` | Estilos do overlay (fundo transparente, brilho, animação) |
| `frontend/src/renderer/components/computer-agent/useComputerAgent.ts` | Hook: assina `computer-agent-started/step/stopped` e devolve `{ active, goal, step, stepIndex, stepTotal }` |
| `frontend/src/renderer/components/computer-agent/computerAgentBridge.ts` | Resolve a ponte do preload (aceita `window.zaraComputerAgent` **ou** `window.zaraIPC.computerAgent`) |
| `frontend/src/renderer/lib/computerAgentTrigger.ts` | Gatilho `use o computador para <goal>` (puro, com teste) |
| `frontend/src/renderer/main.tsx` | **EDITADO**: se a URL tem `?overlay=computer-agent`, renderiza só o overlay em vez do app |
| `frontend/src/renderer/components/zara-home/TextCommandInput.tsx` | **EDITADO**: gatilho no chat + botão discreto "usar PC" (ícone monitor) |
| `frontend/src/renderer/components/zara-home/brain-selector.css` | **EDITADO**: estilo do botão `.zh-command-pc` |
| `frontend/src/renderer/types/global.d.ts` | **EDITADO**: tipos `ComputerAgentPreloadAPI`, `window.zaraComputerAgent`, `window.zaraIPC.computerAgent` |
| `frontend/tests/computerAgentTrigger.test.ts` | Teste do gatilho (6 casos) |
| `frontend/src/preload-computer-agent.ts` | **PRELOAD SEPARADO** — ver seção "Preload" abaixo |

## 1. Canais IPC que o main precisa registrar (Frente C, em `setupIPC`)

| Canal (renderer → main) | Payload | Ação do main |
|---|---|---|
| `computer-agent-run` | `{ goal: string }` | `sendToPython('computer-agent-run', payload)` — o backend executa |
| `computer-agent-overlay-show` | — | mostra a janela de overlay |
| `computer-agent-overlay-hide` | — | esconde/destrói a janela de overlay |

## 2. Eventos do backend que o main precisa repassar (Frente A emite → Frente C repassa)

Verificado no código real em 29/09 (~06:00): `core/computer_agent.py` emite via
`send_event`, que escreve no stdout um JSON por linha **com o payload aninhado
em `data`** (não flat):

- `{ "type": "computer_agent_started", "data": { "goal": "..." } }`
- `{ "type": "computer_agent_stopped", "data": { "goal": "...", "success": true, "refused": false, "verified": false, "steps": 3, "error": null } }`

> **ATENÇÃO — nomes com underscore no fio:** o `switch` do `handlePythonEvent`
> tem que casar `'computer_agent_started'` / `'computer_agent_stopped'`
> (underscore). O `IPC_EVENT_TYPES` no `ipc_handlers.py` lista os mesmos nomes
> com hífen (`computer-agent-started`), **mas esse conjunto não é consultado
> em lugar nenhum** — o que chega de verdade no fio é o underscore, que é o
> que `core/computer_agent.py` emite. Coordenador: pedir p/ Frente A alinhar
> os nomes no `IPC_EVENT_TYPES` (ou ignorar — inofensivo hoje).

> **Sem evento de passo (ainda):** o backend hoje só emite started/stopped —
> não existe `computer_agent_step`. O renderer JÁ suporta o canal
> `computer-agent-step` (selo mostra o passo) caso a Frente A passe a emitir
> no futuro; por enquanto o selo exibe o goal.

Novos `case` em `handlePythonEvent` (o overlay recebe; a janela principal recebe
junto — inofensivo):

```ts
case 'computer_agent_started': {
  const data = (msg.data ?? {}) as { goal?: unknown }
  showComputerAgentOverlay()
  const payload = { goal: typeof data.goal === 'string' ? data.goal : '' }
  computerAgentOverlay?.webContents.send('computer-agent-started', payload)
  mainWindow?.webContents.send('computer-agent-started', payload)
  break
}
case 'computer_agent_stopped': {
  const data = (msg.data ?? {}) as {
    goal?: unknown
    success?: unknown
    refused?: unknown
    verified?: unknown
    steps?: unknown
    error?: unknown
  }
  const payload = {
    goal: typeof data.goal === 'string' ? data.goal : '',
    success: data.success === true,
    refused: data.refused === true,
    verified: data.verified === true,
    steps: typeof data.steps === 'number' ? data.steps : 0,
    error: typeof data.error === 'string' ? data.error : null,
  }
  computerAgentOverlay?.webContents.send('computer-agent-stopped', payload)
  mainWindow?.webContents.send('computer-agent-stopped', payload)
  hideComputerAgentOverlay()
  break
}
```

Comportamento: `computer_agent_started` → a borda neon aparece na tela toda +
selo "ZARA usando o PC…" com o goal. `computer_agent_stopped` → a borda some
(o main destrói a janela). Se o Supercérebro estiver desligado, o backend emite
`started` e logo em seguida `stopped` com `refused: true` + `error` explicando —
a borda pisca e some, e o chat mostra o motivo.

## 3. Janela de overlay — especificação (Frente C)

```ts
// Colar após createWindow() em main.ts
let computerAgentOverlay: BrowserWindow | null = null

function createComputerAgentOverlay(): BrowserWindow {
  if (computerAgentOverlay && !computerAgentOverlay.isDestroyed()) return computerAgentOverlay
  const overlay = new BrowserWindow({
    fullscreen: true,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    skipTaskbar: true,   // não aparece na barra de tarefas
    focusable: false,    // nunca rouba o foco
    resizable: false,
    movable: false,
    minimizable: false,
    maximizable: false,
    show: false,
    webPreferences: {
      preload: join(__dirname, 'preload.js'), // + seção computer-agent (ver "Preload")
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  overlay.setIgnoreMouseEvents(true) // click-through: o mouse atravessa
  overlay.setAlwaysOnTop(true, 'screen-saver')
  if (app.isPackaged) {
    // loadFile aceita query: a URL final é index.html?overlay=computer-agent
    overlay.loadFile(join(getFrontendDistPath(), 'index.html'), { query: { overlay: 'computer-agent' } })
  } else {
    overlay.loadURL('http://localhost:5173?overlay=computer-agent')
  }
  overlay.on('closed', () => {
    if (computerAgentOverlay === overlay) computerAgentOverlay = null
  })
  computerAgentOverlay = overlay
  return overlay
}

function showComputerAgentOverlay(): void {
  const overlay = createComputerAgentOverlay()
  if (!overlay.isVisible()) overlay.showInactive() // mostra sem roubar o foco
}

function hideComputerAgentOverlay(): void {
  if (computerAgentOverlay && !computerAgentOverlay.isDestroyed()) {
    computerAgentOverlay.close() // destrói; recria no próximo start
    computerAgentOverlay = null
  }
}
```

E em `setupIPC`:

```ts
ipcMain.handle('computer-agent-run', (_event, payload) => sendToPython('computer-agent-run', payload))
ipcMain.handle('computer-agent-overlay-show', () => {
  showComputerAgentOverlay()
  return { ok: true }
})
ipcMain.handle('computer-agent-overlay-hide', () => {
  hideComputerAgentOverlay()
  return { ok: true }
})
```

## 4. Preload — 2 opções (Frente C escolhe UMA)

- **Opção A (recomendada):** copiar o objeto `computerAgentAPI` de
  `frontend/src/preload-computer-agent.ts` para dentro do `zaraAPI` no
  `preload.ts`, como `computerAgent: { ... }`. O renderer enxerga como
  `window.zaraIPC.computerAgent`.
- **Opção B:** compilar `preload-computer-agent.ts` como segundo preload
  (adicionar em `tsconfig.node.json` + fundir no build). O renderer enxerga
  como `window.zaraComputerAgent`.

O renderer aceita os dois (`computerAgentBridge.ts` resolve sozinho).

## 5. Nota para a Frente A (backend) — já entregue, só registro

- ✅ Handler `'computer-agent-run'` registrado no `handler_map`
  (`core/ipc_handlers.py:4019`) — recebe `{ goal }`, roda em thread, devolve o relatório.
- ✅ Eventos `computer_agent_started` (`{"goal"}`) / `computer_agent_stopped`
  (`{"goal","success","refused","verified","steps","error"}`) emitidos via `send_event`.
- ⚠️ `IPC_EVENT_TYPES` lista os nomes com hífen, mas o fio usa underscore
  (ver seção 2) — alinhar quando der.
- Trava fail-closed intacta: sem Supercérebro, o agente recusa (`refused: true`).

## 6. Como testar (sem rebuild do instalador)

1. `npm run build` no `frontend/` (tsc + vite) — portão da Frente B, já verde.
2. Rodar o app em dev (`npm run electron:dev`) com a Opção A aplicada.
3. No chat, digitar `use o computador para abrir o bloco de notas` → a borda
   neon aparece na tela toda + selo "ZARA usando o PC…" com o objetivo.
4. Quando o backend emitir `computer_agent_stopped`, a borda some.
5. Com o Supercérebro desligado: a borda pisca e some; o chat mostra
   "Supercerebro desligado: o agente recusou mexer no computador…".

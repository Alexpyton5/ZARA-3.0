# Regras para `frontend/` — Electron + React/Vite

Aplica-se a: `frontend/src/**`, `frontend/*.config.*`, `frontend/package.json`

## Mapa mínimo

- `frontend/src/main.ts` — processo principal Electron, spawn/lifecycle do sidecar, ~28 handlers IPC
- `frontend/src/preload.ts` — ponte contextIsolated
- `frontend/src/renderer/App.tsx` — raiz da UI
- `frontend/src/renderer/components/zara/ZaraControlCenter.tsx` — controle de voz/engine/estado
- `frontend/src/renderer/components/zara/VoiceParticleSphere.tsx` — visualização de nível de voz
- `frontend/src/renderer/types/global.d.ts` — contrato da API exposta pelo preload

## Contrato de fronteira

Renderer nunca fala com o sidecar direto. Sempre
`renderer → preload → ipcMain (main.ts) → stdin/stdout do sidecar`.

Ao adicionar um canal IPC, atualizar os quatro pontos: `main.ts`, `preload.ts`,
`global.d.ts` e o consumidor no renderer. Canal declarado em três dos quatro é bug silencioso.

## Lifecycle do sidecar

Já houve **dois sidecars órfãos** observados após ciclos abrir/fechar do candidato.
Tratar como regressão aberta até prova em contrário.

Invariantes:

- uma única instância do app (gate de instância única)
- ao fechar a janela, o sidecar recebe encerramento e o processo some da lista
- watchdog de processo-pai encerra o sidecar se o Electron morrer
- readiness do backend é promessa compartilhada — nenhuma requisição IPC antes de pronto
  (esta corrida de boot já foi corrigida uma vez; não reintroduzir)

Verificação obrigatória após qualquer mexida em lifecycle: abrir e fechar o candidato
3 vezes e conferir que não sobra `zara-backend.exe` na lista de processos.

## Áudio e voz no renderer

- captura de microfone, wake e barge-in vivem na camada de interação
- a camada de interação **não fabrica conclusão de ação**; ela só transporta
- cancelar TTS tem de cortar o áudio de fato, não só mudar o estado visual

## Gates antes de empacotar

```
npm ci
npm run typecheck
npm run lint
npm run build
```

Usar **npm**. Não substituir por pnpm/yarn. Uma tentativa de pnpm já moveu dependências
para `.ignored` e quebrou o `node_modules`.

Preservar `node_modules` antes de qualquer experimento de gerenciador de pacotes.

## Proibido

- `npm install <pacote>` novo dentro de uma tarefa de correção de bug
- regenerar `package-lock.json` como efeito colateral
- sobrescrever `frontend/release/` (é a linhagem baseline)
- adicionar caminho de UI que exiba sucesso sem resposta real do backend

# ZARA — ARCHITECTURE

**Fonte:** `ARCHITECTURE_MAP.md`, código existente e auditoria de saúde registrada em `.zara-dev/reports/`.

## Fluxo principal

`Usuário → Electron/React → preload/IPC → sidecar Python → classificação/planejamento → ToolRouter/registro de ações → execução com risco → verificação → memória/auditoria → resposta para a interface`.

## Mapa de componentes

| Camada | Componentes canônicos | Responsabilidade |
|---|---|---|
| Frontend | `frontend/src/renderer/`, `App.tsx`, `components/zara/` | Home, chat, core visual, painéis e estados reais |
| Electron | `frontend/src/main.ts`, `preload.ts` | Janela nativa, spawn do sidecar, IPC e controles |
| Contrato | `frontend/src/types/global.d.ts` | Tipos e superfície IPC |
| Backend | `main.py`, `core/ipc_handlers.py` | Entrada do sidecar e despacho de mensagens |
| Voz | `core/gemini_live_voice.py`, `voice_stt.py`, `voice_tts.py` | STT/TTS, turn-taking e fallback |
| Intenção | `core/intent_classifier.py`, `pc_voice_intent.py` | Resolução de comandos para intenções |
| Ações | `core/action_registry.py`, `core/actions/` | Registro, autorização, execução e readback |
| Ferramentas | `ToolDefinition`, `ToolResult`, `ToolRouter`, verificadores | Roteamento estruturado e evidência de execução |
| Planejamento | módulos Planner existentes | Receitas multi-etapas e handoff para ferramentas |
| Modelos | `core/model_router.py` e bridge aditiva | Seleção por capacidade, custo, privacidade e saúde |
| Memória | `core/conversation_history.py`, `aprendizado.py`, `local_rag.py`, `memory/`, SQLite e Obsidian | Contexto, histórico, projeto, usuário e recuperação |
| Automação | `core/actions/scheduler.py`, lembretes e workflows | Tarefas únicas, recorrentes e condicionais |
| Visão/PC | `screen_understanding.py`, ações OS/browser | Observação e ações de computador com verificação |
| Validação | `tools/zara_validate.py`, `.zara-tests/`, `scripts/debug/nightly_regression.py` | SAFE/SANDBOX, baseline, seleção incremental e relatórios |
| Empacotamento | `build_exe.py`, `dist-sidecar/`, `frontend/release/` | Sidecar, runtime e instalador; saídas são geradas |
| Segurança | gates de capability/risco, confirmação, auditoria | Bloquear ações perigosas e não fabricar sucesso |

## Regras arquiteturais

1. O caminho de execução de ações deve passar pelo registro, gates, `ToolRouter` quando aplicável, execução e verificador.
2. O backend deve retornar o estado real; valores visuais do MASTER não podem substituir telemetria real.
3. O Supercérebro e ações de hardware LIVE permanecem desligados por padrão.
4. A memória existente deve ser auditada antes de qualquer nova abstração.
5. O Home visual deve convergir para o MASTER sem retirar IPC, dados ou controles reais.
6. O sidecar empacotado deve emitir `SYS: Interface neural pronta` antes de o renderer depender de IPC que exige backend pronto.

## Bloqueio conhecido

A integração Electron → sidecar está bloqueada por falha de extração do executável PyInstaller one-file (`vosk\libvosk.dll`/módulo PIL `.pyd`). O diagnóstico e a correção devem permanecer limitados ao empacotamento/runtime até que o handshake volte a passar.

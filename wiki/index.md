# Wiki Index — ZARA 3.0

> Content catalog of ZARA project components.
> Last updated: 2026-08-24 | Total pages: 61

## Entities
<!-- Alphabetical within section -->

### core
- [[entities/ipc_handlers]] — Despachante central IPC (voz/texto/Telegram)
- [[entities/gemini_live_voice]] — Camada de voz Gemini Live com Kore
- [[entities/action_registry]] — Registro central de 105+ ações de PC
- [[entities/pc_voice_intent]] — Intenções de voz por regex
- [[entities/aprendizado]] — Diário de experiências e aprendizado
- [[entities/telegram_ponte]] — Ponte Telegram privado (dono)
- [[entities/telegram_grupo]] — Ponte Telegram grupo (hermes/codex/claude/zara/todos)
- [[entities/ponte_codex_cli]] — Ponte com Codex CLI
- [[entities/reminder_engine]] — Motor de lembretes persistente
- [[entities/vigia_das_respostas]] — Vigia de respostas Claude/Codex
- [[entities/conversation_history]] — Histórico de conversas SQLite
- [[entities/self_knowledge]] — Auto-conhecimento da ZARA
- [[entities/cronometro]] — Medição de latência
- [[entities/model_router]] — Roteador de modelos
- [[entities/zara_orchestrator]] — Orquestrador principal

### core-actions
- [[entities/os_ops]] — Operações de SO: volume, brilho, janelas, luz noturna, Wi-Fi, Bluetooth
- [[entities/files]] — Ações de arquivos: write, copy, move, search
- [[entities/browser]] — Ações de navegador: open, search
- [[entities/media_apps]] — YouTube, Spotify, mídia
- [[entities/code]] — Execução de código
- [[entities/scheduler]] — Agendamento de tarefas
- [[entities/aprendizado_acoes]] — Ações de aprendizado
- [[entities/ponte_claude]] — Ação ponte Claude

### core-voice

### integrations-hermes
- [[entities/integration]] — Integração Hermes Agent
- [[entities/client]] — Cliente Hermes Gateway
- [[entities/bridge]] — Ponte Hermes↔ZARA
- [[entities/ensure_gateway]] — Garantia de gateway

### memory
- [[entities/memory_manager]] — Gerenciador de memória
- [[entities/project_memory]] — Memória do projeto
- [[entities/user_memory]] — Memória do usuário
- [[entities/memory_context]] — Contexto de memória
- [[entities/episodic_memory]] — Memória episódica

### frontend-src
- [[entities/main.ts]] — Entry point Electron
- [[entities/preload.ts]] — Preload script IPC
- [[entities/renderer-]] — Renderer process (UI)

### config
- [[entities/api_keys.json]] — Chaves de API (NVIDIA, Groq, Google, etc.)
- [[entities/config_manager]] — Gerenciador de configuração
- [[entities/schemas-]] — Schemas de validação

### tests
- [[entities/conftest]] — Configuração pytest
- [[entities/test_telegram_grupo]] — Testes da ponte grupo
- [[entities/test_telegram_ponte]] — Testes da ponte privada
- [[entities/test_gemini_live_voice_responsiveness]] — Testes voz Gemini
- [[entities/test_voice_conversation_fluidity]] — Testes fluidez conversa

### docs
- [[entities/ARQUITETURA-VOZ-DECISOES]] — Decisões de arquitetura de voz
- [[entities/AUDITORIA_VOZ_JARVIS]] — Auditoria voz estilo JARVIS
- [[entities/mentor-handoff-CLAUDE_CEO_BRIEFING_LIVE]] — Briefing vivo CEO/Mentor
- [[entities/technical-]] — Documentação técnica

### tools
- [[entities/build_candidate]] — Build candidato
- [[entities/executor_local]] — Executor local

## Concepts

- [[concepts/supercerebro.md]] — Supercérebro — Hermes Agent como cérebro da ZARA via gateway local
- [[concepts/wake-word.md]] — Wake word — Detecção de 'Zara/Sara' via Gemini Live ou Vosk local
- [[concepts/aec-renderer.md]] — AEC Renderer — Cancelamento de eco acústico no Electron/Chromium
- [[concepts/intent-routing.md]] — Roteamento de intenção — CONVERSA vs ACAO, dispatcher determinístico
- [[concepts/context-sync.md]] — Context Sync — Carregamento mentor_context_latest.md no boot
- [[concepts/corujao.md]] — Corujão — Execução noturna autônoma com time de bots
- [[concepts/voice-fluidity.md]] — Fluidez de voz — Janela de conversa 75s, réplica livre 20s
- [[concepts/action-verification.md]] — Verificação de ação — Nunca declarar sucesso sem pós-condição real
- [[concepts/telegram-bridge.md]] — Ponte Telegram — Privada (dono) + Grupo (equipe), prefixes hermes/codex/claude/zara/todos
- [[concepts/model-routing.md]] — Roteamento de modelos — Codex GPT-5.6-sol crítico, NVIDIA rotina, Anthropic cooldown
- [[concepts/reminder-engine.md]] — Motor de lembretes — Persistente, UTF-8, sem duplicação, notificação Telegram
- [[concepts/pc-control.md]] — Controle de PC — 105 ações reais, 63 por voz, gates de risco

## Comparisons

## Queries

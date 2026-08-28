# Arquitetura ZARA Brain: Incremental 3 Horizons

## Visão Geral

Projeto de uma única cérebro ZARA acessível por PC e celular, com percepção de tela/ambiente, memória unificada, plugin system e aprovação remota. Baseado no que já existe em `core`, `Telegram bridge`, `Hermes gateway`, `MCP` e `brain/store.py`.

---

## Horizonte 1 — Imediato (o que já funciona)

### Capacidades existentes

| Componente | Descrição | Status |
|---|---|---|
| **brain/store.py** | Store com 3 gavetas (MEMORY/KNOWLEDGE/SKILL), SQLite FTS5 + embeddings, import_vault reversible | ✅ Implementado |
| **MCP servers** | file_ops, network, processes, ui_automation — servidores STDIO registrados no client manager | ✅ Implementado |
| **IPC handlers** | `core/ipc_handlers.py` — normaliza requests voz→texto, correção de nomes, sanitização | ✅ Implementado |
| **core/actions/os_ops.py** | Ações de sistema (volume, brilho, processos, arquivos, rede) registradas no action mapping | ✅ Implementado |
| **core/pc_voice_intent.py** | Intent parsing por regex, classificar dificuldade simples/complexa | ✅ Implementado |
| **Alex Router** | Classifica speech → simple (modelo pequeno/local) vs complex (modelo grande/razão) | ✅ Implementado |
| **Telegram bridge** | Ponte de mensagens, aprovação remota via Telegram | ✅ Implementado |

### Interfaces definidas

1. **MCP Client → Server**: STDIO-based, registry em `core/actions/os_ops.py` mapeia nomes de ação → servidor MCP
2. **IPC Frontend↔Backend**: JSON over pipes, `ipc_handlers.py` faz _canonical_request_ e _correção de nomes_
3. **Voice Intent → Action**: `pc_voice_intent.py` regex → ação nomeada → `action_mapping.py` resolve implementação
4. **Brain Store**: `brain/store.py` import_vault, search_semantic, search — markdown notes + SQLite FTS5

### Riscos de segurança (Horizon 1)

- Secrets acidentais em notas (palavras-chave `api_key`, `token`, `senha` são bloqueadas no `import_vault` via _SECRET_PATTERNS)
- Acesso a processos de outros usuários (psutil pode falhar com AccessDenied)
- UI Automation sobre janelas não supervisionadas

### Provas de conceito (Horizon 1)

- ✅ `import_vault` com vault de Markdown — verificado que secrets são bloqueados
- ✅ Router classifica simples vs complexa
- ✅ MCP file_read/write testado via STDIO

---

## Horizonte 2 — Médiano (conectando os pontos)

### Nova arquitetura de "Cérebro Único"

A ideia é unificar as compartments do `brain/store.py` com o action mapping e o IPC, de modo que:

1. **Single Source of Truth**: Todas as memórias, conhecimentos e skills vivem no `brain/store.py` (single vault, single SQLite DB)
2. **Perception Layer**: Captação de tela/ambiente via UI Automation server + STT do Gemini Live
3. **Plugin System**: Extensível via MCP servers registrados dinamicamente
4. **Remote Approval**: Flow via Telegram bridge + aprovação_remota.py

### Componentes novos ou modificados

| Componente | Responsabilidade | Mudança |
|---|---|---|
| **brain/store.py** | Adicionar gaveta `PERCEPTION` para frames de tela + metadata | ➕ Nova gaveta + schema upgrade |
| **core/perception.py** | Novo módulo: captura de screen region, dump para markdown no store | ➕ Novo arquivo |
| **core/actions/os_ops.py** | Extender mapping para incluir novos action types (perception, plugins) | ➕ Novas rotas |
| **core/ipc_handlers.py** | Novos prefixos de request: `perceive:`, `plugin:`, `approve:` | ➕ Novos _canonical_request_ paths |
| **integrations/hermes/bridge.py** | Integração Hermes → ZARA brain (query/embedding via gateway) | ➕ Conexão HTTP/gateway |
| **core/model_router.py** | Roteamento baseado em tipo de request (perception vs reasoning vs action) | ➕ Atualização leve |

### Interfaces definidas (Horizon 2)

1. **Perception → Store**: `POST /perception` → injeta markdown `screen-<timestamp>.md` no compartment PERCEPTION
2. **Plugin Discovery**: MCP client lista servers disponíveis → `core/action_mapping.py` resolve qual usar
3. **Remote Approval Flow**:
   - ZARA gera proposta → Telegram bridge envia ao usuário
   - Usuário aprova/rejeita → `aprovacao_remota.py` confirma → action executada
4. **Brain Query**: `search_semantic()` + `search()` sobre todas as compartments

### Riscos de segurança (Horizon 2)

- Perception data (capturas de tela) pode conter informações sensíveis — deve ser opt-in
- Plugin sand-boxing: cada MCP server opera em processo separado, mas compartilha mesma memória do brain
- Approval fatigue: usuário pode aprovar automaticamente sem ler

### Provas de conceito (Horizon 2)

- [ ] Captura de screen region → injeta no store PERCEPTION compartment
- [ ] Plugin dinâmico: registrar um novo MCP server em tempo de execução
- [ ] Flow completo: ZARA propõe ação → Telegram approval → execução confirmada

---

## Horizonte 3 — Longo Prazo (extensibilidade total)

### Cérebro distribuído + mobile

1. **Sincronicão PC ↔ Celular**: SQLite DB replicada via SQLite Over Android (SOA) ou Async API
2. **Modelo unificado**: Mesmo roteador de decisão tanto no PC (Windows) quanto no celular (Android/iOS)
3. **Skills nativas móveis**: Touch gestures, sensores (acelerômetro, GPS), notificações push
4. **Aprovação descentralizada**: Qualquer dispositivo da casa pode aprovar ações da ZARA

### Componentes novos

| Componente | Responsabilidade |
|---|---|
| **brain/replicator.py** | Sync do SQLite brain.db entre PC e celular (conflict resolution) |
| **core/mobile_client.py** | Cliente leve para celular (Pythonite / Kivy / BeeWare) |
| **gateway/hermes** | API REST/WS unificada exposta pelo Hermes gateway |
| **core/skills_registry.py** | Registro de plugins com metadados (capabilities, permissions, risk level) |
| **ui/touch_ui.py** | Interface touch para quando Alexa/Gemini Live for front-end |

### Interfaces definidas (Horizon 3)

1. **REST API**: `GET /brain/search`, `POST /brain/import`, `POST /action/execute`
2. **WebSocket**: Streaming de percepção em tempo real
3. **Mobile Sync API**: `POST /sync` → pulls/pushes changed documents desde o store

### Riscos de segurança (Horizon 3)

- Replicação entre dispositivos — garantir consistência do SQLite FTS5
- Dispositivos móveis comprometidos — sandbox por usuário, não por app
- Aprovação entre dispositivos — necessidade de autenticação forte (biometria do dispositivo)

### Provas de conceito (Horizon 3)

- [ ] Replicação SQLite entre duas instâncias (PC + celular simulado)
- [ ] API REST mínima exposta pelo Hermes gateway
- [ ] Skill registry com validação de permissões

---

## Quadro Comparativo: O que existe vs. o que falta

| Área | Já existe | Falta / precisa | Impacto |
|---|---|---|---|
| **Store unificado** | `brain/store.py` 3 compartments | Gaveta PERCEPTION + schema upgrade | ⭐⭐⭐ Crítico |
| **Perception** | UI Automation server (mouse/keyboard) | Captura de screen + dump markdown | ⭐⭐⭐ Crítico |
| **Plugin system** | MCP servers registrados staticamente | Registro dinâmico + sandbox | ⭐⭐ Importante |
| **Remote approval** | Telegram bridge + aprovacao_remota.py | Flow completo ZARA→Telegram→confirm→action | ⭐⭐⭐ Crítico |
| **Action mapping** | `core/actions/os_ops.py` ~105 actions | Mapear novos tipos (perception, plugin) | ⭐⭐ Importante |
| **Model routing** | Alex Router (simple vs complex) | Extender para tipos de perception/action | ⭐⭐ Importante |
| **Mobile sync** | Nenhum | Replicação PC↔Celular, API mobile | ⭐⭐⭐⭐ Futuro |
| **Hermes gateway** | Ponte básica | API REST/WS unificada + skills registry | ⭐⭐⭐ Importante |

---

## Dependências entre horizontes

```
Horizon 1 → Horizon 2: precisa de store unificado + perception layer
Horizon 2 → Horizon 3: precisa de sync PC↔mobile + API gateway
```

Cada horizonte é entregue como uma versão iterativa do `brain/store.py` schema + novos módulos associados. Nenhum horizonte requer banco de dados concorrente — usa-se o mesmo SQLite com compartments adicionais.

---

## Interface públicas resumidas

### brain/store.py API (versão 2.0 planejada)

```python
# Compartimentos: MEMORY, KNOWLEDGE, SKILL, PERCEPTION
store = BrainStore()
store.initialize()

# Import notes from vault
report = store.import_vault(
    source=Path("~/zara-vault"),
    source_label="my-vault",
    compartment="memory"  # ou auto-detect
)

# Search
results = store.search_semantic(query="como abrir arquivo", limit=5)
results = store.search(query="backup", limit=10)

# Perception
store.perceive_screen(region=(x, y, w, h))  # salva markdown no compartment PERCEPTION
```

### Ação pública para Alex

| Comando voz | Backend flow |
|---|---|
| "ZARA, percebe esta tela" | → `ui_get_foreground_window` → região → `store.perceive_screen()` → markdown no PERCEPTION |
| "ZARA, lembra deste documento" | → `store.search_semantic()` → citações retornadas |
| "ZARA, faz X" | → `pc_voice_intent.py` → `action_mapping.py` → MCP server ou ação nativa |
| "ZARA, aprova isto" | → Telegram bridge → `aprovacao_remota.py` → ação confirmada |

---

## Próximos passos imediatos (próximas 40h)

1. **Schema upgrade**: adicionar gaveta PERCEPTION ao `brain/store.py` ( migration similar ao _normalize_manifest )
2. **core/perception.py**: capturar screen region via UI Automation + salvar markdown no store
3. **core/ipc_handlers.py**: adicionar prefixos `perceive:`, `plugin:`, `approve:` ao _canonical_request_
4. **Telegram flow**: testar aprovação remota completa (ZARA propõe → usuário aprova → ação executa)
5. **Documentação**: atualizar ROADMAP.md com este plano de 3 horizontes

---
*Gerado em 2026-08-23 como parte da tarefa t_6ba45353 — Pesquisa Arquitetura ZARA Brain*
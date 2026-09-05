# Arquitetura alvo

```text
ZARA UI / Desktop
        │
        ▼
Interaction Layer
        │
        ▼
ZARA Brain
├── Intent Engine
├── Context Engine
├── Planner
├── Permission Engine
├── Tool Router
├── Execution Engine
├── Verification Engine
├── Recovery Engine
└── Memory Manager
        │
        ├────────────► Model Router
        │              ├── Local
        │              ├── Free Cloud
        │              ├── Premium
        │              └── Fallback
        │
        ├────────────► Tool System
        │              ├── Files
        │              ├── Apps
        │              ├── Browser
        │              ├── OS
        │              ├── Email
        │              ├── Messaging
        │              └── Calendar
        │
        ├────────────► Second Brain
        │              ├── Obsidian Vault
        │              ├── Structured DB
        │              ├── Vector Index
        │              └── Memory Graph
        │
        └────────────► Platform Adapters
                       ├── Windows
                       ├── macOS
                       ├── Linux
                       └── Mobile
```

## Regras

- UI não acessa Node diretamente.
- Electron Main concentra capacidades privilegiadas.
- Preload expõe APIs mínimas.
- Brain não conhece detalhes da UI.
- Tools são independentes.
- Platform Adapter encapsula SO.
- Memory é externa aos LLMs.
- Model Router é desacoplado do Brain.

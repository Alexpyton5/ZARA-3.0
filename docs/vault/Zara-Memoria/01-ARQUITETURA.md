---
title: ZARA — Arquitetura
fonte: ZARA_AGENT_START_HERE.md e código atual
---

# Arquitetura

A ZARA é um desktop Windows em três camadas:

```text
React/TypeScript → Electron Main + Preload → sidecar Python
```

- Home: `frontend/src/renderer/components/zara-home/`
- Electron: `frontend/src/main.ts`
- Ponte segura: `frontend/src/preload.ts`
- Backend: `main.py` e `core/ipc_handlers.py`
- Ações: `core/actions/`
- Memória: `memory/`
- Lab V1: `core/lab_v1/`

Fluxo: mensagem → IPC → normalização → ação determinística ou modelo → gates → executor → verificação/auditoria → resposta.

A resposta de um modelo nunca é prova de que uma ação ocorreu.

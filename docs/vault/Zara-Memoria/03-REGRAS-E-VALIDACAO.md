---
title: ZARA — Regras e Validação
fonte: governança do repositório
---

# Regras

- Leia `ZARA_AGENT_START_HERE.md` antes de editar.
- Não apagar memória, bancos, histórico ou snapshots.
- Não mover o build ativo sem atualizar o ponteiro e os hashes.
- Não usar `git reset --hard` ou `git clean -fd`.
- Não bypassar ToolRouter, confirmação, risco ou auditoria.
- Não declarar capacidade só por existir um ícone, arquivo ou modelo listado.
- Não colocar segredos em logs, memória ou Markdown.
- Mudanças de texto e voz devem manter paridade.

# Validação

Backend: `python -m pytest -q`, `ruff check` e `compileall` usando o Python de `.venv`.

Frontend: `npm run typecheck`, `npm run lint` e `npm run build`.

Testes live/hardware exigem autorização explícita. `frontend/npm test` ainda é um stub e não é evidência.

# ZARA 3.0

O contexto operacional canônico está em [`ZARA_MASTER_CONTEXT.md`](./ZARA_MASTER_CONTEXT.md).

Este README é deliberadamente curto: não duplica estado, capacidades, números de testes ou decisões. Relatórios históricos e handoffs anteriores ficam em `_quarentena/docs-legacy/` e só têm valor histórico; para o estado atual, prevalecem o código, `.zara-tests/` e o contexto mestre.

Entradas principais:

- Backend: `main.py`, `core/`, `memory/`, `integrations/`.
- Frontend/Electron: `frontend/src/`.
- Testes: `tests/` e `.zara-tests/`.
- Build: `build_exe.py` e `frontend/package.json`.
- Governança: `CLAUDE.md` e `.claude/rules/`.

Saídas em `dist-sidecar/`, `frontend/dist-*` e `frontend/release/` são artefatos gerados, não source of truth.

# ZARA 3.0 — Documentação Única

**Propósito:** este é o documento resumido de orientação humana e técnica. Para qualquer mudança, leia primeiro `ZARA_AGENT_START_HERE.md` na raiz e depois este arquivo.

## Estado atual

A ZARA é um aplicativo desktop Windows formado por React/TypeScript, Electron e um sidecar Python. O caminho de execução é:

```text
Home React → preload/contextBridge → Electron Main → sidecar Python
→ interpretação → ação/modelo → gates → execução → verificação/auditoria
```

O único build operacional é o indicado por `ZARA_ACTIVE_BUILD.json`. Hoje o ponteiro indica `frontend/release-candidate-fix-9router-v2-20260917-0020`. Não editar nem mover esse diretório sem atualizar o ponteiro e validar os hashes.

## Código ativo

- `main.py`: inicialização do sidecar Python.
- `core/ipc_handlers.py`: dispatcher central de texto, voz, memória, sistema, Lab e IPC.
- `core/actions/`: ações de Windows, arquivos, navegador, terminal, web, voz e sistema.
- `core/action_registry.py`: cadastro, parâmetros e risco das ações.
- `core/tool_router.py`: validação, permissão, execução, verificação e auditoria.
- `core/model_router.py`: escolha de provider/modelo conforme política e disponibilidade.
- `memory/`: memória de usuário, projeto e episódios.
- `core/lab_v1/`: runtime multiagente V1; separado do Lab legado.
- `frontend/src/main.ts`: janela Electron, sidecar e IPC.
- `frontend/src/preload.ts`: ponte segura.
- `frontend/src/renderer/components/zara-home/`: Home ativa.
- `tests/` e `.zara-tests/`: testes e evidências.

## O que já funciona, com limitações

Texto, histórico, Home React, métricas do sistema, memória persistente, ações registradas, gates de risco/confirmação, roteamento de modelos e Lab V1 possuem implementação real. Voz, providers externos, navegador e recursos Windows dependem de configuração e teste físico.

O Planner valida e executa planos explícitos; não existe ainda decomposição autônoma geral de qualquer linguagem natural. O Lab V1 possui sessões, equipes, agentes, delegação limitada, handoffs e failover, mas não é uma fábrica autônoma irrestrita.

## Correções importantes já registradas

- Home saiu de iframe e virou React conectado ao backend.
- Histórico e navegação da Home foram conectados a dados reais.
- Respostas não devem declarar ação concluída sem executor/prova.
- Texto e voz compartilham a cadeia de intenção.
- Memória usa escrita atômica, backup, limite e redaction.
- Lab V1 separa provider, model, agent, role, team e session.
- Self-delegation é recusada para evitar chamada paga falsa.
- Build ativo usa ponteiro, identidade e hashes.
- Builds, patches, dumps e relatórios antigos foram isolados em `_quarentena/organizacao-2026-09-17/`.

## O que é legado ou não deve ser confundido com o ativo

- `core/lab_coordinator.py`: Lab legado; não é o Lab V1.
- `ActionRegistry` e `ToolRouter`: ambos ainda existem; não criar terceiro caminho.
- `.claude/`: instruções da IA, não runtime.
- `_quarentena/`: histórico recuperável, não fonte de verdade.
- `dist-*`, `build-*`, `release/`, caches e `*.tsbuildinfo`: artefatos gerados.
- Relatórios de autopilot e scripts one-shot: histórico, não estado oficial.
- Hermes e o conceito de Supercérebro foram removidos e não devem ser reintroduzidos.

## Regras de segurança

Não apagar memória, bancos, histórico ou snapshots. Não usar `git reset --hard` ou `git clean -fd`. Não mover o build ativo. Não executar hardware/live tests sem autorização explícita. Não colocar segredo em logs, documentação ou memória. Não bypassar ToolRouter, confirmação ou auditoria. Não declarar uma integração por causa de um ícone ou arquivo: exige estado real e evidência.

## Validação

Backend:

```bat
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check main.py core memory integrations tests build_exe.py
.venv\Scripts\python.exe -m compileall -q main.py core memory integrations tests build_exe.py
```

Frontend:

```bat
cd frontend
npm run typecheck
npm run lint
npm run build
```

O `npm test` ainda é um stub e não é evidência de qualidade.

## Memória e Obsidian

A memória de projeto usa SQLite e Markdown em `%LOCALAPPDATA%\ZARA3\data\project-memory\`. Se o Obsidian estiver configurado, `ProjectMemory` detecta o vault real pelo arquivo de configuração do Obsidian e espelha documentos em uma pasta `Zara-Memoria`.

A memória é seletiva: a ZARA deve recuperar apenas memórias relevantes, com limite e proveniência; não deve despejar todo o cofre em cada prompt.

O pacote inicial de documentos para o cofre está em `docs/vault/Zara-Memoria/`. Ele deve ser sincronizado pelo runtime `ProjectMemory.save_doc` ou copiado para o vault real somente depois de confirmar o caminho físico.

## Manutenção da documentação

Quando uma mudança alterar arquitetura, build, segurança, capacidade, memória ou fluxo do Lab:

1. atualizar `ZARA_AGENT_START_HERE.md` se mudar a orientação de qualquer IA;
2. atualizar este documento se mudar o estado consolidado;
3. registrar evidência em `.zara-tests/`;
4. manter relatórios detalhados em `docs/` ou quarentena, nunca criar outro “estado atual” na raiz.

**Fonte rápida:** `ZARA_AGENT_START_HERE.md` → este documento → código → `.zara-tests/` → `ZARA_ACTIVE_BUILD.json`.

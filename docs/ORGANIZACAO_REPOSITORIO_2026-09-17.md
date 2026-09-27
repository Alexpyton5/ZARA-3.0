# Organização do repositório — 17/09/2026

## Objetivo

Reduzir a bagunça acumulada por diferentes agentes de IA sem apagar dados. A organização foi feita de forma reversível: candidatos antigos foram movidos para `_quarentena/organizacao-2026-09-17/` e os movimentos foram registrados em `MOVIMENTACOES.txt`.

## Preservado como fonte operacional

- `main.py`, `core/`, `memory/`, `integrations/` e `build_exe.py`;
- `frontend/src/` e os arquivos de configuração do frontend;
- `tests/` e `.zara-tests/`;
- `.claude/`, `CLAUDE.md`, `ZARA_MASTER_CONTEXT.md`, `GATES.md` e regras de segurança;
- `ZARA_ACTIVE_BUILD.json`;
- o candidato de build apontado por `ZARA_ACTIVE_BUILD.json`:
  `frontend/release-candidate-fix-9router-v2-20260917-0020`.

## Movido para quarentena

### Artefatos gerados

Foram movidos para `_quarentena/organizacao-2026-09-17/artefatos-gerados/`:

- `dist-sidecar/`;
- `build-sidecar/`;
- `frontend/dist-frontend/`;
- `frontend/dist-electron/`;
- `frontend/dist-tests/`;
- `frontend/release/`;
- diretórios de backup/teste frontend que existissem.

Esses diretórios não são fonte de código e podem ser recriados pelo build.

### Build antigo

`frontend/ZARA CURRENT BUILD/` foi movido para `_quarentena/organizacao-2026-09-17/builds-antigos/`, pois o ponteiro operacional atual aponta para outro candidato. Ele foi preservado, não apagado.

### Histórico de organização

Os movimentos exatos estão em `_quarentena/organizacao-2026-09-17/MOVIMENTACOES.txt`.

## Documentação ativa

Os documentos ativos foram reduzidos a `ZARA_AGENT_START_HERE.md` na raiz,
`docs/ZARA_DOCUMENTACAO_UNICA.md` e o pacote `docs/vault/Zara-Memoria/`.
Relatórios detalhados anteriores foram arquivados em
`_quarentena/docs-consolidados-2026-09-17/`.

## Não removido por segurança

Não foram apagados arquivos, históricos, bancos, memórias, snapshots, código experimental ou diretórios cujo uso atual não pôde ser provado com segurança. Também não foram movidos `.venv/`, `node_modules/`, `data/` ou `lembretes/`, pois são ambientes/dados locais e uma movimentação poderia quebrar o runtime ou deslocar dados pessoais.

## Próximo passo recomendado

A próxima limpeza deve ser feita por inventário de referências: confirmar quais módulos experimentais e arquivos históricos não possuem callers, scripts, atalhos ou dependências de build. Só depois disso deve-se decidir entre arquivar definitivamente ou remover.

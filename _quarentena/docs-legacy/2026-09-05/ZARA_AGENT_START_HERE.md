# ZARA — LEIA ISTO ANTES DE AUDITAR O REPOSITÓRIO

Isto vale para qualquer agente: Claude, Codex, GPT, Manus, Verdent, ou qualquer outro.
Não é específico de um modelo.

## Existe UMA ZARA

Um source-fonte ativo. Um frontend oficial (`frontend/`, Electron + React). Um backend
oficial (`core/` + sidecar Python). Um ponteiro de build ativo: `ZARA_ACTIVE_BUILD.json`
na raiz (não existe mais "candidato" — esse conceito foi abolido em 2026-09-04).

## Antes de reler o código, leia isto (nessa ordem)

1. `.zara-tests/latest/ZARA_STATE.md` — o que está provado, o que está quebrado, o que
   mudou desde o último teste.
2. `.zara-tests/latest/ZARA_CAPABILITIES.json` — status de cada capacidade testada.
3. `.zara-tests/latest/ZARA_TEST_REPORT.md` — o relatório completo da última rodada.

## Depois, compare

`Commit:` no `ZARA_STATE.md` vs `git rev-parse HEAD` (ou `--short HEAD`).

- **Iguais, sem mudança relevante:** o estado já é a resposta. NÃO rode a suíte completa
  de novo. NÃO redescubra capacidades já verificadas. NÃO refaça auditoria geral.
- **HEAD mudou:** rode `.venv\Scripts\python.exe tools\zara_validate.py` (incremental —
  mapeia o que mudou para o teste relevante) antes de cogitar qualquer suíte completa.
  FULL SAFE (`ZARA_TESTAR_TUDO.bat`, opção 3) só quando a mudança for arquitetural,
  tocar o router/dispatcher compartilhado, for pedido explícito do Alex, ou o baseline
  mudar de forma significativa.

Teste só o subsistema afetado pela mudança atual. Gaste raciocínio em problema novo,
regressão, implementação ou decisão de arquitetura real — não em redescobrir o projeto.

## Regras que valem sempre (não específicas de tarefa)

- `.claude/rules/evidence.md` — o que cada nível de evidência prova e não prova.
- `.claude/rules/governance.md` — escopo por tarefa, anti-loop, git proibido sem autorização.
- `.claude/rules/path-rules/backend-core.md` e `frontend-electron.md` — mapa mínimo antes
  de editar `core/` ou `frontend/`.

## Se o estado estiver desatualizado (`STATE_STALE`)

Não assuma que tudo ficou inválido. Descubra qual subsistema foi tocado (frontend/CSS não
invalida o estado de voz; `core/model_router.py` não invalida o estado do frontend).

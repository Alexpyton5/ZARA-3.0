---
name: higiene-do-repositorio
description: Limpa e organiza lixo acumulado no projeto e no ambiente do Alex — linhagens de build velhas, sidecars órfãos, pastas deixadas por outros agentes, entradas duplicadas de config, arquivos temporários — sempre com inventário e backup antes de apagar, e nunca como efeito colateral de outra tarefa; use ao encontrar qualquer resíduo, ao ver disco cheio ou quando Alex pedir para organizar.
---

# Higiene do repositório e do ambiente

Alex quer isto como padrão: **achou lixo, limpa; achou bagunça, organiza** — mas sem
nunca transformar limpeza em risco de perda de trabalho.

## Regra de ouro

Limpeza é **tarefa própria**, com relatório próprio. Nunca acontece de carona numa
correção de bug, num build ou numa investigação. Se surgir lixo no meio de outra tarefa:
anotar, terminar a tarefa, limpar depois.

## Ordem obrigatória

1. **Inventariar** — listar o que é candidato, com tamanho e data. Nada de apagar às cegas.
2. **Classificar** — lixo / duvidoso / protegido. Duvidoso conta como protegido.
3. **Backup** — copiar para o scratchpad da sessão ou renomear com sufixo, antes de remover.
4. **Remover** — só o que ficou na lista "lixo".
5. **Relatar** — o que saiu, quanto liberou, o que ficou e por quê.

## Protegido — nunca apagar, mover ou "resetar"

Vem do `AGENTS.md`: `.zara-dev/`, Context Sync, Operational Context, Project Memory,
User Memory, Conversation History, lembretes, dados do LAB, snapshot do Graphify,
`config/api_keys*.json`, configuração local legítima e **todo trabalho não commitado**.

Mais: a baseline `frontend/release/`, o candidato imediatamente anterior e a tag
`zara-3.0-principal-2026-08-08`.

Git proibido sem autorização nomeada: `reset --hard`, `clean -fd`, `checkout -- .` amplo,
`restore .` amplo, stash destrutivo.

## Lixo típico neste ambiente (verificar antes, sempre)

- **Linhagens de build antigas** — `frontend/release-candidate-*/win-unpacked/` custa GB.
  Regra: manter baseline + candidato atual + candidato anterior. O resto sai.
  Vale só quando o candidato atual já passou o smoke físico.
- **Sidecar órfão** — `zara-backend.exe` sobrando na lista de processos depois de fechar o
  app. É regressão de lifecycle, não sujeira: reportar, não só matar o processo.
- **Pastas deixadas por outros agentes** — ex.: `~/.Codex/codex-disabled-skill-test/`
  (Codex, 2026-08-13, ficou vazia e foi removida). Conferir se está vazia antes.
- **Config duplicada** — `~/.Codex.json` chegou a ter o mesmo projeto duas vezes
  (`C:\...` e `C:/...`), a cópia com `PATH` contaminado por caminhos do Codex.
  Nunca editar esse arquivo com o Codex aberto: o app reescreve por cima ou corrompe.
  Fechar o app, editar, validar o JSON, abrir.
- **Artefatos gerados** — `graphify-out/`, `dist-sidecar/`, `build-sidecar/`,
  `__pycache__/`, `.pytest_cache/`. Regeneráveis; garantir que estão no `.gitignore`
  em vez de ficar apagando à mão.
- **Arquivos soltos na raiz** — `.txt`/`.json` de diagnóstico de sessões passadas
  (`ZARA-CONSERTO.txt`, `ZARA_ACTIVE_BUILD.json`). Não apagar sem perguntar: podem ser a
  única memória de um incidente.

## Nunca

- Apagar algo que você não abriu para olhar.
- Apagar `node_modules/` "para reinstalar" dentro de outra tarefa — já quebrou o ambiente
  uma vez (tentativa de pnpm).
- Trocar gerenciador de pacotes ou mexer em `PATH` global como faxina.
- Usar `--force` de reinstalação de ferramenta sem saber que ela some se a instalação
  falhar no meio (aconteceu com o `uv tool install graphifyy --force`; recuperado com
  `--no-cache`).

## Formato do relatório

```
INVENTÁRIO: <itens, tamanho, data>
REMOVIDO: <o que saiu> / LIBEROU: <espaço>
BACKUP: <onde>
MANTIDO POR SEGURANÇA: <itens duvidosos e o motivo>
```

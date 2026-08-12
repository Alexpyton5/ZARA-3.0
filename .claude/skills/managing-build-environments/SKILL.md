---
name: managing-build-environments
description: Resolve conflitos de Python, Node, PyInstaller e gerenciador de pacotes na ZARA usando caminhos explícitos do projeto, sem misturar ambiente Hermes e ZARA, sem trocar npm por pnpm e sem mutar PATH global; use ao encontrar erro de build, dependência faltando, versão errada ou node_modules quebrado.
---

# Ambientes de build da ZARA

## Quando usar

- Build do frontend (Vite/Electron) ou do sidecar (PyInstaller) falha por dependência ou versão.
- Um comando "funciona no terminal do Alex" e falha aqui, ou o contrário.
- `node_modules` sumiu, ficou inconsistente ou o lockfile não bate.
- Antes de instalar, atualizar ou trocar qualquer ferramenta.

## Fluxo obrigatório

1. **Identifique o pipeline e o lockfile primeiro**, antes de rodar qualquer install. Qual comando
   constrói o frontend, qual constrói o sidecar, e qual lockfile governa cada um.
2. **Fixe caminhos explícitos.** Registre o caminho absoluto do Python, do Node, do npm e do
   PyInstaller efetivamente usados pela ZARA. Nada de "python" solto e torcer.
3. **Confirme que o interpretador é o da ZARA**, não emprestado. Não pegar Python/uv do Hermes.
   Problema do Hermes é do Hermes. Não consertar ZARA mexendo no Hermes, nem o contrário.
4. **Preserve `node_modules` antes de qualquer experimento.** Copie ou renomeie de forma reversível
   e anote onde ficou. Só então experimente.
5. **Use o gerenciador que o lockfile indica.** Se o projeto é npm, é npm.
6. **Uma mudança de ambiente por vez**, seguida de um build de verificação. Sem lote.
7. **Se o ambiente estiver realmente quebrado, abra tarefa própria** de reparo de ambiente, com
   `TASK_ID`, escopo e rollback. Não conserte ambiente de passagem no meio de uma tarefa de feature.
8. **Revalide empacotando.** Ambiente só está bom quando produz um candidato empacotável
   (ver `validating-packaged-runtime`).

## Regras de evidência

- Registre versão e caminho absoluto de cada ferramenta usada, colhidos do comando, não de memória.
- Erro de build: cole o traceback exato com arquivo e linha antes de propor hipótese.
- Diferencie três causas: dependência ausente, versão incompatível, ferramenta errada no PATH.
  São consertos diferentes; misturar produz loop.
- "Instalei e o erro sumiu" não é diagnóstico. Diga o que estava faltando e por quê.
- Toolchain divergente entre a máquina e o pacote é causa clássica de teste físico enganoso.

## O que NUNCA fazer

- Nunca misturar ambiente Hermes e ambiente ZARA. Nem Python, nem uv, nem venv, nem cache.
- Nunca substituir npm por pnpm (ou yarn, ou bun) oportunisticamente. **Isso já aconteceu e moveu
  `node_modules` para `.ignored`**, quebrando o build inteiro. Trocar gerenciador é decisão de
  arquitetura, com aprovação do Alex e tarefa própria.
- Nunca mutar PATH global como "correção". Use caminhos explícitos na invocação.
- Nunca rodar upgrade amplo de dependências dentro de outra tarefa.
- Nunca apagar `node_modules`, venv, cache ou lockfile sem preservar cópia reversível.
- Nunca alterar versão de Node, Python ou PyInstaller sem declarar e sem plano de rollback.

# ZARA 3.0 — Novidades recentes e instruções para o Codex

**Data:** 19 de setembro de 2026  
**Projeto:** `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`  
**Objetivo:** registrar as melhorias e novidades implementadas recentemente, separar o que está conectado do que ainda é parcial ou não validado e orientar a continuidade do trabalho pelo Codex.

> Este documento é um inventário operacional de continuidade. A presença de um arquivo ou módulo não é prova suficiente de que uma capacidade está pronta. Cada item deve ser confirmado pelo código, caller, handler, executor, gate, verifier, teste e evidência de runtime correspondentes.

## 1. O que é a ZARA

A ZARA é um **assistente pessoal operacional para Windows**, inspirado em um operador tipo JARVIS. O objetivo do produto é receber comandos por texto e voz, interpretar a intenção, executar ações reais no computador com controle de risco, confirmar o resultado quando possível, manter memória persistente e coordenar tarefas de pesquisa ou trabalho por meio do ZARA Lab.

A ZARA não é apenas uma tela de chat. A parte central do produto é a cadeia:

```text
comando
→ interpretação determinística
→ autorização
→ execução real
→ verificação
→ auditoria
→ resposta honesta
```

A arquitetura possui três camadas:

```text
React/TypeScript
    ↓ window.zaraIPC / contextBridge
Electron Main + Preload
    ↓ IPC e stdin/stdout supervisionado
Sidecar Python
    ↓
intenção, ações, gates, modelos, voz, memória e auditoria
```

A proposta de valor da ZARA é composta por quatro funções principais:

1. **Assistente operacional:** executar ações reais no Windows sem afirmar que algo aconteceu apenas porque um modelo respondeu.
2. **Memória pessoal e de projeto:** guardar fatos, histórico, episódios e documentos relevantes com backup, limites e redaction.
3. **Interface multimodal:** oferecer texto, voz, áudio de saída, estado do Core, métricas do sistema e controles de janela.
4. **Orquestração controlada:** rotear modelos e coordenar trabalho no Lab sem conceder ao modelo controle direto e irrestrito do computador.

A ZARA é, portanto, um **agente operacional pessoal com supervisão, memória e execução controlada**. O Lab é uma extensão de coordenação e pesquisa; não deve ser anunciado como autonomia geral irrestrita.

## 2. Home React Titanium Emerald

### O que foi implementado

- A Home deixou de ser um iframe ou HTML estático.
- A interface passou a ser composta por componentes React reais em `frontend/src/renderer/components/zara-home/`.
- Foi criada e consolidada a identidade visual Titanium Emerald.
- A Home passou a consumir dados reais do backend para:
  - mensagens;
  - histórico;
  - estado do Core;
  - CPU, RAM e disco;
  - bateria;
  - voz;
  - controles de janela;
  - painéis de sistema;
  - memória;
  - conversas;
  - Lab.
- Foi criado um `RendererErrorBoundary` para evitar que uma falha visual derrube toda a interface.
- A navegação da Home abre painéis reais em vez de apenas trocar elementos visuais.

### Limites atuais

Alguns cards continuam sem fonte real conectada, entre eles possíveis estados de:

- Wi-Fi;
- energia;
- segurança;
- comunicações;
- projeto ativo/progresso;
- identidade real do usuário.

Quando não existe fonte real, o estado correto é mostrar indisponível ou não conectado. Não fabricar números ou status.

### Tarefa para o Codex

Validar todos os cards e painéis da Home. Para cada item, registrar:

```text
componente
→ fonte de dados
→ canal IPC
→ handler
→ estado offline
→ teste
```

Remover, desativar ou marcar claramente qualquer card que ainda não tenha fonte real.

## 3. Ponte segura Electron → React → Python

### O que foi implementado

- `contextIsolation=true`.
- `nodeIntegration=false`.
- Comunicação usando `contextBridge` em `frontend/src/preload.ts`.
- Canais para:
  - mensagens;
  - histórico;
  - memória do usuário;
  - memória de projeto;
  - ações;
  - métricas;
  - status da ZARA;
  - voz;
  - Lab legado;
  - Lab V1;
  - lembretes;
  - controles de janela;
  - telemetria de roteamento;
  - resultados de operações do Lab.

### Limite atual

Um canal existente no `preload.ts` não prova que está funcionando. Ele precisa estar ligado aos quatro pontos:

```text
preload.ts
→ main.ts
→ handler Python
→ consumidor React
```

### Tarefa para o Codex

Criar uma matriz completa dos canais IPC e classificar cada um como:

- conectado e testado;
- conectado sem teste;
- presente apenas no preload;
- presente apenas no backend;
- quebrado;
- legado;
- experimental.

## 4. Fluxo de intenções de texto e voz

### O que foi implementado

- Texto e voz passaram a compartilhar a mesma normalização de intenção.
- Foi criado tratamento de wake word para “ZARA” e variações.
- Foram adicionadas correções determinísticas para erros comuns do STT:
  - “Cláudio” → Claude;
  - “Cloud Code” → Claude Code;
  - “Corei” → Kore;
  - “codec”/“Codex” dependendo do contexto.
- Foi ampliado o reconhecimento de verbos coloquiais, incluindo:
  - abrir;
  - fechar;
  - minimizar;
  - maximizar;
  - aumentar;
  - diminuir;
  - ligar;
  - desligar;
  - copiar;
  - colar;
  - pesquisar;
  - tocar;
  - pausar;
  - ajustar brilho;
  - ajustar volume.

### Tarefa para o Codex

Garantir que cada novo verbo tenha testes para texto e voz. A matriz mínima deve cobrir:

| Intenção | Texto | Voz | Executor | Verificação |
|---|---:|---:|---|---|
| Abrir aplicativo | pendente de confirmação | pendente de confirmação | localizar | readback |
| Minimizar janela | pendente de confirmação | pendente de confirmação | localizar por nome | estado da janela |
| Maximizar janela | pendente de confirmação | pendente de confirmação | localizar por nome | estado da janela |
| Ajustar volume | pendente de confirmação | pendente de confirmação | Windows audio | leitura do volume |
| Ajustar brilho | pendente de confirmação | pendente de confirmação | Windows display | leitura do brilho |
| Copiar/colar | pendente de confirmação | pendente de confirmação | clipboard | readback |
| Pesquisar | pendente de confirmação | pendente de confirmação | navegador/web | URL ou resultado |

Uma alteração de intent deve ser aplicada e testada nos dois caminhos.

## 5. Proteção contra falso sucesso

### O que foi implementado

- Foi criado um bloqueio para frases que parecem comandos de computador, mas não foram reconhecidas por um handler determinístico.
- A ZARA deve responder honestamente que não sabe executar, em vez de afirmar que realizou a ação.
- Foi adicionada telemetria para:
  - intenções recusadas;
  - intenções que escaparam para o orquestrador;
  - falhas de ação;
  - lacunas de capacidade.

### Tarefa para o Codex

Auditar todos os caminhos de resposta e provar que nenhuma ação Windows é declarada concluída apenas porque o modelo respondeu.

Critério de aceite:

- uma ação reconhecida deve ter executor real;
- ações de risco devem passar por confirmação;
- quando possível, a ação deve ter readback/verifier;
- uma ação não reconhecida deve gerar resposta honesta;
- erro de modelo não pode ser convertido em sucesso de sistema.

## 6. Captura de lacunas de capacidade

### O que foi implementado

- Falhas de intenção não reconhecida podem ser registradas como `CapabilityGap`.
- Existe deduplicação por frase normalizada.
- Existe limite diário para novas lacunas.
- Existe limite diário para escalonamentos que podem gerar missões de melhoria.
- O objetivo é evitar que cada erro de voz gere uma chamada paga automática.

### Tarefa para o Codex

Testar:

1. deduplicação da mesma frase;
2. limite diário de novas lacunas;
3. limite diário de escalonamentos;
4. não geração de missão antes do limite definido;
5. não repetição de missão para o mesmo gap já escalonado;
6. preservação da paridade entre texto e voz.

## 7. ToolRouter e execução segura

### O que foi implementado

O `ToolRouter` possui o fluxo:

```text
VALIDATE
→ LOOKUP
→ SCHEMA
→ PERMISSION
→ EXECUTE
→ NORMALIZE
→ VERIFY
→ AUDIT
→ RESULT
```

O sistema possui integração ou suporte para:

- registro de ferramentas;
- registro antigo de ações;
- schemas;
- permission checker;
- confirmação;
- verifiers;
- auditoria;
- resultados estruturados;
- classificação de erros;
- fallback de compatibilidade.

### Risco atual

A coexistência de `ActionRegistry` e `ToolRouter` pode fazer com que ações diferentes sigam gates diferentes. Um caminho pode ter verifier e outro não.

### Tarefa para o Codex

Mapear quais ações:

- passam pelo `ToolRouter`;
- usam apenas `ActionRegistry`;
- usam fallback;
- têm permission checker;
- exigem confirmação;
- têm verifier;
- geram auditoria;
- possuem testes atuais.

Não criar um terceiro sistema de registro ou execução. Consolidar os caminhos existentes com compatibilidade controlada.

## 8. Controle real do Windows

### O que foi implementado ou corrigido

Há ações para:

- abrir aplicativos;
- focar janelas;
- minimizar janelas por nome;
- maximizar janelas;
- restaurar janelas;
- controlar brilho;
- controlar volume;
- consultar informações do sistema;
- abrir pastas;
- interagir com navegador;
- operar arquivos;
- usar terminal com gates.

Um problema importante foi corrigido: comandos como “Minimize o Chrome” deixaram de depender apenas da janela ativa e passaram a procurar a janela pelo nome.

### Tarefa para o Codex

Testar cada ação no Windows real e exigir readback/verificação. O teste precisa provar o efeito no sistema, não apenas a resposta textual da ZARA.

## 9. Memória persistente

### O que foi implementado

A ZARA possui memória:

- de usuário;
- de projeto;
- episódica;
- histórica;
- em SQLite;
- em JSON com backup;
- com escrita atômica;
- com limite de tamanho;
- com redaction de segredos.

Foram adicionados ou ampliados canais para:

- adicionar memória;
- buscar memória;
- listar memória;
- esquecer memória;
- consultar memória de projeto;
- listar memória de projeto;
- obter contexto de projeto.

Também existe uma bridge local para Obsidian/Galaxy.

### Limite atual

A existência da memória no backend e no preload não prova que todos os recursos chegaram a uma tela funcional na Home. A recuperação automática de memória no Planner também não deve ser presumida.

### Tarefa para o Codex

Confirmar, para cada recurso:

```text
memória
→ armazenamento
→ handler
→ canal IPC
→ tela/consumidor
→ teste
```

Testar escrita atômica, backup, redaction, busca, esquecimento e recuperação após reinício.

## 10. Voz, STT, TTS e interrupção

### O que foi implementado ou trabalhado

Existem caminhos para:

- Vosk;
- Gemini Live;
- Edge TTS;
- Kokoro;
- áudio PCM;
- microfone;
- AEC do Chromium;
- mute;
- interrupção de fala;
- barge-in;
- streaming de áudio.

A Home possui controle de voz e canais para envio de chunks de microfone. A interrupção foi trabalhada para cortar a fala atual, em vez de apenas enviar silêncio.

### Limite atual

A voz continua condicionada a:

- microfone;
- pacotes instalados;
- modelos disponíveis;
- configuração;
- rede, quando aplicável;
- teste físico no Windows.

### Tarefa para o Codex

Executar no Windows real:

1. iniciar voz;
2. falar uma solicitação;
3. aguardar o início da resposta;
4. interromper durante a fala;
5. confirmar que o áudio para;
6. confirmar que a próxima fala não é perdida;
7. testar mute/unmute;
8. registrar latência e falhas.

Sem esse teste, a voz deve permanecer marcada como **implementada, mas não validada ao vivo**.

## 11. Lab V1 multiagente

### O que foi implementado

Foi criado `core/lab_v1/`, separado do Lab legado. O modelo diferencia:

- provider;
- model;
- agent;
- role;
- team;
- session.

Também foram adicionados ou trabalhados:

- criação de sessões;
- criação de agentes;
- equipes;
- submissão de mensagens;
- delegação limitada;
- handoff;
- failover;
- cancelamento;
- exclusão de sessão;
- listagem de providers;
- autopilot;
- autonomia configurável;
- chat da equipe;
- pesquisa de skills.

Existe proteção contra self-delegation para evitar uma segunda chamada paga ao mesmo agente.

O retorno `QUEUED` significa que a solicitação foi recebida e persistida. Não significa que a missão foi concluída.

### Limites atuais

O Lab V1 não deve ser anunciado como:

- autonomia geral;
- executor autônomo irrestrito;
- scheduler completo;
- learned routing adaptativo;
- council completo;
- formação automática completa de equipes.

### Tarefa para o Codex

Validar:

- persistência de sessão;
- recuperação após reinício;
- failover;
- handoff;
- limite de delegações;
- ausência de perda de mensagens;
- ausência de chamada duplicada ao mesmo agente;
- retorno correto de `QUEUED`;
- isolamento entre banco do Lab legado e banco do Lab V1.

## 12. Autonomia e autopilot

### O que existe

Existem módulos e documentos relacionados a:

- autonomia;
- missões;
- evolução;
- autopilot;
- pesquisa;
- observação de falhas;
- melhoria orientada por lacunas.

### Limite atual

A existência desses módulos e documentos não prova que a autonomia geral está pronta ou conectada ao fluxo principal da Home.

### Tarefa para o Codex

Mapear o caller real de cada módulo e classificar cada um como:

- conectado e testado;
- conectado, mas sem teste;
- experimental;
- somente documentação;
- duplicado;
- perigoso;
- sem uso atual.

Nenhum módulo de autonomia deve ganhar permissão para executar ações fora do ToolRouter e dos gates existentes.

## 13. Telegram e integrações externas

### O que existe

Existem módulos para:

- Telegram;
- aprovação remota;
- grupos;
- webhook;
- importação;
- ponte de Telegram;
- áudio;
- bridges externas.

Também existem arquivos de configuração, locks e logs específicos.

### Limite atual

A presença de módulos não prova que a integração está ativa.

### Tarefa para o Codex

Para cada integração, confirmar:

- credencial configurada;
- processo ativo;
- canal correto;
- webhook ou polling;
- confirmação/aprovação;
- redaction;
- teste de ponta a ponta;
- comportamento quando offline.

## 14. Ferramentas auxiliares novas ou alteradas

O conjunto recente de alterações inclui ferramentas como:

- `tools/zara_validate.py`;
- `tools/quality_gate.py`;
- `tools/project_hygiene.py`;
- `tools/qa_home_ui.py`;
- `tools/probe_voice.py`;
- `tools/testar_intents.py`;
- `tools/system_stats.py`;
- `tools/zara_claude_bridge.py`;
- `tools/zara_telegram_bot.py`;
- `tools/room_relay/`;
- `tools/meeting_transcriber.py`;
- `tools/media_downloader.py`;
- `tools/mock_data_gen.py`;
- `tools/preparar_python.py`;
- `tools/price_watch.py`;
- `tools/smart_clipboard.py`;
- `tools/snippet_finder.py`;
- `tools/syntax_watcher.py`.

### Tarefa para o Codex

Classificar cada ferramenta como:

- usada pelo app em runtime;
- usada apenas no desenvolvimento;
- usada apenas em testes;
- protótipo;
- obsoleta;
- duplicada;
- candidata a quarentena.

Não incluir automaticamente ferramentas auxiliares no executável principal.

## 15. Documentação e conhecimento interno

Foram alterados muitos arquivos em `wiki/`, incluindo assuntos como:

- arquitetura de voz;
- AEC;
- wake word;
- roteamento de intenção;
- roteamento de modelos;
- controle do PC;
- verificação de ações;
- memória;
- Telegram;
- lembretes;
- scheduler;
- Lab;
- build;
- bridge;
- Supercérebro.

Também foram encontrados documentos novos ou recentes do Verdent:

- `.agent_context/AUTOPILOT_SPRINT.md`;
- `.claude/HANDOFF_VERDENT_2026-09-14.md`;
- `.claude/VERDENT_ADDENDUM_COMPUTADOR_ZARA.md`;
- `.claude/VERDENT_ADDENDUM_FINALIZACAO_E2E.md`.

### Tarefa para o Codex

Tratar documentação como contexto, não como prova. Para cada afirmação relevante, localizar:

```text
afirmação
→ implementação
→ caller
→ teste
→ evidência de runtime
```

Atualizar os documentos canônicos quando houver divergência entre documentação, código, build e testes.

## 16. Ordem recomendada para continuidade

### P0 — Antes de nova funcionalidade

1. Recuperar a conexão da pasta montada e preservar todas as alterações.
2. Não usar `git reset --hard`.
3. Não usar `git clean -fd`.
4. Não apagar bancos, memória, histórico ou snapshots.
5. Fazer inventário completo das alterações não commitadas.
6. Separar código-fonte, documentação, artefatos e arquivos locais.
7. Liberar o `app.asar` bloqueado.
8. Revalidar o build Windows.
9. Atualizar o estado de testes com evidência atual.

### P1 — Consolidar o funcionamento

1. Mapear todos os canais IPC ponta a ponta.
2. Mapear todas as ações Windows e seus verifiers.
3. Testar texto e voz com a mesma matriz de intenções.
4. Testar memória e histórico.
5. Testar Lab V1 com persistência e failover.
6. Testar voz e barge-in no Windows real.
7. Confirmar exatamente o que entra no próximo build.
8. Atualizar hashes e identidade do build.

### P2 — Higienizar e melhorar

1. Escolher oficialmente npm ou pnpm.
2. Separar claramente Lab legado e Lab V1.
3. Classificar os módulos de autonomia e autopilot.
4. Classificar integrações Telegram, MCP e navegador.
5. Remover ou marcar placeholders da Home.
6. Atualizar `ZARA_MASTER_CONTEXT.md`.
7. Atualizar `ZARA_DOCUMENTACAO_UNICA.md`.
8. Atualizar `ZARA_AGENT_START_HERE.md`.
9. Criar uma matriz única de capacidade.

## 17. Matriz de capacidade que o Codex deve criar

```text
capacidade
→ arquivo
→ caller
→ handler
→ executor
→ gate
→ verifier
→ teste
→ status
→ build incluído
```

O campo `status` deve usar uma das categorias:

- implementada e conectada;
- implementada, mas sem teste;
- implementada parcialmente;
- backend sem frontend;
- frontend sem backend;
- experimental;
- documentação apenas;
- quebrada;
- não conectada;
- não incluída no build atual.

## 18. Mensagem pronta para enviar ao Codex

> Codex, continue a ZARA considerando as seguintes novidades recentes: Home React Titanium Emerald, ponte IPC segura, normalização compartilhada de texto e voz, wake word, correção de nomes do STT, proteção contra falso sucesso, telemetria de lacunas, ToolRouter com gates e verificação, ações Windows por nome de janela, memória persistente, voz com AEC/TTS/STT/barge-in, Lab V1 multiagente com sessões, agentes, equipes, handoff e failover, autopilot e módulos de evolução, além das integrações Telegram e ferramentas auxiliares.
>
> Antes de implementar qualquer coisa, faça o inventário dos arquivos modificados e classifique cada novidade como: implementada e conectada; implementada sem integração; implementada sem teste; experimental; documentação; ou quebrada.
>
> Não trate documentação como prova. Para cada capacidade, localize caller, handler, executor, gate, verifier e teste. Preserve todas as alterações existentes. Não use `git reset --hard`, `git clean -fd` nem apague bancos, memória ou histórico.
>
> Prioridade imediata: corrigir o build bloqueado, atualizar a evidência de testes, validar os canais IPC e comprovar o runtime Windows. Depois consolidar voz, memória, ToolRouter, Lab V1 e integrações.

## 19. Referências principais

- `ZARA_AGENT_START_HERE.md`
- `ZARA_MASTER_CONTEXT.md`
- `docs/ZARA_DOCUMENTACAO_UNICA.md`
- `main.py`
- `core/ipc_handlers.py`
- `core/tool_router.py`
- `frontend/src/preload.ts`
- `frontend/src/renderer/App.tsx`
- `frontend/package.json`
- `.zara-tests/latest/ZARA_STATE.md`
- `build-current.log`
- `ZARA_ACTIVE_BUILD.json`

*Documento preparado por Manus AI para continuidade do trabalho do Codex.*

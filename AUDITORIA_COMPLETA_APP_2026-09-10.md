# Auditoria completa — ZARA 3.0

**Data:** 2026-09-10  
**Escopo:** estrutura da raiz, arquitetura, responsabilidades dos módulos, qualidade, segurança, build, testes, artefatos e estado crítico.  
**Método:** inspeção do contexto mestre, estado de validação, gates, política de testes, manifesto frontend, configuração Python, script de empacotamento e regras de governança. Nenhum arquivo de runtime foi alterado.

## 1. Veredito executivo

A ZARA 3.0 é um aplicativo desktop Windows com uma separação correta, em princípio, entre **interface Electron/React**, **ponte IPC via preload** e **backend Python sidecar**. O caminho operacional mais confiável é o de comandos simples: entrada de texto ou voz, resolução determinística, registro/roteamento de ação, gates de segurança, execução, normalização, auditoria e resposta.

Há evidência documentada de que o build atual foi aberto em Electron empacotado e executou o golden path de texto, abertura e minimização de janelas e leitura de métricas reais. Também há evidência de um runtime multiagente V1 validado em ambiente isolado de teste.

Entretanto, o projeto **não está em estado de release plenamente comprovado**. Os maiores riscos são:

1. **Higiene da raiz classificada como CRITICAL** no estado de validação.
2. **Estado desatualizado e contraditório:** `.zara-tests/latest/ZARA_STATE.md` aponta commit/validação de 2026-09-05, enquanto `ZARA_MASTER_CONTEXT.md` registra build e mudanças de 2026-09-06/07.
3. **Teste frontend falso:** `frontend/package.json` possui `npm test` como stub que sempre termina com código 0.
4. **Lab V1 validado, mas não promovido ao build operacional**, por falta de espaço em disco.
5. **Várias capacidades da Home são placeholders ou não estão conectadas**: Wi-Fi, energia, segurança, comunicações, projeto ativo e identidade real.
6. **Voz, barge-in, hardware e alguns caminhos condicionais ainda exigem teste Windows físico.**
7. **A cadeia de dependências e build está duplicada/inconsistente:** o contexto considera `requirements.txt` canônico, mas esse arquivo não foi encontrado na inspeção; o `pyproject.toml` e o build usam políticas parcialmente diferentes.

**Classificação geral:** funcionalidade central forte; governança e evidência de release insuficientes; risco operacional atual **alto** até reconciliar estado, raiz, testes e build.

## 2. O que existe na raiz e para que serve

| Área | Conteúdo principal | Função | Classificação |
|---|---|---|---|
| Documentação canônica | `README.md`, `ZARA_MASTER_CONTEXT.md` | Entrada curta e fonte operacional do estado | Deve permanecer |
| Governança | `CLAUDE.md`, `.claude/`, `.claude/rules/` | Regras de trabalho, testes, caminhos e decisões | Deve permanecer; não é runtime |
| Entrada Python | `main.py` | Inicia o backend IPC | Código essencial |
| Núcleo Python | `core/` | IPC, intenções, ações, roteamento, memória, voz, modelos, segurança, Lab | Código essencial, com módulos experimentais a auditar |
| Memória | `memory/` | Memória estruturada, episódica e contexto | Código essencial; dados não devem ficar no Git |
| Integrações | `integrations/` | Integrações externas e adaptadores | Código real/condicional; revisar callers |
| Frontend | `frontend/src/` | Electron main, preload, React renderer e Home | Código essencial |
| Configuração Python | `pyproject.toml` | Dependências, pytest, Ruff, mypy e entry points | Deve permanecer |
| Configuração Node | `frontend/package.json`, `package-lock.json` | Scripts, dependências, Electron Builder | Deve permanecer; definir política de lockfile |
| Build | `build_exe.py` | Cria somente `zara-backend.exe` via PyInstaller | Deve permanecer |
| Testes | `tests/`, `.zara-tests/` | Testes puros, sandbox, live e evidências | Deve permanecer; atualizar evidências |
| Configuração local | `config/` | Chaves e configurações locais | Manter exemplos; nunca versionar segredos |
| Artefatos | `dist-sidecar/`, `build-sidecar/`, `frontend/dist-*`, `frontend/release/` | Saídas geradas de build | Não são source of truth |
| Quarentena | `_quarentena/` | Histórico, snapshots e relatórios antigos | Histórico; não usar como estado atual |
| Estado local | `data/`, `lembretes/`, `.zara-dev/` | Dados/runtime e desenvolvimento local | Fora do Git; conservar só se usado |

## 3. Arquitetura funcional

### 3.1 Frontend/Electron

`frontend/src/main.ts` cria a janela Electron, inicia o sidecar e encaminha IPC. `frontend/src/preload.ts` expõe uma API mínima para o renderer. O desenho documentado usa `contextIsolation=true` e `nodeIntegration=false`, o que é uma decisão forte de segurança.

`frontend/src/renderer/App.tsx` é a raiz visual e deve renderizar `ZaraHome`. A Home Titanium Emerald compõe sidebar, status, cabeçalho, entrada de comando, cards, Core, dock de voz e faixa de sistema. Ela possui conexões reais para texto, estado do Core, voz, CPU/RAM/disco, bateria e relógio.

### 3.2 Backend Python

`main.py` inicia `core.ipc_handlers`. O dispatcher central é `core/ipc_handlers.py`. A detecção de intenções de voz/texto fica em `core/pc_voice_intent.py`. A execução de ações fica em `core/action_registry.py`, `core/actions/` e no `ToolRouter`.

O caminho de ferramenta declarado é:

`VALIDATE → LOOKUP → SCHEMA → PERMISSION → EXECUTE → NORMALIZE → VERIFY → AUDIT → RESULT`

Esse encadeamento é uma boa base: impede que modelos puros executem subprocessos, hardware ou rede diretamente e centraliza permissões. O risco é a coexistência de caminhos antigos e novos; é necessário provar que todas as ações de alto impacto passam pelo mesmo caminho e não pelo fallback legado sem gates equivalentes.

### 3.3 Planner

O domínio `core/planner/` tem modelos, validação topológica e execução segura via ToolRouter. Ele detecta IDs duplicados, ferramentas desconhecidas/bloqueadas, argumentos inválidos, dependências inválidas, auto-dependências e ciclos.

**Limite importante:** o `RulePlanner` aceita somente `explicit_steps`. Não existe, pelo estado documentado, decomposição automática confiável de linguagem natural nem `LLMPlanner`/`HybridPlanner` integrado ao fluxo geral. Portanto, a ZARA ainda não deve ser descrita como planner autônomo geral.

### 3.4 Voz

Existem canais de start/stop, envio de chunks, interrupção e áudio de saída. A cascata documentada é Vosk para STT local quando selecionado; Gemini Live de modo condicionado; e TTS Edge, Kokoro ou Gemini conforme configuração. O barge-in foi implementado, mas não recebeu prova física recente em microfone, áudio e latência no Windows.

### 3.5 Memória e histórico

A memória estruturada usa JSON atômico, backup, limite de tamanho, truncamento e redaction. O histórico de conversas usa SQLite. A ponte Obsidian cria vault local e índice mínimo. Isso é positivo, mas a ponte não prova que a memória relevante seja recuperada automaticamente para cada decisão de planejamento.

### 3.6 ZARA Lab V1

O Lab V1 fica separado do coordenador legado, com banco próprio. A separação PROVIDER/MODEL/AGENT/ROLE/TEAM/SESSION é conceitualmente forte. O runtime usa Claude CLI restrito, sem Bash/PowerShell/execução de código pelos agentes; o ToolRouter continua sendo o executor.

A aceitação documentada provou persistência, delegação, retorno à sessão, ausência de chain-of-thought armazenado, restart, failover e isolamento de produção. O Lab V1 responde `QUEUED`, corretamente sem alegar conclusão.

**Limite:** ele ainda não é scheduler novo, executor autônomo, router adaptativo, council completo ou formação automática de times. Além disso, não foi empacotado no build operacional atual.

## 4. Pontos fortes

- **Separação arquitetural clara** entre Electron, preload, React e sidecar Python.
- **Modelo de segurança explícito**, com capability, risco, permissão, confirmação e auditoria.
- **Preload endurecido** com isolamento de contexto e sem Node no renderer.
- **Fast path determinístico** adequado para comandos simples e mais fácil de validar do que uma automação totalmente baseada em LLM.
- **Planner com validação topológica** e sem privilégio próprio de execução.
- **Persistência mais segura** na memória, incluindo escrita atômica, backup e redaction.
- **Honestidade de produto** em vários pontos: estados `NOT_CONNECTED_YET`, custo desconhecido como `—`, resposta de falha sem fabricar sucesso e Lab respondendo `QUEUED`.
- **Runtime multiagente com isolamento de teste** e proteção contra self-delegation.
- **Build do sidecar com escopo controlado**, sem empacotar configuração, dados, vault ou logs.
- **Governança documentada** com fonte canônica e política para não executar testes live sem autorização.
- **Evidência real de Electron empacotado** para o golden path, não apenas preview Vite.

## 5. Pontos fracos

- O frontend não possui suíte de testes real: o script `test` informa que é stub e sempre sai com sucesso.
- A evidência de testes está fragmentada entre contexto mestre, `ZARA_STATE`, `GATES` e artefatos; há divergência temporal e de commit.
- A raiz contém histórico, candidatos e artefatos suficientes para ser classificada como crítica em higiene.
- A cadeia Node/Python tem mais de uma fonte potencial de dependências; o contexto declara `requirements.txt`, mas ele não foi localizado na inspeção.
- Dependências Python são majoritariamente abertas por `>=`, o que aumenta risco de builds não reprodutíveis.
- O build tem uma lista extensa de hidden imports e módulos experimentais, elevando tamanho, tempo e risco de divergência source/build.
- O frontend mantém canais e telas legadas coexistindo com a Home eleita, aumentando superfície de manutenção.
- A Home visual pode sugerir um produto mais conectado do que o backend realmente está: vários cards são placeholders explícitos.
- Cobertura de `verifier` varia por ferramenta; a existência do ToolRouter não significa que toda ação tenha verificação pós-execução.
- Módulos como `autonomy_engine`, `proactive_monitor`, `macro_engine`, MCP e visão ainda precisam de classificação por uso real antes de serem conectados ou arquivados.
- O projeto declara múltiplos sistemas operacionais no `pyproject.toml`, embora a arquitetura e os testes estejam claramente centrados em Windows.
- O `electron` declarado é uma versão antiga da linha 28; precisa de revisão controlada por segurança e compatibilidade antes de qualquer upgrade.

## 6. Estado crítico atual

### Crítico imediato — P0

| Item | Por que é crítico | Ação necessária |
|---|---|---|
| Estado de validação desatualizado | Pode levar a decisões baseadas no commit errado | Gerar novo estado datado após comparar `git rev-parse HEAD`, status e build ativo |
| Higiene da raiz | Aumenta confusão entre source, histórico e artefato; pode fazer build/atalho usar candidato errado | Inventariar e classificar cada item; arquivar ou remover somente de forma reversível |
| `npm test` falso | CI ou operador pode interpretar código 0 como testes passando | Substituir por suíte real ou fazer o script falhar explicitamente enquanto não houver suíte |
| Lab V1 não promovido | Funcionalidade validada não está no executável que o usuário abre | Decidir promoção; liberar espaço e executar build/validação completa sem misturar artefatos |
| Prova de voz física ausente | Microfone, TTS, barge-in e dependências nativas podem falhar só no pacote | Executar teste Windows live autorizado e registrar latência/resultados |

### Alto — P1

- Reconciliar `ZARA_MASTER_CONTEXT.md`, `.zara-tests/latest/`, `GATES.md`, identidade do build e commit real.
- Provar que o atalho e o launcher apontam apenas para o build ativo com hash correspondente.
- Mapear todos os entry points de ação e eliminar bypass do ToolRouter/gates.
- Definir contrato mínimo e cobertura de verifiers para ações de alto impacto.
- Consolidar logs sem parâmetros sensíveis e validar redaction em histórico, memória, export e auditoria.
- Decidir oficialmente npm versus pnpm e pyproject versus requirements, sem apagar lockfile por suposição.

### Médio — P2

- Conectar Planner ao fluxo geral somente após definir política de confirmação e limite de custo.
- Integrar recuperação de memória relevante com limites e redaction.
- Ligar Wi-Fi, energia e segurança apenas com estado backend real.
- Definir fonte de projeto ativo, comunicações e identidade do usuário.
- Classificar módulos experimentais por caller real e custo de manutenção.

## 7. O que parece lixo, o que é histórico e o que não pode ser apagado

### Candidatos a limpeza/arquivamento reversível

- `frontend/dist-*`, `frontend/release/`, `dist-sidecar/`, `build-sidecar/` quando não forem o build ativo nem evidência necessária.
- `__pycache__`, caches de TypeScript, Ruff, mypy, pytest e diretórios temporários.
- Candidatos antigos `frontend/release-candidate-*` e `ZARA-UPDATE-*`, após confirmar que nenhum launcher aponta para eles.
- Dumps/ZIPs de interface arquivada, se houver cópia canônica e hash/documentação do conteúdo.
- Relatórios antigos soltos ou redundantes, desde que permaneçam na quarentena e não sejam tratados como estado atual.

### Não são lixo

- `core/`, `memory/`, `integrations/`, `frontend/src/`, `tests/`, `.zara-tests/` e arquivos de configuração canônicos.
- `ZARA_MASTER_CONTEXT.md`, `CLAUDE.md`, `.claude/`, `GATES.md` e políticas de teste.
- Baselines e evidências datadas que comprovem decisões ou releases, mesmo que não sejam runtime.
- `config/*.example.json`; são contratos/documentação de configuração, desde que não contenham segredos.

### Proibição

Não apagar histórico, bancos, snapshots ou candidatos sem inventário, hash/backup e confirmação de que não são necessários para recuperação. A política do projeto favorece arquivamento reversível.

## 8. Plano recomendado

### Fase 1 — saneamento e verdade do estado

1. Capturar `git rev-parse HEAD`, branch, `git status`, build ativo, hash do executável e espaço em disco.
2. Atualizar `ZARA_STATE.md` e evidências para o commit real.
3. Produzir inventário da raiz com tamanho, data, dono funcional e classificação: source, config, evidência, histórico, cache ou candidato.
4. Verificar todos os launchers e o `ZARA_ACTIVE_BUILD.json`.

### Fase 2 — gates de qualidade

1. Remover o falso positivo de `npm test`.
2. Executar `npm run typecheck`, `npm run build` e lint em sequência.
3. Executar `tools/zara_validate.py` conforme a política antes de pytest completo.
4. Rodar testes puros/sandbox; testes live apenas em Windows e com autorização explícita.
5. Registrar falhas e evidências com timestamp, commit e artefato.

### Fase 3 — release e produto

1. Decidir se o Lab V1 entra no build atual.
2. Empacotar candidato limpo em disco suficiente.
3. Validar preload, spawn do sidecar, texto, ação com confirmação, memória, voz e interrupção.
4. Só então declarar um novo build como operacional.
5. Depois do release, atacar placeholders e integração real do Planner/memória.

## 9. Conclusão

A ZARA não é um amontoado sem estrutura: existe um núcleo funcional, uma arquitetura coerente e várias decisões de segurança acima da média. O problema principal hoje não é falta de código; é **controle de estado, higiene de artefatos e prova de release**.

A recomendação é **não ampliar capacidades agora**. Primeiro deve-se reconciliar o estado real, sanear a raiz, eliminar o teste frontend falso e executar a validação empacotada completa. Só depois vale decidir a promoção do Lab V1 e a conexão dos placeholders. Isso reduz o risco de construir novas funcionalidades sobre um build ou evidência incorretos.

## 10. Limitações desta auditoria

A inspeção do terminal remoto do computador Windows apresentou falha de canal durante a listagem automática. Portanto, este documento usa como fonte primária os arquivos canônicos já presentes no projeto e os arquivos lidos diretamente; a lista final de cada item físico da raiz, tamanhos atuais, status Git atual e execução de comandos Windows deve ser confirmada na Fase 1 antes de qualquer remoção ou declaração de release.

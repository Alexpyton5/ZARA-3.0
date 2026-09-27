# Auditoria integral da ZARA 3.0

**Data da auditoria:** 19 de setembro de 2026  
**Projeto auditado:** `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`  
**Escopo:** propósito do produto, arquitetura, capacidades reais, funcionalidades incompletas, riscos críticos, higiene da pasta e prontidão para novos builds.

## 1. Veredito executivo

A ZARA é um **assistente pessoal de desktop para Windows**, inspirado em um operador tipo JARVIS. O objetivo do produto é receber comandos por texto e voz, interpretar a intenção, executar ações reais no computador com controle de risco, confirmar o resultado quando possível, manter memória persistente e coordenar tarefas de pesquisa ou trabalho por meio do ZARA Lab.

Ela não é apenas uma tela de chat. A parte mais importante do produto é a cadeia **comando → interpretação determinística → autorização → execução real → verificação → auditoria**. O frontend Electron/React é a interface e o supervisor de processos; o sidecar Python concentra a inteligência operacional, as ações Windows, a memória, os modelos, a voz e os registros.

O núcleo do produto está implementado e possui arquitetura de segurança acima de um protótipo comum. Entretanto, o repositório está em estado de **desenvolvimento avançado, mas não de release plenamente comprovado**. Há quatro fatores que impedem declarar o aplicativo como totalmente pronto:

1. A evidência de testes consolidada está desatualizada em relação às mudanças de 17 a 19 de setembro.
2. O build atual está sofrendo bloqueio por processo que mantém um `app.asar` de staging aberto.
3. A Home apresenta alguns estados visuais explicitamente não conectados, enquanto vários módulos backend existem sem integração de produto.
4. A pasta contém muitos artefatos, relatórios, stagings e duas cadeias de dependências Node, o que aumenta o risco de usar um build ou fonte errados.

**Conclusão:** a ZARA já tem um produto real e identificável. O próximo passo correto não é adicionar mais módulos. É consolidar a fonte de verdade, atualizar a evidência, limpar artefatos com segurança e provar o caminho completo no Windows.

## 2. Para que a ZARA serve

O uso principal da ZARA é permitir que Alex controle e consulte o próprio computador por uma interface pessoal unificada. O usuário pode conversar com a ZARA, pedir informações do sistema, abrir ou controlar aplicativos, interagir com arquivos, usar navegador e terminal conforme os gates de segurança, falar por voz, consultar memória e enviar trabalho para o Lab.

A proposta de valor pode ser resumida em quatro funções:

- **Assistente operacional:** executar ações reais no Windows sem fingir que uma ação ocorreu apenas porque um modelo gerou uma resposta.
- **Memória pessoal e de projeto:** guardar fatos, histórico de conversas, episódios e documentos relevantes com redaction, backup e limites.
- **Interface multimodal:** oferecer texto, voz, áudio de saída, estado do Core, métricas do sistema e controles de janela em uma Home única.
- **Orquestração controlada:** rotear modelos, organizar sessões e agentes no Lab V1 e registrar propostas, handoffs, falhas e custos sem conceder ao modelo controle direto do computador.

O produto, portanto, é mais próximo de um **agente operacional pessoal com supervisão e memória** do que de um chatbot tradicional. O Lab é uma extensão de coordenação e pesquisa; não deve ser descrito como autonomia irrestrita.

## 3. Como o app funciona

A arquitetura atual possui três camadas principais:

```text
React/TypeScript
    ↓ window.zaraIPC / contextBridge
Electron Main + Preload
    ↓ stdin/stdout e IPC supervisionado
Sidecar Python
    ↓
intenção, ações, gates, modelos, voz, memória e auditoria
```

### 3.1 Frontend e Electron

`frontend/src/renderer/App.tsx` renderiza a Home React Titanium Emerald. A Home não é mais um iframe estático. Ela usa componentes React reais em `frontend/src/renderer/components/zara-home/`.

`frontend/src/main.ts` cria a janela Electron, controla o ciclo de vida, inicia o sidecar e encaminha eventos. `frontend/src/preload.ts` expõe a superfície `window.zaraIPC` usando `contextBridge`, com `contextIsolation` e sem `nodeIntegration` conforme a governança do projeto.

A ponte expõe mensagens, histórico, memória, ações, métricas, voz, configuração, Lab legado, Lab V1, lembretes, controles de janela e eventos de estado. Essa superfície é ampla, mas organizada por domínios.

### 3.2 Backend Python

`main.py` prepara os diretórios graváveis do usuário, tenta adquirir o lock de escritor, verifica dependências essenciais e inicia `core.ipc_handlers`.

`core/ipc_handlers.py` é o dispatcher central. Ele normaliza texto e nomes, remove o wake word, compartilha o caminho de intenção entre texto e voz, bloqueia sinais de ações locais não reconhecidas e encaminha solicitações para o caminho determinístico ou para o orquestrador de modelos.

O caminho de ação pretendido é:

```text
VALIDATE → LOOKUP → SCHEMA → PERMISSION → EXECUTE
→ NORMALIZE → VERIFY → AUDIT → RESULT
```

Esse fluxo está implementado em `core/tool_router.py`. O roteador é determinístico e não chama LLM diretamente. A integração final depende de quais registries, permission checkers, verifiers e handlers estão ligados em cada caminho.

### 3.3 Memória e persistência

A aplicação possui histórico de conversas em SQLite, memória estruturada com escrita atômica e backup, memória episódica, memória de projeto e uma bridge local para Obsidian/Galaxy. A memória não deve ser confundida com recuperação global automática: a documentação indica limites e recuperação seletiva, e o contexto do Planner ainda precisa ser consolidado.

### 3.4 Voz

Há canais para iniciar e parar voz, enviar chunks de microfone, silenciar, tocar PCM e interromper fala. O backend suporta caminhos condicionais para Vosk, Gemini Live, Edge TTS e Kokoro. A interrupção/barge-in está implementada no código, mas a capacidade física depende de dispositivo, pacotes, rede e teste real no Windows.

### 3.5 Lab

Existem dois domínios que não devem ser confundidos:

- `core/lab_coordinator.py` e os canais `lab-*` representam o Lab legado.
- `core/lab_v1/` representa o runtime multiagente V1, com provider, model, agent, role, team e session separados.

O Lab V1 possui sessões, equipes, agentes, delegação limitada, handoffs e failover. O resultado `QUEUED` significa recebido e persistido, não concluído. Não há, segundo a documentação canônica, scheduler novo, executor autônomo irrestrito, learned routing ou formação automática completa de equipes.

## 4. O que já existe e funciona, com limites

| Domínio | Estado auditado | Limite principal |
|---|---|---|
| Home React Titanium Emerald | Implementado | A Home depende de contratos IPC e alguns cards ainda exibem estado não conectado quando não há fonte real. |
| Texto | Implementado | Depende do sidecar, do provider configurado e da rota de intenção. |
| Histórico | Implementado | SQLite e canais existem; a cobertura atual precisa de nova prova após as mudanças recentes. |
| Ações Windows | Implementado | Ações passam por registro/gates, mas a cobertura de verifiers varia. |
| Controle de janelas | Implementado | O caminho por nome de janela foi corrigido e já teve prova histórica. |
| Arquivos | Implementado com gate | Operações de risco exigem validação de caminho e confirmação. |
| Terminal | Implementado com gate | A segurança depende da política e do allowlist em vigor. |
| Browser/Selenium | Condicional | Requer navegador, driver e configuração; não deve ser declarado disponível só por existir módulo. |
| Roteamento de modelos | Implementado | Provider, credenciais, rede e disponibilidade real condicionam o resultado. |
| Memória estruturada | Implementado | Usa JSON, backup, escrita atômica, limites e redaction. |
| Memória episódica | Implementada | A cobertura de recuperação precisa de validação atualizada. |
| Conversas | Implementado | SQLite real; há risco operacional se dois processos escreverem no mesmo data dir. |
| Voz STT/TTS | Condicional | Depende de hardware, modelos, pacotes, rede e teste live no Windows. |
| Barge-in | Implementado no código | Ainda requer medição física de latência e interrupção. |
| Planner | Parcial | O domínio valida e executa `explicit_steps`; não decompõe qualquer objetivo natural automaticamente. |
| Verificação de resultados | Parcial | O ToolRouter suporta verifier, mas nem toda ferramenta tem verificador comprovado. |
| Lab V1 | Implementado e limitado | Coordenação multiagente V1, não autonomia geral. |
| Wi-Fi na Home | Não conectado | Existem ações, mas a Home não consulta esse canal. |
| Energia na Home | Não conectado | Existem ações, mas a Home não liga list/set. |
| Segurança na Home | Placeholder | Não há ação correspondente comprovadamente conectada à tela. |
| Comunicações | Placeholder | Não há fonte real para contagens. |
| Projeto ativo/progresso | Placeholder | Não há conceito backend consumido pela Home. |
| Perfil | Fallback | O nome `Alex Silva` é fixo; não há autenticação de identidade. |

## 5. O que ainda não funciona ou não deve ser anunciado como pronto

### 5.1 Autonomia geral

O nome “autopilot” aparece em documentos e módulos, mas o produto não deve ser descrito como uma entidade que recebe qualquer objetivo e controla o PC sem supervisão. O Planner atual é explícito e validado; o Lab limita delegações; o executor continua sendo o ToolRouter.

### 5.2 Integrações condicionais

A presença de código para Gemini, Telegram, Obsidian, navegador, MCP, visão, automações ou providers não prova que a integração está ativa. Cada uma depende de credencial, configuração, conectividade, processo externo e teste específico.

### 5.3 Voz física

A voz é uma capacidade implementada, mas ainda não é uma capacidade universalmente validada. Microfone, STT, TTS, latência, áudio PCM e barge-in precisam de uma rodada Windows live com hardware real.

### 5.4 Cobertura dos verifiers

O ToolRouter sabe verificar quando recebe um verifier, mas o código do roteador não garante por si só que toda ação registrada tenha verifier. Esse é um risco de produto: uma resposta pode ser estruturada como sucesso sem a mesma força de evidência em todas as ferramentas.

### 5.5 Contratos IPC e duplicidade de caminhos

A coexistência de `ActionRegistry` e `ToolRouter`, do Lab legado e do Lab V1, e de vários canais de configuração aumenta o risco de uma funcionalidade funcionar por um caminho e permanecer quebrada por outro. A consolidação deve mapear caller, handler, executor e teste para cada canal crítico.

## 6. Estado crítico identificado

### P0 — impedir release confiável

**P0.1 — Evidência de testes desatualizada.** O arquivo `.zara-tests/latest/ZARA_STATE.md` registra validação de 5 de setembro, enquanto o código, a documentação e o build ativo possuem mudanças posteriores. Esse arquivo não pode ser usado para declarar o estado atual sem nova execução.

**P0.2 — Build bloqueado por arquivo em uso.** O último empacotamento Windows parou ao tentar manipular `frontend/.current-build-staging-20260917-131439/.../resources/app.asar`, com `WinError 32`. Um processo Electron/ZARA ainda mantém esse arquivo aberto. O novo build não deve ser promovido enquanto a candidate não terminar e seus hashes não forem conferidos.

**P0.3 — Divergência entre documentação e ponteiro.** Os documentos canônicos ainda mencionam `release-candidate-fix-9router-v2-20260917-0020`, enquanto `ZARA_ACTIVE_BUILD.json` observado durante a auditoria aponta para `release-candidate-autonomia-20260919-0608`. Essa divergência impede saber, apenas pela documentação, qual identidade é realmente operacional.

### P1 — risco alto de manutenção e comportamento

**P1.1 — Integração parcial entre registros e roteador.** O código mantém fallback entre `ToolRouter` e `ActionRegistry`. Isso preserva compatibilidade, mas dificulta garantir de forma uniforme permission check, confirmação, verifier e auditoria.

**P1.2 — Muitos módulos experimentais no mesmo checkout.** Autonomia, macros, visão, MCP, integrações externas e bridges coexistem com o núcleo. Sem caller e teste recente, esses módulos devem permanecer explicitamente condicionais ou ser arquivados de forma reversível.

**P1.3 — Duas cadeias Node.** O frontend contém `package-lock.json`, `pnpm-lock.yaml` e `pnpm-workspace.yaml`, enquanto os scripts observados usam `npm`. Isso cria risco de instalação não determinística e deve ser resolvido por decisão explícita, não por apagar um lockfile sem validação.

**P1.4 — Execução como administrador.** O log do build mostra PyInstaller executado como administrador e emite aviso de depreciação. Isso não quebrou o build, mas é uma prática operacional desnecessária e deve ser removida para reduzir risco.

### P2 — produto incompleto ou poluído

**P2.1 — Cards visuais sem fonte de dados.** Wi-Fi, energia, segurança, comunicações, projeto ativo e identidade real ainda não são capacidades de produto conectadas. O estado visual honesto é preferível a fabricar números, mas esses cards devem ser tratados como backlog de produto ou removidos da promessa comercial.

**P2.2 — Lab legado e V1 paralelos.** A separação é documentada, mas aumenta o custo cognitivo e o risco de enviar eventos para o banco ou canal errado. É necessário manter uma matriz clara de ownership.

**P2.3 — Testes de frontend limitados.** O `package.json` contém quatro testes Node focados no Lab, mas não substitui typecheck, lint, build, smoke Electron e teste de IPC. A documentação antiga também chama `npm test` de stub; esse ponto precisa ser reconciliado com o conteúdo atual do pacote.

## 7. Higiene da pasta

A pasta precisa de higienização, mas **não de uma limpeza destrutiva**. A governança proíbe apagar memória, bancos, histórico ou snapshots sem backup/decisão explícita.

### Manter como fonte operacional

Devem permanecer como fonte de verdade `main.py`, `build_exe.py`, `pyproject.toml`, `core/`, `memory/`, `voice/`, `plugins/`, `frontend/src/`, `frontend/public/`, `tests/`, `.zara-tests/`, `config/` sob controle de segredo, `ZARA_ACTIVE_BUILD.json`, os scripts canônicos de build e a documentação única.

### Tratar como regenerável ou staging

`dist-sidecar/`, `build-sidecar/`, `frontend/dist-*`, `frontend/release/`, `frontend/release-candidate-*`, `.current-build-staging-*`, caches, `__pycache__`, `*.tsbuildinfo`, logs de build e manifests derivados não são fonte de código. Stagings bloqueados devem primeiro ser liberados por processos; depois podem ser removidos ou arquivados conforme o pipeline.

### Revisar com prioridade

`config/api_keys.json`, logs do Telegram, locks de integração, bancos em `data/`, relatórios e dumps na raiz devem passar por uma revisão de segredo, retenção e versionamento. A auditoria não expõe valores desses arquivos. A pergunta correta é se cada item é necessário no checkout, está no `.gitignore`, contém segredo ou é apenas estado local.

A coexistência de `docs/`, `_quarentena/`, `artifacts/`, logs de build e vários documentos de missão torna difícil distinguir estado atual de histórico. A solução recomendada é manter um único documento de estado canônico e mover relatórios antigos para quarentena reversível, com inventário, sem apagar dados.

## 8. O que eu faria primeiro

### Passo 1 — fechar a identidade do produto e do build

Atualizar `ZARA_AGENT_START_HERE.md`, `ZARA_DOCUMENTACAO_UNICA.md`, `ZARA_MASTER_CONTEXT.md` e `ZARA_ACTIVE_BUILD.json` para apontarem para a mesma candidate, branch, commit, timestamp e hashes. Nenhum documento deve continuar afirmando que outro diretório é o build operacional.

### Passo 2 — liberar o bloqueio e gerar uma candidate limpa

Fechar somente processos associados à ZARA/Electron, repetir o pipeline canônico e confirmar que a nova candidate contém `ZARA 3.0.exe`, `resources/app.asar` e `resources/backend/zara-backend.exe`. O build anterior deve continuar preservado até a verificação.

### Passo 3 — atualizar a evidência

No Windows, executar `npm run typecheck`, `npm run lint`, `npm run build`, pytest seguro e smoke do Electron empacotado. Depois testar texto, histórico, uma ação com confirmação, memória, estado do Core, start/stop de voz e interrupção, registrando o que não for possível testar.

### Passo 4 — consolidar os contratos de ação

Produzir uma matriz com `ação → caller → handler → executor → permission gate → confirmation → verifier → teste`. Começar por abrir aplicativo, foco/minimizar/restaurar janela, arquivos, terminal, navegador e volume/brilho.

### Passo 5 — separar produto pronto de laboratório

Manter módulos experimentais no checkout, mas marcar claramente sua condição. Para cada um, escolher entre integrar com teste, manter atrás de feature flag ou mover para quarentena reversível. Não conectar mais cards da Home antes de existir estado backend real.

### Passo 6 — higienizar sem apagar

Classificar arquivos em fonte, estado local, artefato regenerável, relatório atual e histórico. Remover apenas caches e artefatos que não estejam em uso; arquivar o restante com inventário. Validar `.gitignore` para chaves, bancos, logs e builds.

## 9. Limites desta auditoria

Esta auditoria foi feita por inspeção de código, documentação, ponteiro de build, logs e estrutura do checkout. Não foi feita uma rodada física de microfone, navegador, Electron empacotado, ações Windows ou hardware. Portanto, as conclusões distinguem implementação presente de capacidade comprovada em runtime.

Também não é seguro usar o estado de testes de 5 de setembro como prova do código de 19 de setembro. A próxima conclusão de release precisa de uma execução nova no Windows.

## 10. Resultado final

A ZARA **serve para ser o centro operacional pessoal do Alex no Windows**: conversar, ouvir, lembrar, consultar, agir e coordenar trabalho com honestidade sobre o que foi realmente executado. O núcleo já existe e está bem definido.

O estado crítico não é falta de visão do produto. É falta de convergência operacional: build bloqueado, evidência atrasada, documentação divergente e excesso de artefatos paralelos. Se esses quatro pontos forem resolvidos antes de novas expansões, será possível saber exatamente qual ZARA está sendo executada e quais capacidades podem ser prometidas.

## Referências

[1]: ../ZARA_AGENT_START_HERE.md "Guia operacional canônico da ZARA"
[2]: ../ZARA_MASTER_CONTEXT.md "Contexto mestre canônico da ZARA"
[3]: ./ZARA_DOCUMENTACAO_UNICA.md "Documentação única da ZARA"
[4]: ../main.py "Ponto de entrada do sidecar Python"
[5]: ../core/ipc_handlers.py "Dispatcher IPC central"
[6]: ../core/tool_router.py "Roteador determinístico de ferramentas"
[7]: ../frontend/src/preload.ts "Ponte segura Electron-React"
[8]: ../frontend/src/renderer/App.tsx "Raiz visual React"
[9]: ../frontend/package.json "Scripts e dependências do frontend"
[10]: ../.zara-tests/latest/ZARA_STATE.md "Estado de testes mais recente disponível"
[11]: ../build-current.log "Log do último pipeline de build"
[12]: ../ZARA_ACTIVE_BUILD.json "Ponteiro do build ativo"
[13]: ../AGENTS.md "Regras de trabalho do repositório"

*Relatório preparado por Manus AI.*

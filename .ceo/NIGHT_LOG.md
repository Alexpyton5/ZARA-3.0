# ZARA — NIGHT LOG

## 2026-09-03 — Tomada de controle inicial

- O arquivo de missão do proprietário foi lido integralmente.
- A raiz canônica foi confirmada pelo README: `C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`.
- Foram consultados o README, `CLAUDE.md`, `ARCHITECTURE_MAP.md`, `.zara-tests/latest.json`, `.zara-tests/baseline.json`, `.known_failures.json`, o histórico/ref local da branch de trabalho e a auditoria de saúde mais recente.
- Nenhuma alteração de código foi feita nesta etapa.
- Foram criados/atualizados `ZARA_CURRENT_STATE.md`, `ZARA_ARCHITECTURE.md`, `ZARA_DECISIONS.md` e a camada `.ceo/`.
- A principal prioridade é o bloqueio P0 do sidecar PyInstaller, não um redesign ou uma reconstrução arquitetural.
- A execução remota de comandos no Windows não respondeu; branch limpa, status do working tree e espaço em disco permanecem não confirmados.

**Próximo passo:** inspecionar a configuração de empacotamento e os artefatos do sidecar; escolher o menor diagnóstico seguro antes de qualquer rebuild.

## 2026-09-04 madrugada — NIGHT MODE, ZARA-P0-01/02 resolvidos

Esta sessão tem execução real no Windows do Alex (a anterior não tinha). Reexecutei o
diagnóstico do zero em vez de herdar a hipótese registrada.

- **Causa real do P0 não era vosk/PIL.** Rodei `frontend/release/win-unpacked/resources/backend/zara-backend.exe`
  standalone: crash imediato, `ModuleNotFoundError: No module named 'core.actions.system_advanced'`,
  disparado em `core/action_registry.py:709 load_advanced_action_exports` (import dinâmico via
  importlib, invisível para a análise estática do PyInstaller).
- **Root cause:** `build_exe.py` tinha uma lista manual de hiddenimports para `core.actions.*`
  faltando 3 módulos: `system_advanced`, `macro_actions`, `vision_actions`. Os outros módulos de
  `core/actions/__init__.py` são import estático (achados sozinhos); só esses 3 são carregados
  dinamicamente em `action_registry.py:697-699` e dependiam da lista manual.
- **Fix:** 3 linhas adicionadas em `build_exe.py`. Rebuild do sidecar (`dist-sidecar/zara-backend.exe`,
  hash `1139689a...`). Boot standalone confirmado: `SYS: Interface neural pronta` em ~35s, sem
  traceback.
- **Candidato:** copiei o sidecar corrigido por cima de `frontend/release/win-unpacked/resources/backend/zara-backend.exe`
  (convenção de candidato único confirmada por `ABRIR-A-ZARA.bat` + `ULTIMO_CANDIDATO.txt/.json` —
  não é a lineage múltipla que `.claude/rules/build-release.md` descreve; essa doc está desatualizada
  frente à prática atual). Hash conferido byte a byte entre `dist-sidecar` e o pacote.
  `ULTIMO_CANDIDATO.json` e `.txt` atualizados; `BUILD_INFO.json` do candidato com DELTA preenchido.
- **Handshake real testado:** abri `ZARA 3.0.exe` de verdade (não simulação). `zara-backend.exe`
  nasceu como filho do processo Electron e continuou vivo além dos 45s do timeout de
  `startPythonSidecar` em `main.ts` — se não tivesse ficado pronto a tempo, `main.ts` mata o filho
  sozinho; como não matou, o handshake completou. Fechei com `taskkill /F /T` só no processo
  Electron (mesma convenção do `.bat`): a árvore inteira, incluindo os dois processos
  `zara-backend.exe` (bootloader onefile + processo real), morreu junto. Sem órfão.
- **O que NÃO está provado:** não vi a tela com os próprios olhos (nem com computer-use — pediria
  aprovação na tela do Alex, que está dormindo). Nível de evidência é `PACKAGED_RUNTIME`
  (processo real, candidato real, postcondição observada por processo), não `PHYSICAL_BY_ALEX`.
  Isso fica pendente pra ele confirmar visualmente amanhã.
- **Checkpoint:** commit isolado só de `build_exe.py` + `ULTIMO_CANDIDATO.json/.txt` (o delta
  causal desta tarefa). Não toquei nos outros 25 arquivos sujos do working tree (UI em progresso
  de outra sessão) — fora de escopo, não é minha área esta noite.

ZARA-P0-01 e ZARA-P0-02 do `.ceo/BOARD.md`: de `BLOCKED_REQUIRES_OWNER`/`TODO` para **RESOLVED
(PACKAGED_RUNTIME)**, pendente confirmação física.

**Próximo passo:** T2 — comando de texto real ponta-a-ponta (Electron → IPC → sidecar → resposta),
usando este mesmo candidato.

### T2 — comando de texto real (mesma madrugada)

Testei o handler real (`handle_send_message`, o mesmo que o Electron chama) mandando um frame
IPC de verdade pelo stdin do sidecar corrigido, sem simulação:

```
IN:  {"type":"send-message","request_id":"test-1","payload":{"text":"que horas sao?"}}
OUT: {"type":"response","request_id":"test-1","response":{"response":"Agora são 01:16.","engine":"pc_control","selo":"verificado"}}
```

Resposta bate com o relógio real no momento do teste, `selo: verificado` (veio do executor, não
é string fixa). **T2 provado no nível RUNTIME_AUTOMATED** para o backend; a metade
Electron→renderer (o campo de texto de verdade na UI) ainda não foi clicada por ninguém — isso
some com computer-use exigiria aprovação na tela do Alex, então fica pendente de teste físico.

**Achado colateral, não bloqueante:** no boot aparecem avisos `"... ilegivel, usando padrao:
Expecting value: line 1 column 1 (char 0)"` para `wake_word_mode`, `audio_transport`, 3 chaves
de `vad_*` e Telegram — parece um arquivo de preferências ausente/vazio, cai pro padrão sem
quebrar nada. Não investiguei a fundo (fora do escopo de T1/T2 desta madrugada); registrado
como item pequeno pra revisar depois, não é `KNOWN_BROKEN` até alguém confirmar que importa.

**Próximo passo real:** antes de avançar pro resto da lista T3-T18 do dono, realinhar com a
ordem que o próprio Alex travou em `time-zara.md` (Fase 1: voz Kore na saída → latência →
microfone sem eco → voz→ação real). Checando o estado atual de voz Kore agora.

### Achado colateral sério: disco C quase cheio (não é tarefa desta madrugada, só registro)

Ao investigar por que ainda há risco de repetir o incidente antigo
(`ZARA-BACKEND-PYINSTALLER-RECOVERY-002`, %TEMP% cheio → extração PyInstaller falha), medi o
disco: **C: com 5,2 GB livres de 237 GB (98% usado)**, mesmo depois de eu limpar 5 pastas
`_MEI*` órfãs (~2,8 GB) que os meus próprios testes desta madrugada deixaram para trás. Limpei
só o que eu mesmo sujei — não fiz faxina geral no disco (isso é tarefa própria, com inventário
e backup, não efeito colateral de T1/T2).

**Isso é o mesmo tipo de risco que já derrubou o backend antes.** Não bloqueou nada hoje, mas
está perto o suficiente pra merecer atenção logo — cada rebuild completo (sidecar + Electron)
usa uns GBs de temp/build. Não vou fazer limpeza ampla de disco sem autorização específica;
só sinalizando pra manhã.

### Alex mandou mensagem ao vivo: "continue trabalhando em melhorias e conexões da interface"

Isso quebrou o silêncio da madrugada (é uma mensagem real, não notificação de tarefa). Respondi
curto e continuei.

Achei `ZARA_HOME_UI_INTEGRATION.md` — outra sessão já tinha trocado o iframe antigo da Home por
componentes React reais, com texto/voz/Core/CPU-RAM-disco/bateria já conectados de verdade, mas
**nunca commitado**. Documento próprio já apontava 2 conexões triviais pendentes: Wi-Fi e planos
de energia, ambos com action real no backend, só faltando o fio até o componente.

Liguei os dois: `useWifiStatus.ts` (os_wifi_status) e `usePowerPlans.ts` (os_power_plan_list/
os_power_plan_set, com reverificação após trocar) — ambos em
`core/actions/system_advanced.py`, o MESMO módulo que só passou a carregar no pacote depois do
fix de hiddenimports desta madrugada (commit ada233c). Sem os dois fixes juntos, essas duas
conexões não teriam onde pousar.

`npm run typecheck` limpo. `npm run lint`: 3 erros pré-existentes (`'React' is not defined` em
SystemPanel.tsx x2 e TextCommandInput.tsx, de antes desta sessão) — não mexi, fora do meu
escopo. `npm run build` e `npm run electron:build` (pipeline completo, gera o EXE + instalador)
passaram limpo.

Rebuild completo virou candidato novo em `frontend/release/win-unpacked` (sidecar corrigido +
UI nova juntos). Testei de novo o mesmo jeito do T1: `zara-backend.exe` sobreviveu ao timeout de
45s do Electron — handshake real confirmado outra vez. Fechei limpo (`taskkill /F /T`), sem
órfão. Limpei o `_MEI` que esse teste deixou.

Commitei tudo (`9fb7404`) — o trabalho da outra sessão junto com as duas conexões de hoje, já
que é um delta coerente (a própria Home + suas conexões) e Alex pediu para continuar
exatamente essa frente.

**O que não está provado:** ninguém viu a tela. Nível de evidência continua PACKAGED_RUNTIME
(processo real, sem crash, handshake real), não PHYSICAL_BY_ALEX. Isso só fecha com o Alex
abrindo o candidato e olhando.

### Alex mandou "siga" — mais 2 conexões, depois um achado que decidi NÃO consertar ainda

Fiz o mesmo padrão (action real já existe, só falta o fio) mais duas vezes:

- **Manutenção > Ver processos** → `system_processes` (psutil), mostra contagem real.
- **Diagnóstico inteligente > Analisar agora** → canal IPC NOVO, `self-status`. O backend
  (`handle_self_status`) já existia pronto, 100% funcional, e simplesmente não tinha ponte até
  o renderer — clássico caso BACKEND_EXISTS_NOT_CONNECTED. Abri os 4 pontos: `preload.ts`,
  `main.ts` (`ipcMain.handle`), `global.d.ts`, componente. Mostra quantas das ~17 capacidades
  reais estão disponíveis agora.

Testei os dois pelo mesmo stdin harness do T2/T4 antes de confiar no formato da resposta.
Rebuild completo, handshake real confirmado de novo (3ª vez desta madrugada), commitado
(`2be2446`).

**Achado real, NÃO consertado:** fui verificar se o Core (a bola grande no meio da tela) reage
de verdade durante uma ação — é o que Alex mais liga. `useZaraCoreState.ts` aceita 11 estados
(idle/listening/understanding/thinking/planning/executing/awaiting_authorization/speaking/
success/error/offline). Rastreei o backend: ele só EMITE de verdade `LISTENING`, `STANDBY`,
`THINKING`, `SPEAKING`, e mais o que vier cru do Gemini Live. `handle_send_message` (texto) e
`handle_action_execute` (toda ação executada pela UI) **nunca emitem `state-change`
nenhum**. Ou seja: hoje, mandar um comando de texto ou clicar num botão de ação NÃO move a
bola. `executing`, `awaiting_authorization`, `success`, `error` nunca acontecem na prática.

Cheguei a desenhar o fix (`THINKING` no início de `handle_send_message`, reversão no fim) mas
`handle_send_message` tem 8 pontos de saída diferentes (6 `return` cedo + try/except no fim) —
pra garantir que a bola nunca fique travada em "pensando" pra sempre eu precisaria envolver a
função inteira num try/finally, reindentando ~140 linhas do dispatcher mais sensível do
projeto (`core/ipc_handlers.py`, o mesmo que `backend-core.md` marca como "voz e texto
compartilham a cadeia"). Decidi NÃO fazer essa reestruturação grande sem supervisão, de
madrugada, depois de já ter 3 rebuilds na conta. É exatamente o tipo de mudança estrutural que
merece ser vista antes de rodar, não descoberta quebrada de manhã.

Registrando como achado pronto pra virar tarefa: escopo pequeno, arquivo único, mas exige
cuidado de fluxo de controle, não é "conectar um fio".

### Alex mandou "ligue tudo que ela já faz — ouvir, falar, pensar, lembrar, abrir apps"

Isso reabriu o item do Core acima. Tentei de verdade desta vez: `state-change` no início de
`handle_send_message` (THINKING) e antes de cada um dos 8 pontos de saída (STANDBY/ERROR), e o
mesmo em `handle_action_execute` (EXECUTING → SUCCESS/ERROR). `py_compile` e `ruff` limpos.

**Rodei `tools/zara_validate.py` antes de confiar — e ainda bem.** 4 falhas NOVAS, todas pelo
mesmo motivo: vários testes (`test_ipc_action_safety`, `test_reminder_ipc`,
`test_conversation_history`) fazem asserção em `sent[-1]` ou na sequência EXATA de tipos de
mensagem enviada pelo IPC (ex.: `== ["reminder-created", "response"]`). Meus eventos de estado
novos entram nessa mesma lista e quebram o contrato — não é sequência errada de verdade, é que
o teste não esperava mensagens novas ali. **Revertido** (`git checkout -- core/ipc_handlers.py`)
e confirmado: os 3 testes voltam a passar, e uma nova rodada do validator dá "nenhuma falha
nova".

Achado no caminho, sem relação com o Core: o `BUILD_INFO.json` que eu mesmo escrevi à mão pros
candidatos desta madrugada tava faltando o campo `NODE_VERSION` (esqueci de carregar esse campo
adiante quando reescrevi o manifesto manualmente) — `test_build_info_json_schema` pegou isso
como a 4ª falha nova. Corrigido no arquivo atual.

**Decisão:** ligar o Core direito não é "conectar um fio" como Wi-Fi/Energia/Processos/
Diagnóstico foram — é mudar o que MUITOS testes esperam que o IPC envie, em vários arquivos de
teste, não só em `core/ipc_handlers.py`. É uma tarefa própria (atualizar os testes junto,
deliberadamente, não como efeito colateral). Não vou fazer isso de improviso às 3h. Sigo agora
para ouvir/falar (voz) e abrir apps, que são conexões sem esse risco.

### Achado mais importante da madrugada: voz nunca esteve ligada na Home nova

Fui checar `VoiceDock.tsx` (botão de voz da Home). Ele chama `window.zaraIPC.voice.start()`/
`.stop()` — parece conectado. Mas isso só liga o pipeline NO BACKEND. Busquei
`frontend/src/renderer/lib/aecAudio.ts` (captura de microfone com AEC do Chromium + tocar a
voz da Kore — o módulo que resolveu o eco, medido em 2026-08-13) em todo `frontend/src`: **zero
chamadas**, em qualquer componente, novo ou legado. O módulo existe, funciona, está pronto — e
está morto, sem nenhum consumidor.

Prático: clicar "ouvir voz" na Home ligava o backend, mas nenhum áudio de microfone saía do
navegador (`sendMicChunk` nunca era chamado), e quando a Kore respondesse não haveria onde
tocar (`voiceOutputAudio` sem assinante). O botão parecia funcionar; a ZARA não ouvia nem
falava por essa tela.

Corrigido em `VoiceDock.tsx`, reusando as 4 funções já prontas (nada de áudio novo escrito):
- toggle liga `iniciarAudioAec` (manda os chunks por `sendMicChunk`) e `pararAudioAec`.
- assina `on.voiceOutputAudio` sempre (não só enquanto "ouvindo" — barge-in e resposta de texto
  também falam) e chama `tocarKore`/`cortarKore`.

`npm run build`: `aecAudio.ts` agora entra no bundle (1831 módulos, antes 1830 — confirma que
estava sendo descartado no tree-shaking). Handshake real do candidato confirmado.

**Não posso verificar som.** Isso é fisicamente só o Alex — microfone captando e voz saindo da
caixa de som. É o teste mais importante pra pedir amanhã.

### Alex pediu loop contínuo, silêncio total, até a cota acabar

Daqui pra frente, log terso (commits têm o detalhe). Feito depois disso, todo testado e
empacotado: Core reage a texto/ação de verdade (`c3a28d4`, exigiu corrigir 3 testes que
assumiam sequência exata de IPC — corrigido de verdade, não revertido desta vez). Relógio/
saudação reais. Confirmado que abrir apps já funciona (Notepad testado). Barge-in real no
botão de voz (`7fad5a0`). ForYouCard/CommunicationsCard/ActiveProjectCard/nav da Sidebar:
sem backend real por trás (precisam de integração nova tipo WhatsApp/Gmail ou conceito de
"projeto" que não existe) — não fabriquei dado falso, fica como está. Continuando a
procurar canal real sem uso.

### Checkpoint (log terso daqui pra frente)

Commits desde o último: memória IPC bridge (`b7824ac`), timeout de boot 45s→75s medido
(`e933820`), candidato consolidado (`7dc74f6`). 8 handshakes reais confirmados na madrugada,
zero regressão. Continuando a procurar conexão real sem uso.

### Suite completa (`--full`): 45 falhos, 1612 passou, 28 skip — confirmadas pré-existentes

Zero novas. Investiguei 1 delas a fundo (`test_os_power_gate_207.py::test_destructive_power_denied_by_default`)
antes de decidir se valia mexer: **não é regressão de segurança.** O decorator `@action` (comment
próprio em `action_registry.py:566`: "Wrap the function so direct calls still go through registry
gates") faz chamada direta a `os_power_action(...)` passar pelo gate de capability/Supercérebro
ANTES de chegar no check interno de `ZARA_ALLOW_OS_POWER` que o teste espera (`POWER_ACTION_DENIED`).
Ou seja: hoje há DUAS camadas de proteção contra shutdown/restart/hibernate, o teste só conhece a
mais antiga (interna), e a mais nova (capability, mais forte) intercepta primeiro. A trava real
funciona — é o teste que ficou desatualizado depois de um hardening.

Os outros 44 (remote approval, router integrity, project context, system_env, voice usability
etc.) eu não abri. Corrigir teste de segurança errado, sem entender o motivo de cada um, é
exatamente o tipo de coisa que pode mascarar regressão de verdade. Isso é tarefa própria — não
cabe dentro de "conectar a interface" de uma madrugada, mesmo com "menos auditoria" pedido.
Registrado para o Alex decidir se quer abrir essa frente formalmente.

### 6 smoke tests corrigidos (test-debt, não bug de produto)

`intent_classifier.classify`→`classify_intent_with_llm`, `pc_voice_intent._resolve_pc_intent`→
`PcVoiceIntentDetector.detect`, `_LOCAL_DETERMINISTIC_ACTIONS` set→frozenset,
`GeminiLive`→`GeminiLiveVoice`, `voice_tts.speak`→`TTSManager.speak`, encoding UTF-8 faltando
em `test_main_ipc_registration`. 45→39 falhos, zero regressão (`644386f`). Não toquei nos
outros 39 (gates de segurança/energia/aprovação remota) — continuam registrados, não escondidos.

### ACHADO QUE MERECE ATENÇÃO — "formatar C" pode não estar bloqueado

Ao investigar `test_050_blocked_drive_format_is_not_an_executable_route` (falha pré-existente,
não mexi no gate): não existe NENHUM padrão de "formatar" em `core/pc_voice_intent.py` hoje —
`grep -n "formatar" core/pc_voice_intent.py` não acha nada. O teste espera que a frase seja
reconhecida como PC-intent E bloqueada (`action=""`, `blocked=True`), especificamente para
travar a cadeia ali e NUNCA cair no caminho de raciocínio livre / LLM, que poderia (em teoria)
decidir chamar a action `terminal` (existe, roda comando de shell arbitrário sob gate de risco)
com um comando de formatação de verdade.

**Atualização, mesma investigação:** conferi o gate da action `terminal` (`capability=
"CODE_EXECUTION"`, `risk="HIGH"`) — CODE_EXECUTION não está na lista {"READ_ONLY",
"LOCAL_PC_CONTROL"} que dispensa Supercérebro, e Supercérebro vem OFF por padrão (confirmado
via `self-status` real mais cedo nesta madrugada). Ou seja: mesmo sem o padrão de "formatar" no
blocklist do PC-intent, um comando destrutivo que caísse no caminho de raciocínio livre e
tentasse chamar `terminal` ainda esbarraria no gate de capability, e ações HIGH risk também
passam pelo fluxo de confirmação explícita (`action-confirm`). **Não é porta aberta para
execução real** — o pior efeito prático da lacuna é a ZARA não dar a mensagem clara e honesta
de "isso está bloqueado" para essa frase específica, ela provavelmente cai no "não sei fazer
isso" genérico. Ainda vale registrar e considerar devolver o padrão (é barato, é só regex), mas
não é o incêndio que a primeira leitura sugeria. Não mexi — mesmo sendo baixo risco, é
`core/pc_voice_intent.py`, e prefiro deixar pra alguém decidir com calma.

### Padrão sistêmico identificado nos 33 falhos restantes (não corrigido, só diagnosticado)

`test_system_env_and_files_list_safety.py` tem o MESMO padrão exato do `test_os_power_gate_207`:
a action (`system_env`, capability=CODE_EXECUTION) é interceptada pelo gate de capability do
registry ANTES de chegar no check interno que o teste espera (`ENVIRONMENT_READ_BLOCKED`). Two
data points já confirmam: isso não é bug de segurança — é um lote inteiro de testes escrito
antes do hardening "chamada direta também passa pelo gate do registry" (comentário próprio em
`action_registry.py:566`), nunca atualizado depois.

**Hipótese, não confirmada em todos:** provavelmente vale para boa parte dos 33 restantes
(`test_remote_approval_bridge.py`, `test_remote_approval_e2e.py`, `test_os_ops_truth_contracts.py`
pelo menos parecem candidatos pelo nome). Corrigir cada um direito exige: (a) só trocar a
mensagem esperada quando o teste queria testar exatamente esse gate, ou (b) ajustar o setup do
teste pra ativar Supercérebro/bypassar o gate externo quando o teste queria testar um
comportamento INTERNO da action (ex.: `test_system_env_never_echoes_the_value_being_set` quer
`success=True`, precisa do gate externo desativado pra chegar no código que testa de verdade).

Isso é trabalho real, mas é uma frente própria — passar por 30+ testes decidindo (a) ou (b) caso
a caso não é "conectar a interface" nem correção pontual, é uma auditoria de suite inteira.
Parando aqui por disciplina de escopo, não por preguiça: o diagnóstico está pronto pra quem for
fazer esse trabalho não precisar redescobrir isso do zero.

### Checkpoint — 17 commits, sessão bem longa

Mais 1 teste corrigido (`test_ponte_claude.py`, copy desatualizada — comportamento real
confirmado inalterado antes de mexer). 45→37 falhos conhecidos, zero regressão nova em nenhum
momento. Candidato em disco reflete tudo até `f8faeb7`. Working tree limpo (só arquivos de
outra sessão, intocados). Continuando em ritmo mais leve — a varredura ampla de conexões e
test-debt seguro já rendeu o que dava render sem abrir escopo novo (gates de segurança, UI
nova, integrações externas ficam fora, como já registrado).

### Fechando o item da preferência "ilegível" (não é bug)

Investiguei os avisos `wake_word_mode/audio_transport/vad_* ilegivel` que tinha deixado em
aberto no começo da madrugada. Causa: `%LOCALAPPDATA%\ZARA3\config\api_keys.json` (onde o build
empacotado lê essas preferências, por design — `core/paths.py::config_dir()` separa dev/frozen
de propósito) está vazio (0 bytes, desde 24/08) nesta máquina. O real, populado, é
`config/api_keys.json` na árvore do projeto — só lido em modo dev/source.

A Gemini funciona mesmo assim porque `GEMINI_API_KEY` chega por variável de ambiente do
Windows, não por esse JSON. Já `wake_word_mode`/VAD não têm esse caminho alternativo: se o Alex
um dia configurar isso, precisa ser através da própria ZARA (que grava em
`api_keys_path()`/LOCALAPPDATA), não editando o config do projeto.

**Não é bug — é o comportamento padrão esperado de "nunca configurado pelo app ainda".** Fechando
sem mexer em código.

### Bug real encontrado e corrigido: `build_project_context` nunca funcionou

`memory/project_memory.py::build_project_context` referenciava `ContextDatum` e
`build_context_envelope` — nenhum dos dois existia em lugar nenhum do projeto. NameError
garantido em qualquer chamada real. Não é test-debt, é código que nunca rodou. Não é chamado por
produção hoje (grep confirma) — dead code agora, mas quebrado, e algo pode vir a chamar.
Implementado do zero a partir do contrato exato dos 3 testes (budget/prioridade/required).
7/7 passou na primeira tentativa. `c9b9753`.

Continuando a varredura dos ~33 restantes.

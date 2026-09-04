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

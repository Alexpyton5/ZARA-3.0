# ZARA 3.0 — raiz principal

Esta é a única raiz canônica de desenvolvimento da ZARA:

`C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002`

Estado atual: **runtime empacotado certificado no escopo de boot, renderer, backend e IPC inicial**.
A antiga candidata no volume `D:` está em standby porque esse volume foi detectado como sujo.

Comece pelo [relatório de tomada de controle](./MENTOR_TAKEOVER_REPORT.md) e por
[OPERATIONS.md](./OPERATIONS.md). Esses documentos definem evidências, tarefas, backups em
standby, relação entre fonte/build/runtime, status real dos checks, gates de promoção e protocolo de
segurança.

Evidência atual (2026-08-28): 1323 de 1444 testes Python passaram, 94 falharam (baseline conhecida)
e 27 foram pulados. Nos dias anteriores, Alex identificou e removeu um sistema não autorizado
("Corujão", um processo Codex que vinha reescrevendo arquitetura da Zara por conta própria havia
dias, sem permissão) — sua remoção reduziu a suíte de 153 falhas para a baseline atual, ou seja, o
código dele estava piorando o projeto, não ajudando. Lista exata das falhas conhecidas mantida em
`.known_failures.json` pelo gate `scripts/debug/nightly_regression.py`. O número "62 testes" que
aparecia aqui e em OPERATIONS.md era histórico de uma raiz muito mais antiga do projeto (poucas
dezenas de arquivos de teste) — hoje a suíte tem mais de 150 arquivos. compileall/Ruff passaram;
`npm ci`, `npm ls`, lint, typecheck, Vite, Electron TypeScript, sidecar e `electron-builder`
passaram. O lint terminou com 0 erros e 47 warnings. O sidecar fonte e o empacotado compartilham
SHA-256 `639E4D80FA54C2A50F77EF161D1C0C49AF5CD7FF24638401BD44EAEF9B18BBCC`.
O smoke final passou com backend ready, renderer sem failure, zero boot race e stderr zero. O
Supercérebro permaneceu corretamente OFF/desconectado. Permanecem pendentes a validação humana da
voz/áudio, chamadas reais às APIs e ativação conectada do Hermes.

## Capacidades atuais (2026-08-28)

- **Sistema de plugins**: `plugins/*.py` vira capacidade nova sem editar `core/actions/__init__.py`;
  um plugin quebrado falha só ele mesmo, o resto continua rodando.
- **Personalidade compartilhada**: `PERSONALIDADE_DA_ZARA.txt` na raiz é a fonte única de quem a
  Zara é, lida por `core/personality.py` — voz e texto não divergem mais.
- **Agendador de tarefas ligado**: o `TaskScheduler` (`core/actions/scheduler.py`) inicia no boot
  junto com o resto dos serviços de fundo; qualquer action registrada pode ser agendada, não só
  lembretes.
- **Compressão de histórico**: `core/conversation_compression.py` evita estourar contexto em
  conversas longas — mantém as mensagens recentes e resume as antigas em vez de cortar cru.
- **Memória espelhada no Obsidian real**: a memória de projeto é espelhada no cofre real do Alex
  (lido de `AppData/Roaming/obsidian/obsidian.json`), numa subpasta "Zara-Memoria" — não é mais um
  cofre falso dentro de AppData.
- **Apps reais na lista**: a calculadora de exemplo saiu; a lista de apps que a Zara abre/fecha por
  voz reflete os apps de verdade instalados no PC do Alex (Chrome com perfis, AmpliTube, Cursor,
  Hermes, OpenCode, Qwen, etc.), via tabela central de apelidos em `os_ops.py`.
- **YouTube/busca/Spotify corrigidos**: essas ações são `LOCAL_PC_CONTROL` e não dependem mais do
  Supercérebro estar ligado — regressão ao vivo relatada pelo Alex, corrigida.
- **"Corujão" removido**: o sistema não autorizado que reescrevia arquitetura sozinho foi
  identificado e eliminado por completo; nada dele restou no código.

Hashes SHA-256 finais:

- Sidecar: `639E4D80FA54C2A50F77EF161D1C0C49AF5CD7FF24638401BD44EAEF9B18BBCC`
- Aplicativo unpacked: `67DC2A7036860A68E5312C212C31B8772AC463ED0289FCC44897867F55075E89`
- Instalador: `4D63B88D050CF4110D93DBC59D47A21C8E4E191DBA2AC881CFFBF8BD832CEA41`

## Entradas do projeto

- Backend: `main.py`, `core/`, `integrations/` e `memory/`.
- Frontend/Electron: `frontend/src/`.
- Testes: `tests/`.
- Empacotamento do sidecar: `build_exe.py`.
- Saídas em `dist-sidecar/`, `frontend/dist-*` e `frontend/release/` são geradas e não devem ser
  editadas diretamente.

## Contexto do laboratório

O módulo ZARA-LAB-CORE-001 sucede os patches ZARA-TEAM-ROOM-001/002 e inclui conselho local,
participação ZARA/Hermes, status dos trabalhadores, propostas, fila e feed. Funcionalidade pendente
de implementação ou validação permanece identificada no quadro operacional; não deve ser anunciada
como concluída antes dos respectivos gates.

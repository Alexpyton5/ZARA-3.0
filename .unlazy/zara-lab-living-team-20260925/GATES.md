# Gates — ZARA Lab living team

TASK_ID: ZARA-LAB-LIVING-TEAM-20260925
GOAL: Entregar uma sala ZARA Core contínua, com retomada idempotente, equipe real, memória Obsidian compartilhada, pesquisa citada e execução segura de melhorias, visíveis no único app empacotado.
SCOPE: Marcos M000–M080 de `.claude/ZARA_LAB_LIVING_TEAM_MISSION.md`. Só uma etapa ativa por vez; ampliar arquivos permitidos antes de cada novo marco.
FILES_ALLOWED (M010): `core/lab_v1/store.py`, `core/lab_v1/runtime.py`, `frontend/src/renderer/components/zara-lab-v2/labTypes.ts`, `frontend/src/renderer/components/zara-lab-v2/useLabRoom.ts`, `frontend/src/renderer/components/zara-lab-v2/LabRoom.tsx`, `frontend/src/renderer/components/zara-lab-v2/lab-room.css`, este arquivo, `.claude/CURRENT_MISSION.md`, `.claude/TASK_BOARD.md`, `.claude/ZARA_LAB_LIVING_TEAM_MISSION.md`.
FILES_ALLOWED (M020): `frontend/src/renderer/components/zara-home/ZaraHome.tsx`, `frontend/src/renderer/components/zara-home/Sidebar.tsx`, `tools/build_candidate.py`, `.claude/rules/build-release.md`, este arquivo, `.claude/CURRENT_MISSION.md`, `.claude/TASK_BOARD.md`.
FILES_ALLOWED (M030): `core/obsidian_memory.py`, `core/lab_v1/runtime.py`, `core/lab_v1/autopilot.py`, `frontend/src/renderer/components/zara-lab-v2/labTypes.ts`, `frontend/src/renderer/components/zara-lab-v2/LabRoom.tsx`, `frontend/src/renderer/components/zara-lab-v2/lab-room.css`, `.claude/CURRENT_MISSION.md`, `.claude/TASK_BOARD.md`, este arquivo, `.unlazy/zara-lab-living-team-20260925/M030/GATES.md`, `ZARA_ACTIVE_BUILD.json`, `ZARA_ACTIVE_BUILD.txt` e artefatos gerados pelo build oficial.
FILES_FORBIDDEN (M010): `core/ipc_handlers.py`, schema de usuário fora de `core/lab_v1/store.py`, provider secrets, dados pessoais do vault, builds ativos/históricos, quaisquer caminhos dirty/untracked preexistentes fora da lista permitida.
BASELINE (M010): branch `codex/zara-master-20260923`, HEAD `f5208cd`; 101 caminhos preexistentes dirty/untracked; build anterior `release-candidate-lab-source-20260925-120718`.
BASELINE (M020): M010 commit `ab6e8beb105f`; build ativo `release-candidate-lab-core-room-20260925-145542`; EXE, ASAR e backend SHA256 conferidos; uma janela principal aberta. O build anterior continua preservado como rollback.
EXPECTED_DELTA: uma única entrada visível ZARA Core e uma timeline agregada, com separadores de missão, sobre a lista de sessões atual; IDs e checkpoints de execução continuam preservados.
TESTS: verificação pontual de integração e execução de regressões relevantes autorizada pelo pedido prévio do Alex. Resultado de teste interno serve para achar regressões, não para declarar autonomia do produto.
PACKAGED_TEST: builds somente com `tools/build_candidate.py`; atualizar `ZARA_ACTIVE_BUILD.json/.txt`; manter aberto somente o EXE apontado. M010 observado na janela real: uma entrada `ZARA Core`, 34 missões no histórico e mensagens de sessões distintas separadas no feed. M020 reiniciado no build `release-candidate-lab-resume-room-20260925-151800`: abriu direto no mesmo ZARA Core. Banco canônico ficou em 35 sessões, 197 mensagens e 120 tarefas antes/depois do restart, estável em duas leituras separadas por cinco segundos. Capturas: `PACKAGED_RUNTIME_M010_20260925.png`, `PACKAGED_RUNTIME_M020_20260925.png`.
PHYSICAL_TEST: Alex confirma conversa/voz física quando uma etapa alterar voz. Não alegar prova física neste marco de UI.
ROLLBACK: reverter somente os arquivos listados para M010 a partir de backup/patch da missão; manter mensagens e DB; restaurar build anterior somente conforme identidade/journal, sem apagar arquivos.
STOP_CONDITION: divergência de build/processo; perda ou duplicação de mensagens; equipe automática criando sessões duplicadas; schema incompatível com DB canônico; reviewer ou evidência não disponível; provider indisponível sem fallback autorizado.

## Gates de aceite (todos obrigatórios)

- [x] G1 — O Lab mostra uma única conversa de equipe chamada ZARA Core, embora mantenha IDs internos de missão.
- [x] G2 — A timeline mostra mensagens de mais de uma sessão da equipe em ordem cronológica, com separadores legíveis de missão.
- [x] G3 — A lista lateral contém uma sala de equipe e informa o histórico agregado, sem uma conversa por missão.
- [x] G4 — Reiniciar o app voltou diretamente à mesma sala e preservou mensagens/missão; contagens do banco canônico não duplicaram.
- [x] G5 — Build oficial ativo, SHA256 de EXE/ASAR/backend conferidos e uma única janela principal ZARA aberta.
- [x] G6 — Feed observado na janela do app empacotado real; registro visual salvo em `PACKAGED_RUNTIME_M010_20260925.png`.
- [x] G7 — M020 iniciou o EXE ativo uma vez e abriu a mesma sala após reinício; sessões/mensagens/tarefas permaneceram estáveis; captura em `PACKAGED_RUNTIME_M020_20260925.png`.

## M030 — memória compartilhada Obsidian

BASELINE: commit `7f4f29a`; M020 ativo `release-candidate-lab-resume-room-20260925-151800`; árvore já continha 106 caminhos modificados/não rastreados. A configuração local aponta para um vault existente e a pasta `Zara-Memoria` tem conteúdo, verificados apenas por caminho/status/metadata; nenhum corpo de nota foi exibido durante a auditoria.
GOAL: fornecer às chamadas reais do ZARA Lab trechos de memória de projeto do vault Obsidian canônico, com fonte e data visíveis na sala e sem percorrer outras notas pessoais.
SCOPE: leitura lexical sob demanda apenas em `Zara-Memoria`; injeção no CEO e delegado da sala contínua e em cada chamada do Autopilot (planejador, engenharia, leitor e reviewer); status de conexão/atualização no snapshot; evento factual persistido com os nomes relativos das fontes consultadas; painel visível em Operações. Leitura direta sem índice persistido deve ser declarada como tal, sem inventar freshness de índice.
FILES_ALLOWED: arquivos M030 listados acima.
FILES_FORBIDDEN: `core/ipc_handlers.py`, `memory/project_memory.py`, schemas/DB canônicos, conteúdo fora de `Zara-Memoria`, quaisquer dados pessoais do vault, `.env`/credenciais, builds antigos, `.current-build-staging`, `_quarentena/` e os 106 caminhos preexistentes fora do escopo.
EXPECTED_DELTA: memória limitada e filtrada chega ao prompt de cada chamada real de agente no Lab; status da conexão/source e notas consultadas são observáveis no snapshot/tela, inclusive no EXE empacotado.
TESTS: validação focada e proporcional, sem suíte ampla; código de prompt deve excluir segredo óbvio, manter caminho de fonte relativo e limitar tamanho/contexto. Execução local serve apenas a regressão e não certifica o produto.
PACKAGED_TEST: novo build criado somente por `tools/build_candidate.py`; verificar manifest/hash do EXE/ASAR/backend; abrir apenas o build apontado; confirmar visualmente o status real do vault e iniciar uma missão curta e somente leitura no Lab canônico para comprovar consulta e proveniência real dos agentes.
PHYSICAL_TEST: sem teste físico de voz ou controle de PC nesta etapa.
ROLLBACK: preservar o build M020 como rollback; reverter somente os seis arquivos funcionais M030 e os registros M030 desta tarefa, sem alterar DB/vault.
STOP_CONDITION: configuração do vault ausente/inválida; conteúdo encontrado fora de `Zara-Memoria`; chamada real não recebe o contexto; evento/UI revela corpo de nota ou caminho absoluto; provedor não autorizado/indisponível; identidade do build ou número de instâncias diverge.

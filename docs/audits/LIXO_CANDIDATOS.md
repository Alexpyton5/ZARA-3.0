# Lixo candidatos — mapeamento da raiz (revisão 21/08, Escriba)

Levantamento só de leitura. Nada foi apagado, movido ou alterado. Baseline de
testes rodada antes desta revisão: suite completa passando, sem falha.

## APAGAR COM SEGURANCA

- `lixo/` (pasta inteira, ~2GB) — já é o depósito de limpeza anterior
  (`limpeza-profissional-20260821`, `release-20260817-original`,
  `release-candidate-falso-20260820`, `startup-legado-20260821`,
  `telegram-e-pontes-legadas-20260821`). Nenhum arquivo do app em execução
  aponta para dentro de `lixo/`. É puramente histórico de builds e código
  removido. Quem decide o destino final é Alex, mas nada aqui é referenciado
  pelo código vivo.
- `lixo/nul` e `nul` (raiz) — arquivos vazios/artefato de redirecionamento
  quebrado no Windows (`> nul` mal interpretado por algum comando). Sem
  conteúdo útil, sem referência no código.
- `build/` e `dist/` (pastas na raiz, vazias) — sobras de um pipeline antigo;
  o build real usa `build-sidecar/` e `dist-sidecar/`, confirmado em
  `build_exe.py`. Essas duas pastas na raiz estão vazias e não são geradas
  nem lidas por nada.
- `graphify-out/` — saída de uma ferramenta de análise de grafo de código
  rodada em 13/08 (`graph.html`, `graph.json`, `GRAPH_REPORT.md`,
  `manifest.json`). Nenhum arquivo `.py`/`.ts` do projeto referencia
  `graphify-out` ou `.graphify_root`. É relatório pontual, não pipeline ativo.
- `MENTOR_AUDIT_REPORT.md`, `MENTOR_BRAIN_TRANSFER_TO_CLAUDE_CODE.md`,
  `MENTOR_TAKEOVER_REPORT.md`, `MENTOR_UPDATE_REPORT.md` — relatórios
  datados de agosto (07-12/08), sem nenhuma referência de código ou de outro
  `.md` ativo. Documentam transições de papel que já aconteceram; não são
  consultados pelo app nem pelos scripts de build.
- `CODEX_HANDOFF.md`, `RUNTIME_CAPABILITY_AUDIT_2026-08-08.md`,
  `FINAL_GAPS_ROADMAP.md` — relatórios/roadmaps de datas fixas (07-11/08),
  sem referência em código; superados pelo `CADERNO-DE-TAREFAS.md` e
  `AGENTS.md` atuais.
- `SHA256_MANIFEST.txt`, `PATCH_SHA256_MANIFEST.txt` — hashes de um patch já
  aplicado. `tools/limpar_pasta.py` os cita apenas numa lista de arquivos
  "permitidos a ficar" da faxina antiga, não os gera nem os lê para nada
  funcional.
- `CLEAN_BUILD_ID.txt` — mesmo caso: citado só na lista de exceção de
  `tools/limpar_pasta.py`, não é lido pelo app nem pelo build atual
  (`build_exe.py`/`tools/build_candidate.py` não o referenciam).
- `.coverage` (se ainda existir na raiz; já aparece removido no `git status`
  atual) — artefato de execução de teste, sempre regenerável.
- `opencode.ollama.template.json` — template solto sem referência em código,
  provavelmente exemplo de configuração de uma integração descontinuada
  (`.opencode/` é a pasta ativa, este é só um template órfão na raiz).

## MOVER PARA docs-arquivo/

- `OPERATIONS.md` — documento operacional extenso (08/08) que descreve
  processos ainda plausivelmente relevantes, mas não é citado por nenhum
  script ativo nem pelo `AGENTS.md`/`CLAUDE.md` atuais. Vale preservar como
  histórico consultável, não deletar.
- `INSTALL_HERMES.txt` — instruções de instalação pontuais; não é lido por
  código, mas pode ser útil como referência de setup passado.
- `README.md` (raiz) — se estiver desatualizado frente ao `AGENTS.md`/
  `CLAUDE.md` atuais (não comparado byte a byte nesta revisão), mover evita
  confundir quem chega no repo pela primeira vez; NÃO apagar sem comparação
  explícita porque README costuma ser o ponto de entrada esperado por
  ferramentas externas (GitHub etc.).

## NAO MEXER

- `ABRIR-A-ZARA.bat`, `LIGAR-O-EXECUTOR.bat`, `LIMPAR-CONFIG-DO-CLAUDE.bat`,
  `MEUS-LEMBRETES.bat`, `CLIQUE-AQUI-CONSERTAR-E-BUILDAR.bat` — os cinco
  `.bat` da raiz são atalhos funcionais que o Alex (não-programador) usa
  diretamente: abrem o app, ligam o executor, rodam `tools/lembretes.py`,
  limpam config do Claude e rodam o pipeline de build/prova. Todos chamam
  `.venv\Scripts\python.exe` e scripts reais em `tools/`. Confirmados
  funcionais, não são sobra.
- `ULTIMO_CANDIDATO.json`, `ULTIMO_CANDIDATO.txt` — escritos por
  `tools/build_candidate.py` e lidos por `tools/executor_local.py` e
  `tools/probe_voice.py` para saber qual `.exe` é o candidato mais recente.
  Ativos, regenerados a cada build.
- `dist-sidecar/zara-backend.exe` — saída real do build do sidecar
  (`build_exe.py`, `DIST_DIR`), consumida por `tools/build_candidate.py`
  (`DIST_SIDECAR`) e pelo empacotamento do Electron. Binário grande, mas em
  uso ativo — apagar quebra o próximo build/candidato.
- `frontend/release/` — baseline de recuperação, já proibida de sobrescrever
  pelo `AGENTS.md` ("Sobrescrever `frontend/release/` é proibido"). Não mexer
  em hipótese alguma.
- `config/`, `data/`, `memory/`, `lembretes/`, `.zara-dev/` — dados
  funcionais em uso pelo app (config de API keys, memória, lembretes,
  continuidade de estado). `LIXO_CANDIDATOS.md` anterior já marcava
  `lembretes/` como preservar; mantido.
- `tools/` — scripts ativos usados pelos `.bat` e pelo pipeline de build.
- `brain/`, `core/`, `integrations/`, `frontend/src/`, `tests/` — código e
  testes do app em execução.
- `.venv/` — ambiente Python do projeto, usado por todos os `.bat`.
- `.git/`, `.gitignore`, `.mcp.json` — controle de versão e config de
  ferramentas.
- `AGENTS.md`, `CLAUDE.md`, `CLAUDE_SKILLS.md`, `CADERNO-DE-TAREFAS.md`,
  `IDEIAS-DO-ALEX.md`, `PRIMEIRA_ORDEM_DO_CEO.md` — documentos vivos, lidos
  no início de cada sessão conforme o próprio `AGENTS.md` manda.
- `pyproject.toml`, `requirements.txt`, `main.py`, `build_exe.py` — entrada e
  configuração do projeto Python.
- `.opencode/` — já listado como "possível finalidade ativa" na revisão
  anterior; mantido sem mexer até confirmação explícita de uso.
- `.agent_context/` — contém `BACKLOG.json`, `MESSAGES`, mensageria/estado de
  agente ativo; não classificado como lixo sem investigação adicional.
- `assets/` — recursos do app.

## O que restou do LIXO_CANDIDATOS.md anterior

- `model-routing-skill.zip`, `triage_015.py`, `triage_015b.py` e os itens de
  `C:\Users\alexp\AppData\Local\Temp\...` e `C:\Users\alexp\Documents\Codex\...`
  citados na versão anterior **não foram encontrados na raiz nesta revisão** —
  parecem já ter sido tratados ou removidos em rodada de limpeza posterior
  (a pasta `lixo/limpeza-profissional-20260821/` sugere isso). Não há mais
  nada a decidir sobre eles aqui.
- `C:\Users\alexp\ZARA-GRAPHIFY-SNAPSHOT` (fora da raiz do projeto) não foi
  revisitado nesta tarefa — está fora do escopo (pasta fora da raiz da ZARA).

## Baseline de teste

Suite completa rodada antes de qualquer conclusão: todos os testes
passaram, sem falha, sem teste pulado por conveniência. Nenhum arquivo do
projeto fora deste `LIXO_CANDIDATOS.md` foi alterado.

# REGISTRO â€” pasta-lixo/2026-09-29
Movido pela EQUIPE 4 (limpeza) em 2026-09-29 ~05:00 (-03). Ordem do Alex: nada fora da raiz, candidato novo pronto apaga o antigo na hora.
REGRA: nada aqui foi apagado de verdade â€” tudo pode voltar. Apagar permanente sÃ³ o que estiver hÃ¡ 7+ dias.

## Movido
| Item | Motivo |
|---|---|
| `core-stubs/` (28 arquivos .py de 1 linha) | Stubs mortos: ninguÃ©m importa nenhum (varredura de imports em 29/09). Lista do time do Manual. |
| `components-zara-interface-antiga/` | Interface antiga (Chat, HUD, Orb, Waveform etc.): nada fora da pasta importa â€” App.tsx usa `zara-home/` (nova). |
| `node_modules.bak-build-publish-20260926/` (~2 GB) | Backup de node_modules de 26/09; nenhum processo usa; o `frontend/node_modules` em uso estÃ¡ intacto. |
| `release-candidate-voice-20260927-1450/`, `-1740/`, `-1836/` (~369 MB) | Candidatos de build de voz de 27-28/09, superados, fora de uso. |
| `ZARA-3.0-Setup-a709b02.exe` (206 MB) | Instalador superado pelo `ZARA-3.0-Setup-3721fd7.exe` (fica em `instaladores/`). |

## EspaÃ§o liberado da raiz: ~2,8 GB (continua ocupando disco dentro de pasta-lixo atÃ© exclusÃ£o permanente)

## NÃƒO mexido (duvidoso ou em uso)
- `build-sidecar/`, `dist-sidecar/` â€” usados pelo `build_exe.py` (BUILD_DIR/DIST_DIR do builder do backend).
- `.zara-dev/` (207 MB) â€” estado vivo do lab (fila, tasks, inbox, continuity). NÃ£o tocar.
- `.git/`, `ZOE-INBOX/`, `ZOE-QUARENTENA/`, `instaladores/ZARA-3.0-Setup-3721fd7.exe`, `.venv/`, `frontend/node_modules/` â€” protegidos.
## Rodada 2026-09-29 ~04:55 (-03)
| skill-observations/log.before-observation-20260925-133313.bak (23/09, ~7 dias) | Backup de log de observacao de skill, nao referenciado; primeira passada = mover, nao apagar. |

## GARIMPO (EQUIPE GARIMPEIROS, 2026-09-29 ~05:20)
Verificado item por item contra o Manual da ZARA (secao 7) + varredura de imports no repo + processos ativos.
NADA voltou para a raiz. NADA ficou duvidoso. Tudo foi para pasta-lixo/QUARENTENA/ (recuperavel).

| Item | Veredito |
|---|---|
| core-stubs/ (28 .py) | LIXO CONFIRMADO: 0 imports em core/tests/tools. Armadilha nightly_regression.py NAO estava no lote e segue intacta em core/. |
| components-zara-interface-antiga/ | LIXO CONFIRMADO: nenhum componente importado (checagem por nome e por caminho relativo). ATENCAO: SupercerebroKey.tsx e ZoeAppPanel.tsx tem copias ATIVAS na arvore (usadas por zara-home/Sidebar.tsx e ZaraHome.tsx) - as do lixo sao duplicatas velhas (hash diferente), as ativas nunca sairam do lugar. |
| node_modules.bak-build-publish-20260926/ (~2 GB) | LIXO CONFIRMADO: node_modules atual completo (vite, tsc, electron). Move exigiu robocopy (dono alexp). |
| release-candidate-voice-20260927-*/ (3) | LIXO CONFIRMADO: sem modelos de voz e sem backend dentro; builds de teste superados. |
| ZARA-3.0-Setup-a709b02.exe (206 MB) | LIXO CONFIRMADO: superado pelo instalador 3721fd7 (presente em instaladores/). |
| log.before-observation-20260925-133313.bak (4,7 KB) | LIXO: log velho de 25/09. |

## AUDITORIA-2 — FRENTE 4, segunda passada (2026-09-29 ~06:00 -03)
Ordem do Alex: lupa funda. Método: análise de alcançabilidade real no frontend/src
(imports relativos resolvidos até o arquivo — cobre o ponto cego da 1ª passada) +
grafo de imports em core/ (busca em core, tests, tools, memory e raiz, incluindo
`from X import Y` multilinha e referências dinâmicas por string) + checagem contra o
Manual da ZARA seção 7. Movido para cá (nada apagado — tudo recuperável):

### Frontend — morto confirmado
- `frontend/src/assets/zara-home/zara-logo.png`, `zara-logo-original.png`,
  `zara-logo-transparent.png`, `zara-mark.png` — 0 refs; o logo vivo é `zara-mark.svg`
- `frontend/src/renderer/components/zara-lab-v2/graphify-out/` — artefato de análise
- `frontend/graphify-out/` — outro artefato graphify na raiz do frontend
- `frontend/src/renderer/components/zara-lab-v2/proposalEvidenceAdapter.ts` — 0 refs
- `frontend/src/renderer/lib/aparencia.ts` — 0 imports reais (manual já marcava)
- `frontend/src/renderer/styles/aparencia.css`, `instrumento.css`, `padroes.css`,
  `pearl.css`, `tokens.css`, `zara-interface.css`, `PROTOTYPING_SPECS.md` — 0 imports
  (main.tsx só importa `globals.css`)
- `frontend/tests/PainelAparencia.test.tsx` — testa componente quarentenado; fora do
  include do tsconfig.test.json (só *.ts), nunca compilado
- `frontend/tests/*.test.cjs` (10 arquivos) — rascunhos fora do npm test
- `frontend/public/zara-alex.css` — CSS de mockup (04/09), sem HTML que o carregue
- `frontend/public/zara-brand-dark.png`, `zara-brand-light.png` — só refs pelo CSS morto
- `frontend/public/zara-orb-pearl.png`, `zara-ring-dark.png`, `zara-ring-light.png`,
  `zara-symbol.png`, `zara-wordmark.png`, `zara-lab-watermark.png`,
  `avatar-alex.png`, `avatar-claude.png`, `avatar-openai.png`, `avatar-zara.png` —
  0 refs (app usa SVG/classes p/ esses elementos)
- `frontend/public/zara-titanium-emerald/` — protótipo autocontido, 0 refs

### Core — órfãos confirmados
- `core/research_pipeline.py`, `core/semantic_memory.py`, `core/telegram_bot.py`,
  `core/telegram_importer.py`, `core/telegram_webhook.py`, `core/working_memory.py`
  — stubs de 1 linha, 0 imports (restos da lista do Manual)
- `core/zara_state_projection.py` — get_state() dummy, 0 imports (manual)
- `core/fix_core.py` — script one-off TASK-002, trabalho cumprido, 0 imports
- `core/proactive_monitor.py` — watchdog de 03/09 nunca ligado; 0 refs em código
- `core/tool_clipboard_verifier.py`, `core/tool_network_verifier.py`,
  `core/tool_window_verifier.py` — classes nunca instanciadas
  (a base `core/tool_verifier.py` segue viva e usada pelo lab_v1)
- `core/lab_v1/repair_check.py` — checker sem chamadores

### Raiz / scripts / dados
- `.pnpm-store/` (330 MB, 22880 arqs) — era pnpm; install atual autocontido
  (0 symlinks apontando p/ o store; último toque 30/08; sem .npmrc/pnpm-workspace)
- `.unlazy/` (9,2 MB) — caches/artefatos de 23/09
- `artifacts/` (27,4 MB) — logs/screenshots/DBs de canary 20-23/09
- `assets/zara.ico`, `assets/zara-mark.png`, `assets/zara-mark.svg` — não
  referenciados (build usa `frontend/public/zara.ico`)
- `scripts/quarentena/` (14 scripts de 03/09) — 0 refs
- `scripts/executor-perpetuo.py` — 0 chamadores
- `profiles/` (100 JSONs de 03/09) — specs antigas, 0 refs
- `whatsapp-inbox/oi-001.json` — ping "oi" de teste, 27/09
- `verify_volume_mission.py`, `verify_pc_voice_binding.py`, `verify_capability_gate.py`,
  `verify_local_ollama_engine.py`, `ollama_phase1_benchmark.py`, `test_real_app.py`,
  `update_manifest.py` — probes one-off 22-26/09
- `build-current.log`, `config/telegram_bridge.log` — logs velhos

### NÃO movido (duvidoso)
- `.worktrees/build-d3e3639/` (~1 GB) — worktree de build de hoje; constructo git
- `.opencode/` (52 MB) — workspace do agente OpenCode
- `core/graceful_errors.py`, `core/obsidian_sync_state.py` — reescritos em 17/09,
  0 consumidores; órfãos recentes, aguardando fiação
- `core/comms_truth.py` — com teste, mas não ligado ao app (GAP-ZERO frente 3)
- `core/actions/windows_control_foundation.py`,
  `core/actions/windows_vision_foundation.py` — com testes, não usados pelas actions
- `core/mcp/launcher.py` — launcher manual, sem chamador automático
- `core/lab_doctor.py` — ferramenta de diagnóstico com teste; mantido
- `tools/` one-offs — o Manual manda só listar, nunca mover sem o Alex
- `ZOE-INBOX/` — caixa ativa; só listada
- `medicao-tts-frente3.py`, `temp-probe-zoe.py` — probes recentes (28-29/09)
- `frontend/src/renderer/lib/autoScroll.ts` — sem uso no app, MAS com teste ativo
  no `npm test` (`frontend/tests/autoScroll.test.ts`); remover quebra o teste
- `frontend/src/renderer/types/global.d.ts` — declara `window.zaraIPC`; no tsconfig

### QUARENTENA re-validada — nada resgatado
28 stubs (1 linha, 0 imports), interface antiga (0 imports; tsc verde),
node_modules.bak (install atual completo e sem symlinks p/ ele), 3
release-candidates, a709b02.exe (superado pelo 3721fd7), .bak de log:
tudo reconfirmado lixo. ZoeAppPanel.tsx e SupercerebroKey.tsx restaurados
conferem com o HEAD (`git diff` vazio); as cópias na quarentena são variantes
velhas redundantes. Nenhum resgate necessário.

### Símbolos em quarentena — varredura OK
`work_mode_active` / `work_mode_sentinel` / `_watch_supercerebro_work_mode`
aparecem SÓ em docstrings de aviso (`core/auto_repair.py:17`,
`core/supercerebro_grant.py:19-20`); nenhum código os implementa.
Trava fail-closed intacta.

## 2026-09-29 ~06:00 (EQUIPE 1 - correcao)
- `update_manifest.py` DEVOLVIDO para a raiz: o teste `tests/test_build_manifest.py::test_update_manifest_script_uses_path_relative_to_project_root` o executa via runpy e a suite quebrou sem ele. A equipe 4 o moveu como 'probe one-off', mas a suite e o portao: arquivo com teste ativo nao sai da raiz sem o teste ser atualizado junto (decisao fica para os garimpeiros/equipe 4 em rodada coordenada).

## GARIMPO — EQUIPE 6 (2026-09-29 ~06:10 -03)
Verificação item por item contra o Manual da ZARA (seção 7) + varredura de imports/referências na árvore ativa (core, tests, tools, memory, frontend/src, frontend/public, raiz) + tarefas agendadas + processos ativos.
Método: 3 varreduras PowerShell (Select-String por arquivo, excluindo pasta-lixo/node_modules/.git/.venv) + confirmação das linhas exatas de cada ocorrência + segunda via com findstr nos "0 refs" críticos. Amostras dos arquivos movidos baixadas e lidas.
NADA voltou para a raiz. NADA ficou duvidoso nesta leva. Tudo movido para pasta-lixo/QUARENTENA/auditoria2-2026-09-29/ (recuperável).

| Item | Veredito |
|---|---|
| core/research_pipeline.py, semantic_memory.py, telegram_bot.py, telegram_importer.py, telegram_webhook.py, working_memory.py | LIXO: stubs de 1 linha, 0 imports reais. "research_pipeline" ocorre em 14 arquivos mas SEMPRE como core.lab_v1.research_pipeline (módulo ativo); "telegram_bot" ocorre em 10 arquivos mas como telegram_bot_token (config) ou tools/zara_telegram_bot.py (ponte viva). |
| core/zara_state_projection.py | LIXO: get_state() dummy; 0 imports (só citado no manual). |
| core/fix_core.py | LIXO: script one-off TASK-002 cumprido; 0 refs. |
| core/proactive_monitor.py | LIXO: watchdog de 03/09 nunca ligado; 0 refs em código (só 2 docs antigas citam o nome). |
| core/tool_clipboard_verifier.py, tool_network_verifier.py, tool_window_verifier.py | LIXO: classes nunca instanciadas; 0 refs em código (só 1 doc .zara-dev cita os nomes). A base core/tool_verifier.py segue viva. |
| core/lab_v1/repair_check.py | LIXO: sem chamadores. NOTA p/ EQUIPE 2/TIME 7: build-sidecar/zara-backend.spec ainda lista 'core.lab_v1.repair_check' em hiddenimports — gera só warning no PyInstaller; limpar a linha numa passada futura. |
| frontend/src/assets/zara-home/zara-logo*.png, zara-mark.png | LIXO: 0 refs; o logo vivo é frontend/src/assets/zara-home/zara-mark.svg (5 imports ativos, conferidos um a um; arquivo existe). |
| frontend/graphify-out/ + frontend/src/renderer/components/zara-lab-v2/graphify-out/ | LIXO: artefatos de análise (cache de AST). |
| frontend/.../zara-lab-v2/proposalEvidenceAdapter.ts | LIXO: 0 refs. |
| frontend aparencia.ts + styles (aparencia.css, instrumento.css, padroes.css, pearl.css, tokens.css, zara-interface.css, PROTOTYPING_SPECS.md) | LIXO: 0 imports (main.tsx só importa globals.css). |
| frontend/tests/*.test.cjs (10) + tests/PainelAparencia.test.tsx | LIXO: fora do npm test — tsconfig.test.json só inclui tests/**/*.ts (.tsx/.cjs nunca compilam; script test roda dist-tests/tests/*.test.js). |
| frontend/public/*.png (12: avatar-*, zara-orb-pearl, zara-ring-*, zara-symbol, zara-wordmark, zara-lab-watermark, zara-brand-*) + zara-alex.css + zara-titanium-emerald/ | LIXO: 0 refs; app usa SVG/classes. zara-titanium-emerald/ é protótipo autocontido (regra do Alex: código velho se remove). |
| assets/zara.ico, zara-mark.png, zara-mark.svg (raiz) | LIXO: build usa frontend/public/zara.ico (package.json L54-66: extraResources from public/zara.ico, icon public/zara.ico); raiz assets/ sem refs. |
| scripts/quarentena/ (14 scripts 03/09) + scripts/executor-perpetuo.py | LIXO: 0 refs; nenhuma tarefa agendada os chama (conferidas: ZARA Auto-Suite, Lab Loop 24x7, Vigia_Corujao, Hermes_Gateway_zara_ceo). |
| profiles/ (100 JSONs 03/09) | LIXO: specs antigas, 0 refs. |
| whatsapp-inbox/oi-001.json | LIXO: ping "oi" de teste, 27/09. |
| .pnpm-store/ (330 MB) | LIXO: era pnpm; node_modules atual autocontido (0 symlinks p/ o store; 1224 reparse points são internos do pnpm dentro de node_modules). |
| .unlazy/ | LIXO: caches/artefatos 23/09. |
| artifacts/ (27,4 MB) | LIXO: logs/screenshots/DBs de canary 20-23/09. |
| raiz: verify_volume_mission.py, verify_pc_voice_binding.py, verify_capability_gate.py, verify_local_ollama_engine.py, ollama_phase1_benchmark.py, test_real_app.py, update_manifest.py, build-current.log + config/telegram_bridge.log | LIXO: probes one-off 20-26/09 + logs velhos; 0 refs (findstr em core/tests/tools/memory/frontend/raiz). |

### Símbolos banidos — varredura OK (correção ao registro anterior)
work_mode_active / work_mode_sentinel / _watch_supercerebro_work_mode aparecem SÓ em comentários/docstrings de aviso (core/computer_agent.py:10-11, core/supercerebro_grant.py:19-20, core/auto_repair.py:17) e no teste-guarda tests/test_computer_agent.py:89, que AFIRMA a ausência deles. Nenhuma implementação. Trava fail-closed intacta. (O registro da AUDITORIA-2 dizia "só em 2 arquivos" — na verdade são 4 arquivos, todos inofensivos.)

### Quarentena antiga re-validada (fila reserva)
Primeira leva (core-stubs, components-zara-interface-antiga, node_modules.bak, 3 release-candidates, a709b02.exe, .bak de log): reconfirmada por amostragem — cópias ativas de ZoeAppPanel.tsx e SupercerebroKey.tsx conferem com o git HEAD (git diff vazio); ZARA-3.0-Setup-3721fd7.exe na QUARENTENA é o instalador superado pelo d3e3639 (presente em instaladores/). Nenhum resgate necessário.


NOTA 06:20 (-03): update_manifest.py reapareceu na raiz entre a listagem inicial e a movimentacao (outra frente paralela o devolveu?). Reauditado: 0 refs, probe one-off de 20/09; movido para QUARENTENA/auditoria2-2026-09-29/.

## RODADA EQUIPE 4 - 2026-09-29 ~05:45 (-03)
Movido para cá (nada apagado - tudo recuperável). Verificação de imports: varredura em 3243 arquivos (py/ts/tsx/js/json/ps1/bat/md/txt/toml), excluindo .git/.venv/node_modules/pasta-lixo/dist-sidecar.

| Item | Motivo |
|---|---|
| `run_ele.bat`, `run_ele.ps1`, `diag.ps1` (raiz, 29/09 01:17) | Launchers one-off do rebuild GIGANTE 2: `run_ele.*` rodava `npm run electron:build` no frontend; `diag.ps1` checava `frontend\release\win-unpacked\resources\backend\zara-backend.exe` (dir `frontend\release\` nem existe mais). 0 refs em código vivo (refs só em logs históricos de `.zara-tests\runs\`). Trabalho cumprido; movidos, não apagados. |
| `.worktrees\build-d3e3639\` | Esqueleto de worktree do build do Time 7 de hoje: NÃO registrado no git (`git worktree list` mostra só a árvore principal) e 0 refs no código. Conteúdo real = 0 bytes (só `frontend\node_modules` como JUNCTION para o `frontend\node_modules` vivo - junction movida, alvo intacto). Build servido já publicado: instalador `ZARA-3.0-Setup-d3e3639.exe` em `instaladores\` (05:08) + `dist-sidecar\zara-backend.exe` (05:06). |

### NÃO mexido (duvidoso ou em uso)
- `medicao-tts-frente3.py`, `medicao-tts-frente3-resultado.json`, `temp-probe-zoe.py` - probes recentes de voz/use-computer (prioridades 1 e 2 da rodada); 0 refs, mas contexto ativo de debug.
- `COMO-TESTAR-A-VOZ.txt`, `TESTAR-VOZ-AGORA.bat`, `CADASTRO-ROSTO-E-VOZ.md` - cadeia viva de teste de voz (`tools\teste_fisico_voz_alex.py` chama o .bat); voz quebrada = prioridade ativa.
- `CLEAN_BUILD_ID.txt`, `PATCH_SHA256_MANIFEST.txt`, `SHA256_MANIFEST.txt`, `ZARA_ACTIVE_BUILD.json/.txt` - bookkeeping de build; `ZARA_ACTIVE_BUILD` tem 155 refs em skills/agentes vivos (`.agents\skills\higiene-do-repositorio`, `.claude\agents\zara-engenheiro-build`, regras de build-release).
- `build-sidecar\`, `dist-sidecar\` - build-sidecar ativo: `zara-backend.exe` rebuildado hoje 05:06.
- `quarentena\` (raiz) - dir vazio, inofensivo; deixado.
- Itens 7+ dias em pasta-lixo para exclusão permanente: NENHUM (pasta-lixo só tem dirs de hoje).

## GARIMPO — EQUIPE 6 (2026-09-29 ~06:40 -03, rodada 3)
Manual da ZARA (skill) lido antes de qualquer veredito. Método: leitura integral dos
3 scripts movidos (baixados e lidos linha a linha) + inspeção do esqueleto
build-d3e3639 + Select-String de refs na árvore ativa (excluindo pasta-lixo/.git/.venv/node_modules)
+ checagem de tarefas agendadas (446 tarefas, nenhuma menciona os itens) + símbolos banidos.
NADA voltou para a raiz. NADA ficou duvidoso. Tudo movido para pasta-lixo/QUARENTENA/rodada3-2026-09-29/ (recuperável).

| Item | Veredito |
|---|---|
| run_ele.bat / run_ele.ps1 | LIXO CONFIRMADO: launchers one-off do rebuild GIGANTE 2 (29/09 01:17) — rodam `npm run electron:build` no frontend. Trabalho cumprido (build d3e3639 publicado + instalado). Refs só em históricos `.zara-tests/` (listas de changed_files) e numa nota do QUADRO-TRABALHO.md que já os classificava como lixo legítimo deletado em 28/09. Recriáveis em 2 linhas se um dia precisar. |
| diag.ps1 | LIXO CONFIRMADO: checava `frontend\release\win-unpacked\resources\backend\zara-backend.exe` — dir `frontend\release\` NEM EXISTE mais (Test-Path = False). One-off cumprido. |
| build-d3e3639/ | LIXO CONFIRMADO: esqueleto de worktree NÃO registrado no git (`git worktree list` mostra só a árvore principal); 0 bytes de conteúdo real — só `frontend\node_modules` como JUNCTION para o node_modules VIVO (alvo intacto, conferido). 0 refs no código, 0 tarefas agendadas. |

### Símbolos banidos — varredito OK nesta leva
`work_mode_active` / `work_mode_sentinel` / `_watch_supercerebro_work_mode`: 0 ocorrências nos itens movidos (run_ele.*, diag.ps1 limpos).

### update_manifest.py — NÃO tocado (aviso da rodada)
Segue em pasta-lixo/QUARENTENA/auditoria2-2026-09-29/ — quarentena correta (teste removido no commit 70f9676). Nada da missão use-computer ativa foi tocado.

### Fila reserva — quarentenas antigas re-validadas (amostragem)
Leva 1 (core-stubs, components-zara-interface-antiga, node_modules.bak, 3 release-candidates, a709b02.exe, .bak log): segue tudo na QUARENTENA, nada com 7+ dias para exclusão permanente (pasta-lixo só tem itens de hoje 29/09). Nenhum resgate necessário.

### NÃO movido para a QUARENTENA (deixado na pasta-lixo/2026-09-29 — este REGISTRO.md continua na staging até a rodada fechar)

## RODADA EQUIPE 4 - 2026-09-29 ~06:40 (-03)
Movido para `frontend-logs-20260922/` (nada apagado - tudo recuperavel).
Verificacao: 2 varreduras independentes de refs em ~6000 arquivos
(py/ps1/bat/ts/tsx/js/json/md/txt/toml, excl. .git/.venv/node_modules/
pasta-lixo/dist-sidecar/build-sidecar/ZOE-*) = 0 referencias externas
para todos os 16 nomes. Arquivos de 2026-09-22 (7 dias), saidas de
debug antigas (electron/build/tsc), nenhum processo escreve neles.

| Item | Motivo |
|---|---|
| `frontend/ele_run_out.txt`, `npm_build_out*.txt` (3), `npm_typecheck_result.txt`, `tsc_result.txt`, `pe_run_out.txt`, `nv.txt`, `pv.txt`, `s1.txt`..`s7.txt` (16 arquivos) | Logs soltos de debug de 22/09 na raiz do frontend; 0 refs; saida de build/teste antiga. |

### NAO mexido (duvidoso, em uso ou de outra raia)
- `frontend/dist-tests/` - usado pelo `npm test` (`tsc -p tsconfig.test.json && node --test dist-tests/tests/*.test.js`). Nao tocar.
- `frontend/dist-electron/`, `frontend/dist-frontend/` - saidas de build; raia do TIME 7.
- `frontend/public/zara.ico` - em uso (package.json extraResources/icon). Nao tocar.
- `frontend/tests/*.test.ts` (7) - compilados pelo npm test. Nao tocar.
- `medicao-tts-frente3.py`, `medicao-tts-frente3-resultado.json`, `temp-probe-zoe.py` - probes de voz/use-computer; prioridades 1-2 seguem ativas nesta rodada. Nao mexer.
- `COMO-TESTAR-A-VOZ.txt`, `TESTAR-VOZ-AGORA.bat` - cadeia viva (`tools\teste_fisico_voz_alex.py` chama o .bat).
- `quarentena/` (raiz) e `assets/` (raiz) - dirs vazios, inofensivos; deixados.
- `DOSSIE ZARA/` - dossie de documentacao do projeto; nao e lixo.
- Itens 7+ dias em pasta-lixo para exclusao permanente: NENHUM (tudo de hoje).
- Simbolos banidos (`work_mode_active` etc.): nao procurados nesta passada (raia so-move; sem edicao de codigo). EQUIPE 2/6 cobre.

## GARIMPO - EQUIPE 6 (2026-09-29 ~07:05 -03, rodada 06:55)
Metodo: varredura INDEPENDENTE de refs (py/ps1/bat/cmd/js/ts/tsx/json/md/yml/yaml/txt, fora pasta-lixo/.git/.venv/node_modules) = 0 ocorrencias p/ "frontend-logs", "npm_build_out", "ele_run_out" + checagem de simbolos banidos nos 16 arquivos + armadilhas do Manual (secao 7) re-validadas. Lido SKILL manual-zara antes do veredito.
Veredito: frontend-logs-20260922/ (16 logs de debug de 22/09, ~16 KB, 0 refs) -> movido p/ pasta-lixo/QUARENTENA/frontend-logs-20260922/. NADA voltou p/ raiz. NADA duvidoso.
Simbolos banidos (work_mode_active / work_mode_sentinel / _watch_supercerebro_work_mode): 0 ocorrencias nos 16 logs.
Armadilhas re-validadas: core/nightly_regression.py intacta; SupercerebroKey.tsx e ZoeAppPanel.tsx com copias ATIVAS na arvore (frontend/src/renderer/components/zara/) - as quarentenadas seguem sendo duplicatas velhas (regra: nao tocar nas ativas).
Fila reserva (re-varredura): rodada3-2026-09-29/ ja garimpada na rodada anterior (~06:40, tudo confirmado lixo na QUARENTENA); leva 1 re-validada na rodada anterior; nada com 7+ dias p/ exclusao permanente.

## RODADA EQUIPE 4 - 2026-09-29 ~07:05 (-03)
Movidos para ca (nada apagado - tudo recuperavel).
Verificacao: varredura de referencias em todo o repo (py/ps1/bat/ts/tsx/js/
json/md/txt/toml/yaml/spec, excluindo .git/.venv/node_modules/pasta-lixo/
dist-sidecar/build-sidecar/ZOE-*) = 0 ocorrencias para "run_diag".

| Item | Motivo |
|---|---|
| un_diag.bat (raiz, 22/09) | Launcher one-off de diag do GIGANTE 2: rodava zara-backend.exe em rontend\release\win-unpacked\resources\backend - dir que NAO existe mais. Trabalho cumprido, 0 refs. |
| un_diag_src.bat (raiz, 22/09) | Launcher one-off: python.exe -u main.py. Trabalho cumprido, 0 refs. |

### NAO mexido (duvidoso ou em uso)
- PERSONALIDADE_DA_ZARA.txt - VIVA: core/personality.py e core/gemini_live_voice.py a usam (+ teste 	est_personality_shared_source.py). Nao tocar.
- INSTALL_HERMES.txt - citado por 	ools\limpar_pasta.py e docs. Nao tocar.
- medicao-tts-frente3.py, medicao-tts-frente3-resultado.json, 	emp-probe-zoe.py - probes de voz/use-computer; prioridades 1-2 seguem ativas. Nao mexer.
- COMO-TESTAR-A-VOZ.txt, TESTAR-VOZ-AGORA.bat - cadeia viva de teste de voz. Nao mexer.
- Manifests de build (CLEAN_BUILD_ID.txt, SHA256_MANIFEST.txt, ZARA_ACTIVE_BUILD.*) - bookkeeping do TIME 7. Nao mexer.
- .bak: nenhum fora de pasta-lixo. Dirs temp/tmp/release-candidate/old/bak: nenhum. Logs soltos: nenhum (so bookkeeping em .zara-tests/.lab-vivo). instaladores/: so o setup atual d3e3639 (protegido).
- Itens 7+ dias em pasta-lixo para exclusao permanente: NENHUM (pasta-lixo so tem dirs de hoje 29/09).

## GARIMPO - EQUIPE 6 (2026-09-29 ~07:35 -03, rodada 07:25)
Metodo: leitura integral dos 2 .bat movidos (baixados e lidos) + varredura
INDEPENDENTE de refs "run_diag" na arvore ativa (py/ps1/bat/cmd/ts/tsx/js/json/
md/txt/yaml/yml/xml/toml/spec/task; fora pasta-lixo/.git/.venv/node_modules/
dist-sidecar/build-sidecar/ZOE-INBOX/ZOE-QUARENTENA) + tarefas agendadas
(schtasks) + simbolos banidos nos 2 arquivos + armadilhas do Manual re-validadas.
SKILL manual-zara lida antes do veredito.
Veredito: run_diag.bat + run_diag_src.bat -> movidos p/ pasta-lixo/QUARENTENA/rodada4-2026-09-29/. NADA voltou p/ raiz. NADA duvidoso.

| Item | Veredito |
|---|---|
| run_diag.bat | LIXO CONFIRMADO: launcher one-off (22/09) que roda zara-backend.exe em frontend\release\win-unpacked\resources\backend - o dir frontend\release\ NEM EXISTE (Test-Path=False). Unica ref na arvore ativa: lista de changed_files num .zara-tests\runs\...\summary.json (historico de teste, nao codigo vivo). 0 tarefas agendadas. 0 simbolos banidos. |
| run_diag_src.bat | LIXO CONFIRMADO: launcher one-off (22/09): .venv\Scripts\python.exe -u main.py. Unica ref = mesmo summary.json historico. 0 tarefas agendadas. 0 simbolos banidos. |

### Simbolos banidos nesta leva
work_mode_active / work_mode_sentinel / _watch_supercerebro_work_mode: 0 ocorrencias nos 2 arquivos.

### Armadilhas re-validadas (Manual secao 7)
- core/nightly_regression.py intacta (stub intencional p/ testes).
- SupercerebroKey.tsx e ZoeAppPanel.tsx: copias ATIVAS existem na arvore
  (frontend\src\renderer\components\zara\interface\SupercerebroKey.tsx e
  frontend\src\renderer\components\zara\ZoeAppPanel.tsx) e conferem com o
  git HEAD (git diff --quiet, exit 0) - as quarentenadas seguem duplicatas velhas.
- instaladores\: so ZARA-3.0-Setup-d3e3639.exe (206,5 MB, o atual). a709b02 e
  3721fd7 seguem na QUARENTENA, superados.

### Fila reserva - quarentenas antigas
Re-validada a regra de 7+ dias: todas as quarentenas entraram em pasta-lixo em
29/09 (pelos registros de movimento; CreationTime dos dirs preserva a data
original, nao a data de entrada). NENHUM item com 7+ dias em pasta-lixo hoje -
nada elegivel p/ exclusao permanente nesta rodada.

## RODADA EQUIPE 4 - 2026-09-29 ~07:35 (-03)
VARRIDO e NADA MOVIDO - a raiz está limpa. Método: 5 varreduras PowerShell na árvore ativa
(~6000 arquivos: py/ps1/bat/cmd/ts/tsx/js/json/md/yaml/yml/txt/toml, excluindo
pasta-lixo/.git/.venv/node_modules/ZOE-QUARENTENA/dist-sidecar/build-sidecar):
(1) arquivos novos desde 07:05, (2) padrões .bak/.old/.tmp/.log/.orig, (3) dirs
release-candidate-*/node_modules.bak/Temp/tmp, (4) exes/instaladores fora das zonas
protegidas, (5) dumps/crashes.

### Resultado
- Arquivos novos desde 07:05: só estado vivo (runs do .zara-tests, core/ editado pela
  equipe 2 (ipc_handlers.py, voice_tts.py), ZOE-INBOX ativa, logs do .lab-vivo).
  Nada para mover.
- Padrões de lixo: zero .bak/.old/.tmp fora de pasta-lixo; logs soltos só em
  .lab-vivo/logs e .zara-tests/ (bookkeeping vivo, de hoje/ontem) - não tocar.
- Exes/instaladores: só dentro de .zara-dev/voice-probe/site-packages/ (venv viva
  de probe de voz) e nas zonas protegidas. instaladores/ tem só o setup atual.
- Dirs vazios na raiz: assets/ e quarentena/ (0 itens) - deixados de propósito
  (scripts de build podem esperar o path; mover dir vazio não libera nada).
- frontend/tsconfig.node.tsbuildinfo - artefato de build incremental, equipe 5
  compilando; não tocar.

### NÃO mexido (deliberado, prioridades ativas)
- medicao-tts-frente3.py, medicao-tts-frente3-resultado.json, temp-probe-zoe.py,
  COMO-TESTAR-A-VOZ.txt, TESTAR-VOZ-AGORA.bat, CADASTRO-ROSTO-E-VOZ.md -
  contexto de debug das prioridades 1 (use-computer) e 2 (voz), ainda ativas.
  0 refs em código, mas a exclusão de acesso manual agora pode atrapalhar o debug
  em curso. Reavaliar na próxima rodada se as prioridades fecharem.
- .zara-dev/ (207 MB, lab vivo), .worktrees/ vazios, frontend/dist-*/dist-tests/
  (equipe 5/time 7), __pycache__/ (regenerável, mas em uso).

### Itens 7+ dias em pasta-lixo para exclusão permanente: NENHUM
pasta-lixo/ só tem dirs de hoje 29/09 (2026-09-29/, QUARENTENA/) - nada com 7+ dias.
Candidatos futuros: pasta-lixo/QUARENTENA/ completa 7 dias em 06/10/2026 (levar
para o CADERNO na rodada daquela semana).

### Símbolos banidos - varredura de rotina OK
work_mode_active / work_mode_sentinel / _watch_supercerebro_work_mode: 6
ocorrências em 3275 arquivos, TODAS em avisos de docstring (core/auto_repair.py:17,
core/computer_agent.py:10-11, core/supercerebro_grant.py:19-20 - "continuam
proibidos", "não existem neste módulo", "NUNCA reimplementar") + o teste-guarda
tests/test_computer_agent.py::test_simbolos_banidos_nao_existem_no_agente que
AFIRMA a ausência no código. Nenhuma implementação. Trava fail-closed intacta.


## GARIMPO — EQUIPE 6 (2026-09-29 ~09:30 -03, rodada 09:25)
Manual da ZARA (skill) lido antes de qualquer veredito. EQUIPE 4 não moveu NADA novo nesta rodada (varredura 07:35: raiz limpa; staging 2026-09-29/ tem só este REGISTRO.md). Fila reserva: re-varredura das quarentenas + regra de 7+ dias.
Método: 2 varreduras PowerShell na árvore ativa (refs aos instaladores antigos; símbolos banidos na QUARENTENA) + git status/diff das cópias ativas de SupercerebroKey.tsx/ZoeAppPanel.tsx + checagem do backup-app-20260929-0915/ + CreationTime dos dirs p/ regra de 7+ dias.

| Item | Veredito |
|---|---|
| ZARA-3.0-Setup-d3e3639.exe (206,5 MB, na QUARENTENA desde ~09:14) | QUARENTENA CORRETA: superado pelo e35b204 (instaladores/, 203,4 MB, commit e35b204 09:02). Backup do app anterior completo em instaladores/backup-app-20260929-0915/. 0 refs ativas. Registrado no QUARENTENA/REGISTRO.txt. |
| ZARA-3.0-Setup-3721fd7.exe (206,5 MB, na QUARENTENA) | QUARENTENA CORRETA: superado pelo d3e3639; registrado a posteriori no QUARENTENA/REGISTRO.txt. |
| Demais quarentenas (core-stubs, components-zara-interface-antiga, node_modules.bak, 3 release-candidates, a709b02.exe, .bak log, auditoria2, rodada3, rodada4, frontend-logs-20260922) | Re-validadas por amostragem: nada resgatável. ZoeAppPanel.tsx ATIVA tem 1 linha modificada não commitada (trabalho in-flight de outra frente nesta rodada — raia alheia, TIME 7 commita); SupercerebroKey.tsx ativa = HEAD. As quarentenadas seguem duplicatas velhas. |

### Símbolos banidos
`work_mode_active` / `work_mode_sentinel` / `_watch_supercerebro_work_mode`: 2 ocorrências na QUARENTENA, AMBAS em logs inertes do canary readonly de 28/09 (`auditoria2-2026-09-29/artifacts/canary-zara-current-20260928-153755-readonly/electron.stderr.log:21`, `electron.stdout.log:108`) — são linhas de `ImportError` registrando a FALHA do import banido durante a neutralização da anomalia de 28/09. Logs não executam; nenhum código vivo reimplementa. Quarentena intacta, trava fail-closed intacta.

### Regra de 7+ dias (exclusão permanente)
NENHUM item com 7+ dias em pasta-lixo: a entrada mais antiga é 29/09 ~04:53 (leva 1, per REGISTRO.md). Nada elegível p/ exclusão permanente nesta rodada.

### Nota de higiene p/ rodadas futuras
`skills-compartilhadas/manual-zara/manual-snapshot.md:45` cita `ZARA-3.0-Setup-a709b02.exe` como exemplo na descrição de `instaladores/` — só doc, sem efeito funcional; atualizar o exemplo numa passada de docs (não é raia da EQUIPE 6).

## Rodada 2026-09-29 ~09:35 (-03) — EQUIPE 4 (vigia-melhoria-app-30min)
Verificacao: varredura de referencias em 5899 arquivos do repo (nome + conteudo, inclui caminhos relativos, docs, frontend, ZOE-INBOX) + checagem de processos ativos no PC. Nenhum codigo, teste, build, doc ou tarefa agenda referencia os itens abaixo. Nada apagado de verdade — tudo recuperavel aqui.

| Item | Motivo |
|---|---|
| TESTAR-VOZ-AGORA.bat | Wrapper de duplo-clique para tools/teste_fisico_voz_alex.py (o script continua em tools/). Citado so no doc COMO-TESTAR-A-VOZ.txt. |
| COMO-TESTAR-A-VOZ.txt | Roteiro de teste fisico de voz para o Alex (28/09). Nao referenciado por codigo. |
| CADASTRO-ROSTO-E-VOZ.md | Guia de cadastro rosto/voz (28/09); o script scripts/cadastrar_identidade.py continua no lugar. |
| medicao-tts-frente3.py | Script avulso de medicao de latencia do TTS (Frente 3, 28/09). 0 imports em todo o repo. |
| medicao-tts-frente3-resultado.json | Resultado JSON da medicao acima (28/09). Nao consumido por nada. |
| temp-probe-zoe.py | Probe avulso do registry de actions (computer_*). 0 referencias. |

NAO mexido (verificado, mantido na raiz):
- tools/teste_fisico_voz_alex.py e scripts/cadastrar_identidade.py — scripts-alvo dos docs acima, continuam ativos.
- Nenhum .exe / .bak / release-candidate-* / node_modules.bak / Temp novo na raiz (varredura 29/09 ~09:35).
- Exclusao permanente: NADA — nenhum item completou 7 dias dentro da pasta-lixo (pastas datadas mais antigas sao de 29/09; mtimes antigos dentro delas sao da epoca do arquivo, nao da entrada no lixo).

## GARIMPO — EQUIPE 6 (2026-10-02 ~15:45 -03, vigia-melhoria-app-30min)
Manual da ZARA (skill, seção 7) lido antes de qualquer veredito. Método: varredura
INDEPENDENTE de referências na árvore ativa (410.721 arquivos examinados:
py/ps1/bat/cmd/ts/tsx/js/json/md/yaml/yml/txt/toml/spec; excluindo
.git/.venv/node_modules/pasta-lixo/dist-sidecar/build-sidecar/.worktrees/
.zara-tests/.lab-vivo/.zara-dev/ZOE-INBOX/ZOE-QUARENTENA + binários) + leitura das
menções encontradas + confirmação de existência dos scripts-alvo + varredura de
símbolos banidos em core/*.py + re-validação das quarentenas antigas.
Veredito: os 6 arquivos soltos na staging (probes e guias de voz de 28-29/09, que as
rodadas de 29/09 deixaram como "duvidosos" por causa do debug ativo de voz) →
movidos para pasta-lixo/QUARENTENA/rodada5-2026-10-02/ (recuperáveis). NADA voltou
para a raiz. NADA ficou duvidoso. NADA apagado permanentemente (regra de 7+ dias:
entradas mais antigas são de 29/09 — nada elegível; QUARENTENA completa 7 dias
em 06/10/2026).

| Item | Veredito |
|---|---|
| TESTAR-VOZ-AGORA.bat | QUARENTENA: wrapper de duplo-clique p/ tools/teste_fisico_voz_alex.py (o script REAL continua ativo na raiz). A única menção ao nome é instrução textual dentro do próprio script ("Duplo clique em TESTAR-VOZ-AGORA.bat") — não dependência de código. |
| COMO-TESTAR-A-VOZ.txt | QUARENTENA: 0 refs; roteiro de teste físico de voz de 28/09. Voz entregue 02/10 (491 testes verdes, failover provado) e documentada no vault (20-PROJETO-ZARA/2026-10-02-voz-como-testar.md). |
| CADASTRO-ROSTO-E-VOZ.md | QUARENTENA: 0 refs; guia de cadastro rosto/voz de 28/09. O script-alvo scripts/cadastrar_identidade.py continua ativo na raiz. |
| medicao-tts-frente3.py | QUARENTENA: 0 refs; probe one-off de latência TTS (Frente 3, 28/09). Missão de voz concluída 02/10. |
| medicao-tts-frente3-resultado.json | QUARENTENA: 0 refs; resultado JSON não consumido por nada. |
| temp-probe-zoe.py | QUARENTENA: 0 refs; probe avulso do registry de actions (computer_*). |

### Símbolos banidos — varredura OK nesta rodada
work_mode_active / work_mode_sentinel / _watch_supercerebro_work_mode em
core/*.py: ocorrências SÓ nos arquivos de aviso conhecidos (docstrings de aviso em
core/auto_repair.py, core/computer_agent.py, core/supercerebro_grant.py) — nenhum
arquivo novo implementa os símbolos. O teste-guarda
tests/test_computer_agent.py continua afirmando a ausência. Nenhuma
reimplementação. Trava fail-closed intacta.

### Fila reserva — quarentenas antigas re-validadas
- components-zara-interface-antiga/ (ZoeAppPanel.tsx, SupercerebroKey.tsx etc.):
  RECONFIRMADO LIXO — o frontend/src NÃO tem mais nenhum arquivo com esses nomes
  e 0 referências aos nomes ZoeAppPanel/SupercerebroKey em todo o frontend/src
  (a interface foi reestruturada para zara-home/zara-nova; os componentes velhos
  não são montados por nada). As cópias quarentenadas seguem duplicatas velhas.
- Demais quarentenas (core-stubs, node_modules.bak-build-publish-20260926,
  3 release-candidates de voz, instaladores a709b02/3721fd7/d3e3639, .bak de log,
  auditoria2-2026-09-29, rodada3-2026-09-29, rodada4-2026-09-29,
  frontend-logs-20260922): vereditos de 29/09 mantidos — nada resgatável.
- Regra de 7+ dias: NENHUM item elegível p/ exclusão permanente (tudo entrou em
  29/09; 02/10 = 3 dias).

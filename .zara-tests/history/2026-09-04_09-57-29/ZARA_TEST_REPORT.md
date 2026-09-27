# ZARA SELF TEST REPORT

- run_id: `2026-09-04_09-57-29`
- commit: `ce83e63` (branch `backup/estado-20260820-1143`)
- duração: 249.9s

## SUMMARY

- Total: 37
- Passed: 32
- Failed: 0
- Known failures (camada técnica): ver seção técnica abaixo
- Skipped: 0
- Unsupported: 0
- Executed unverified: 4
- Timeout: 0
- Blocked: 1

## HEALTH SCORE: 86%

## WORKING NOW

- SYS-DISK Espaço em disco (0ms)
- TECH-001 Camada técnica (zara_validate.py) (147936ms)
- SYS-BOOT Boot do backend (0ms)
- SYS-001 Comando de texto ("que horas são?") (59ms)
- SYS-002 Ver processos (system_processes) (1289ms)
- SYS-003 Métricas de sistema (CPU/RAM/disco) (133ms)
- SYS-004 Wi-Fi (leitura real do rádio) (1629ms)
- SYS-005 Planos de energia (powercfg real) (121ms)
- SYS-006 Diagnóstico interno (self-status) (1431ms)
- MEM-001 Memória de usuário (leitura real) (27ms)
- MEM-002 Memória de projeto (leitura real) (30ms)
- APP-001 Abrir app real (Bloco de Notas) (206ms)
- APP-002 Minimizar app (via texto) (182ms)
- REM-001 Lembretes (criar) (38ms)
- REM-002 Lembretes (cancelar, limpa o teste) (30ms)
- FILE-001 Criar pasta (sandbox) (0ms)
- FILE-002 Criar arquivo (sandbox) (0ms)
- FILE-003 Renomear arquivo (sandbox) (0ms)
- FILE-004 Copiar arquivo (sandbox) (1ms)
- FILE-005 Listar pasta (sandbox) (0ms)
- ERR-001 App inexistente falha com erro claro (24ms)
- ERR-002 Comando sem sentido não trava o backend (24127ms)
- PC-001 "abre o youtube" (493ms)
- PC-002 "pesquisa hans zimmer no youtube" (433ms)
- PC-005 "diminui o volume" (224ms)
- PC-006 "diminui o brilho" (5566ms)
- PC-008 "pausa" (941ms)
- PC-009 "continua" (1855ms)
- PC-010 "abre o spotify" (2368ms)
- PC-011 "minimiza" (154ms)
- RESTORE-VOL Restaurar volume original (151ms)
- RESTORE-BRI Restaurar brilho original (4228ms)

## SLOW OPERATIONS

| Test | Latência | Categoria |
|---|---|---|
| TECH-001 Camada técnica (zara_validate.py) | 147936ms | technical |
| ERR-002 Comando sem sentido não trava o backend | 24127ms | system |
| PC-003 "toca hans zimmer" | 13300ms | pc_control |
| PC-007 "pula essa" | 8849ms | pc_control |
| PC-006 "diminui o brilho" | 5566ms | pc_control |

## NOTAS

- A ZARA tem 141 ações registradas no total; este relatório testa uma amostra representativa (37 checagens).

## TEST DETAILS

- **SYS-DISK** [PASS] Espaço em disco — 0ms — 20.9GB livres
- **TECH-001** [PASS] Camada técnica (zara_validate.py) — 147936ms — 1632 passou, 25 falha(s) já conhecida(s), 0 nova(s)
- **SYS-BOOT** [PASS] Boot do backend — 0ms — emitiu o sinal de pronto
- **SYS-001** [PASS] Comando de texto ("que horas são?") — 59ms — "Agora são 10:00."
- **SYS-002** [PASS] Ver processos (system_processes) — 1289ms — 267 processos reais
- **SYS-003** [PASS] Métricas de sistema (CPU/RAM/disco) — 133ms — {'cpu': 0.0, 'ram': 88.7, 'disk': 91.6, 'netUp': 0, 'netDown': 0}
- **SYS-004** [PASS] Wi-Fi (leitura real do rádio) — 1629ms — estado: On
- **SYS-005** [PASS] Planos de energia (powercfg real) — 121ms — 4 planos
- **SYS-006** [PASS] Diagnóstico interno (self-status) — 1431ms — 14/18 disponíveis
- **MEM-001** [PASS] Memória de usuário (leitura real) — 27ms — 12 fatos
- **MEM-002** [PASS] Memória de projeto (leitura real) — 30ms — docs: architecture, auditoria_completa_20260824, charter, decisions, roadmap, state
- **APP-001** [PASS] Abrir app real (Bloco de Notas) — 206ms — PID 16204, janela verificada
- **APP-002** [PASS] Minimizar app (via texto) — 182ms — Janela minimizada e verificada.
- **REM-001** [PASS] Lembretes (criar) — 38ms — id REM-1788526812581-E35D
- **REM-002** [PASS] Lembretes (cancelar, limpa o teste) — 30ms — cancelado
- **FILE-001** [PASS] Criar pasta (sandbox) — 0ms — C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\.zara-tests\sandbox\TesteAutomacao
- **FILE-002** [PASS] Criar arquivo (sandbox) — 0ms — C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\.zara-tests\sandbox\TesteAutomacao\teste.txt
- **FILE-003** [PASS] Renomear arquivo (sandbox) — 0ms — C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\.zara-tests\sandbox\TesteAutomacao\resultado.txt
- **FILE-004** [PASS] Copiar arquivo (sandbox) — 1ms — C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\.zara-tests\sandbox\Backup\resultado.txt
- **FILE-005** [PASS] Listar pasta (sandbox) — 0ms — ['resultado.txt']
- **ERR-001** [PASS] App inexistente falha com erro claro — 24ms — Aplicativo não autorizado. Use um aplicativo conhecido da lista segura.
- **ERR-002** [PASS] Comando sem sentido não trava o backend — 24127ms — Esse comando não existe no meu sistema, Alex. Não encontrei nenhuma ação registrada para ele.
- **PC-001** [PASS] "abre o youtube" — 493ms — [EXCELLENT] YouTube enviado ao navegador padrão. Não consegui confirmar; se não tiver acontecido, me fala.
- **PC-002** [PASS] "pesquisa hans zimmer no youtube" — 433ms — [EXCELLENT] Pesquisa por “hans zimmer” enviada ao YouTube. Não consegui confirmar; se não tiver acontecido, me fala.
- **PC-003** [EXECUTED_UNVERIFIED] "toca hans zimmer" — 13300ms — [VERY_SLOW] Não consegui executar essa ação. O vídeo foi selecionado, mas a reprodução não pôde ser confirmada.
- **PC-004** [EXECUTED_UNVERIFIED] "pula o anuncio" — 1620ms — [EXCELLENT] Não consegui executar essa ação. Não encontrei um botão acessível de anúncio pulável no YouTube.
- **PC-005** [PASS] "diminui o volume" — 224ms — [EXCELLENT] Volume definido para 44%.
- **PC-006** [PASS] "diminui o brilho" — 5566ms — [VERY_SLOW] Brilho definido para 30%.
- **PC-007** [EXECUTED_UNVERIFIED] "pula essa" — 8849ms — [SLOW] Não consegui executar essa ação. Comando enviado, mas a troca de música não pôde ser confirmada.
- **PC-008** [PASS] "pausa" — 941ms — [EXCELLENT] Pausado.
- **PC-009** [PASS] "continua" — 1855ms — [EXCELLENT] Continuando.
- **PC-010** [PASS] "abre o spotify" — 2368ms — [EXCELLENT] Spotify aberto e verificado.
- **PC-011** [PASS] "minimiza" — 154ms — [EXCELLENT] Janela minimizada e verificada.
- **PC-012** [EXECUTED_UNVERIFIED] "foca no chrome" — 71ms — [EXCELLENT] Não consegui executar essa ação. Encontrei mais de uma janela de chrome. Diga qual delas.
- **PC-013** [BLOCKED] "abre o chrome no perfil trabalho" — 23ms — [EXCELLENT] Para controlar o computador, ative o Supercérebro.
- **RESTORE-VOL** [PASS] Restaurar volume original — 151ms — de volta para 54%
- **RESTORE-BRI** [PASS] Restaurar brilho original — 4228ms — de volta para 40%
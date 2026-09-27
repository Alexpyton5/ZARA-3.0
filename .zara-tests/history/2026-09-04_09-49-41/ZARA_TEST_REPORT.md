# ZARA SELF TEST REPORT

- run_id: `2026-09-04_09-49-41`
- commit: `ce83e63` (branch `backup/estado-20260820-1143`)
- duração: 292.5s

## SUMMARY

- Total: 36
- Passed: 29
- Failed: 1
- Known failures (camada técnica): ver seção técnica abaixo
- Skipped: 0
- Unsupported: 0
- Executed unverified: 5
- Timeout: 0
- Blocked: 1

## HEALTH SCORE: 81%

## BROKEN NOW

- **ERR-002** Comando sem sentido não trava o backend: sem resposta (pode ter travado)

## WORKING NOW

- SYS-DISK Espaço em disco (0ms)
- TECH-001 Camada técnica (zara_validate.py) (144764ms)
- SYS-BOOT Boot do backend (0ms)
- SYS-001 Comando de texto ("que horas são?") (97ms)
- SYS-002 Ver processos (system_processes) (1178ms)
- SYS-003 Métricas de sistema (CPU/RAM/disco) (123ms)
- SYS-004 Wi-Fi (leitura real do rádio) (1597ms)
- SYS-005 Planos de energia (powercfg real) (140ms)
- SYS-006 Diagnóstico interno (self-status) (1382ms)
- MEM-001 Memória de usuário (leitura real) (35ms)
- MEM-002 Memória de projeto (leitura real) (31ms)
- APP-001 Abrir app real (Bloco de Notas) (197ms)
- APP-002 Minimizar app (via texto) (194ms)
- REM-001 Lembretes (criar) (32ms)
- REM-002 Lembretes (cancelar, limpa o teste) (30ms)
- FILE-001 Criar pasta (sandbox) (1ms)
- FILE-002 Criar arquivo (sandbox) (0ms)
- FILE-003 Renomear arquivo (sandbox) (0ms)
- FILE-004 Copiar arquivo (sandbox) (1ms)
- FILE-005 Listar pasta (sandbox) (0ms)
- ERR-001 App inexistente falha com erro claro (22ms)
- PC-001 "abre o youtube" (452ms)
- PC-002 "pesquisa hans zimmer no youtube" (425ms)
- PC-005 "diminui o volume" (222ms)
- PC-006 "diminui o brilho" (5264ms)
- PC-008 "pausa" (1234ms)
- PC-010 "abre o spotify" (2241ms)
- PC-011 "minimiza" (238ms)
- RESTORE-BRI Restaurar brilho original (4231ms)

## SLOW OPERATIONS

| Test | Latência | Categoria |
|---|---|---|
| TECH-001 Camada técnica (zara_validate.py) | 144764ms | technical |
| ERR-002 Comando sem sentido não trava o backend | 40108ms | system |
| PC-003 "toca hans zimmer" | 11705ms | pc_control |
| PC-009 "continua" | 5290ms | pc_control |
| PC-006 "diminui o brilho" | 5264ms | pc_control |

## NOTAS

- A ZARA tem 141 ações registradas no total; este relatório testa uma amostra representativa (36 checagens).

## TEST DETAILS

- **SYS-DISK** [PASS] Espaço em disco — 0ms — 22.3GB livres
- **TECH-001** [PASS] Camada técnica (zara_validate.py) — 144764ms — 1632 passou, 25 falha(s) já conhecida(s), 0 nova(s)
- **SYS-BOOT** [PASS] Boot do backend — 0ms — emitiu o sinal de pronto
- **SYS-001** [PASS] Comando de texto ("que horas são?") — 97ms — "Agora são 09:52."
- **SYS-002** [PASS] Ver processos (system_processes) — 1178ms — 267 processos reais
- **SYS-003** [PASS] Métricas de sistema (CPU/RAM/disco) — 123ms — {'cpu': 0.0, 'ram': 93.1, 'disk': 91.2, 'netUp': 0, 'netDown': 0}
- **SYS-004** [PASS] Wi-Fi (leitura real do rádio) — 1597ms — estado: On
- **SYS-005** [PASS] Planos de energia (powercfg real) — 140ms — 4 planos
- **SYS-006** [PASS] Diagnóstico interno (self-status) — 1382ms — 14/18 disponíveis
- **MEM-001** [PASS] Memória de usuário (leitura real) — 35ms — 12 fatos
- **MEM-002** [PASS] Memória de projeto (leitura real) — 31ms — docs: architecture, auditoria_completa_20260824, charter, decisions, roadmap, state
- **APP-001** [PASS] Abrir app real (Bloco de Notas) — 197ms — PID 19256, janela verificada
- **APP-002** [PASS] Minimizar app (via texto) — 194ms — Janela minimizada e verificada.
- **REM-001** [PASS] Lembretes (criar) — 32ms — id REM-1788526342194-4AF6
- **REM-002** [PASS] Lembretes (cancelar, limpa o teste) — 30ms — cancelado
- **FILE-001** [PASS] Criar pasta (sandbox) — 1ms — C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\.zara-tests\sandbox\TesteAutomacao
- **FILE-002** [PASS] Criar arquivo (sandbox) — 0ms — C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\.zara-tests\sandbox\TesteAutomacao\teste.txt
- **FILE-003** [PASS] Renomear arquivo (sandbox) — 0ms — C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\.zara-tests\sandbox\TesteAutomacao\resultado.txt
- **FILE-004** [PASS] Copiar arquivo (sandbox) — 1ms — C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\.zara-tests\sandbox\Backup\resultado.txt
- **FILE-005** [PASS] Listar pasta (sandbox) — 0ms — ['resultado.txt']
- **ERR-001** [PASS] App inexistente falha com erro claro — 22ms — Aplicativo não autorizado. Use um aplicativo conhecido da lista segura.
- **ERR-002** [FAIL] Comando sem sentido não trava o backend — 40108ms — sem resposta (pode ter travado)
- **PC-001** [PASS] "abre o youtube" — 452ms — [EXCELLENT] YouTube enviado ao navegador padrão. Não consegui confirmar; se não tiver acontecido, me fala.
- **PC-002** [PASS] "pesquisa hans zimmer no youtube" — 425ms — [EXCELLENT] Pesquisa por “hans zimmer” enviada ao YouTube. Não consegui confirmar; se não tiver acontecido, me fala.
- **PC-003** [EXECUTED_UNVERIFIED] "toca hans zimmer" — 11705ms — [SLOW] Não consegui executar essa ação. O vídeo foi selecionado, mas a reprodução não pôde ser confirmada.
- **PC-004** [EXECUTED_UNVERIFIED] "pula o anuncio" — 4897ms — [GOOD] Não consegui executar essa ação. Não encontrei um botão acessível de anúncio pulável no YouTube.
- **PC-005** [PASS] "diminui o volume" — 222ms — [EXCELLENT] Volume definido para 20%.
- **PC-006** [PASS] "diminui o brilho" — 5264ms — [VERY_SLOW] Brilho definido para 30%.
- **PC-007** [EXECUTED_UNVERIFIED] "pula essa" — 57ms — [EXCELLENT] Não consegui executar essa ação. Não encontrei um vídeo ativo do YouTube.
- **PC-008** [PASS] "pausa" — 1234ms — [EXCELLENT] Pausado.
- **PC-009** [EXECUTED_UNVERIFIED] "continua" — 5290ms — [GOOD] Não consegui executar essa ação. Comando enviado, mas a mudança do player não pôde ser confirmada.
- **PC-010** [PASS] "abre o spotify" — 2241ms — [EXCELLENT] Spotify aberto e verificado.
- **PC-011** [PASS] "minimiza" — 238ms — [EXCELLENT] Janela minimizada e verificada.
- **PC-012** [EXECUTED_UNVERIFIED] "foca no chrome" — 53ms — [EXCELLENT] Não consegui executar essa ação. Encontrei mais de uma janela de chrome. Diga qual delas.
- **PC-013** [BLOCKED] "abre o chrome no perfil trabalho" — 132ms — [EXCELLENT] Para controlar o computador, ative o Supercérebro.
- **RESTORE-BRI** [PASS] Restaurar brilho original — 4231ms — de volta para 40%
# ZARA SELF TEST REPORT

- run_id: `2026-09-04_13-00-26`
- commit: `ce83e63` (branch `backup/estado-20260820-1143`)
- duração: 315.2s

## SUMMARY

- Total: 48
- Passed: 45
- Failed: 1
- Known failures (camada técnica): ver seção técnica abaixo
- Skipped: 0
- Unsupported: 0
- Executed unverified: 2
- Timeout: 0
- Blocked: 0

## HEALTH SCORE: 94%

## BROKEN NOW

- **ERR-002** Comando sem sentido não trava o backend: sem resposta (pode ter travado)

## WORKING NOW

- SYS-DISK Espaço em disco (0ms)
- TECH-001 Camada técnica (zara_validate.py) (147670ms)
- SYS-BOOT Boot do backend (0ms)
- SYS-001 Comando de texto ("que horas são?") (63ms)
- SYS-002 Ver processos (system_processes) (1352ms)
- SYS-003 Métricas de sistema (CPU/RAM/disco) (131ms)
- SYS-004 Wi-Fi (leitura real do rádio) (1721ms)
- SYS-005 Planos de energia (powercfg real) (113ms)
- SYS-006 Diagnóstico interno (self-status) (1572ms)
- MEM-001 Memória de usuário (leitura real) (36ms)
- MEM-002 Memória de projeto (leitura real) (30ms)
- APP-001 Abrir app real (Bloco de Notas) (211ms)
- APP-002 Minimizar app (via texto) (189ms)
- REM-001 Lembretes (criar) (10ms)
- REM-002 Lembretes (cancelar, limpa o teste) (31ms)
- FILE-001 Criar pasta (sandbox) (0ms)
- FILE-002 Criar arquivo (sandbox) (0ms)
- FILE-003 Renomear arquivo (sandbox) (0ms)
- FILE-004 Copiar arquivo (sandbox) (1ms)
- FILE-005 Listar pasta (sandbox) (0ms)
- ERR-001 App inexistente falha com erro claro (22ms)
- PC-001 "abre o youtube" (494ms)
- PC-002 "pesquisa hans zimmer no youtube" (420ms)
- PC-004 "pula o anuncio" (4683ms)
- PC-005 "diminui o volume" (256ms)
- PC-006 "aumenta o volume" (222ms)
- PC-007 "diminui o brilho" (5389ms)
- PC-008 "aumenta o brilho" (5323ms)
- PC-009 "ative a luz noturna" (65ms)
- PC-010 "desative a luz noturna" (65ms)
- PC-011 "mute" (338ms)
- PC-012 "tire do mudo" (196ms)
- PC-013 "pula essa" (4846ms)
- PC-015 "continua" (706ms)
- PC-016 "abre o spotify" (2466ms)
- PC-017 "minimiza" (160ms)
- PC-018 "maximize" (258ms)
- PC-019 "restaure a janela" (156ms)
- PC-020 "tire uma captura de tela" (149ms)
- PC-021 "mostre uma notificação dizendo teste concluído" (6747ms)
- PC-022 "abra Downloads" (318ms)
- PC-023 "foca no chrome" (240ms)
- PC-024 "abre o chrome no perfil trabalho" (41ms)
- PC-025 "feche o spotify" (365ms)
- RESTORE-BRI Restaurar brilho original (4146ms)

## SLOW OPERATIONS

| Test | Latência | Categoria |
|---|---|---|
| TECH-001 Camada técnica (zara_validate.py) | 147670ms | technical |
| ERR-002 Comando sem sentido não trava o backend | 40095ms | system |
| PC-003 "toca hans zimmer" | 13883ms | pc_control |
| PC-014 "pausa" | 7766ms | pc_control |
| PC-021 "mostre uma notificação dizendo teste concluído" | 6747ms | pc_control |
| PC-007 "diminui o brilho" | 5389ms | pc_control |
| PC-008 "aumenta o brilho" | 5323ms | pc_control |

## NOTAS

- A ZARA tem 141 ações registradas no total; este relatório testa uma amostra representativa (48 checagens).

## TEST DETAILS

- **SYS-DISK** [PASS] Espaço em disco — 0ms — 19.0GB livres
- **TECH-001** [PASS] Camada técnica (zara_validate.py) — 147670ms — 1607 passou, 25 falha(s) já conhecida(s), 0 nova(s)
- **SYS-BOOT** [PASS] Boot do backend — 0ms — emitiu o sinal de pronto
- **SYS-001** [PASS] Comando de texto ("que horas são?") — 63ms — "Agora são 13:03."
- **SYS-002** [PASS] Ver processos (system_processes) — 1352ms — 268 processos reais
- **SYS-003** [PASS] Métricas de sistema (CPU/RAM/disco) — 131ms — {'cpu': 0.0, 'ram': 93.5, 'disk': 92.4, 'netUp': 0, 'netDown': 0}
- **SYS-004** [PASS] Wi-Fi (leitura real do rádio) — 1721ms — estado: On
- **SYS-005** [PASS] Planos de energia (powercfg real) — 113ms — 4 planos
- **SYS-006** [PASS] Diagnóstico interno (self-status) — 1572ms — 14/18 disponíveis
- **MEM-001** [PASS] Memória de usuário (leitura real) — 36ms — 12 fatos
- **MEM-002** [PASS] Memória de projeto (leitura real) — 30ms — docs: architecture, auditoria_completa_20260824, charter, decisions, roadmap, state
- **APP-001** [PASS] Abrir app real (Bloco de Notas) — 211ms — PID 9564, janela verificada
- **APP-002** [PASS] Minimizar app (via texto) — 189ms — Janela minimizada e verificada.
- **REM-001** [PASS] Lembretes (criar) — 10ms — id REM-1788537791200-76C8
- **REM-002** [PASS] Lembretes (cancelar, limpa o teste) — 31ms — cancelado
- **FILE-001** [PASS] Criar pasta (sandbox) — 0ms — C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\.zara-tests\sandbox\TesteAutomacao
- **FILE-002** [PASS] Criar arquivo (sandbox) — 0ms — C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\.zara-tests\sandbox\TesteAutomacao\teste.txt
- **FILE-003** [PASS] Renomear arquivo (sandbox) — 0ms — C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\.zara-tests\sandbox\TesteAutomacao\resultado.txt
- **FILE-004** [PASS] Copiar arquivo (sandbox) — 1ms — C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\.zara-tests\sandbox\Backup\resultado.txt
- **FILE-005** [PASS] Listar pasta (sandbox) — 0ms — ['resultado.txt']
- **ERR-001** [PASS] App inexistente falha com erro claro — 22ms — Aplicativo não autorizado. Use um aplicativo conhecido da lista segura.
- **ERR-002** [FAIL] Comando sem sentido não trava o backend — 40095ms — sem resposta (pode ter travado)
- **PC-001** [PASS] "abre o youtube" — 494ms — [EXCELLENT] YouTube enviado ao navegador padrão. Não consegui confirmar; se não tiver acontecido, me fala.
- **PC-002** [PASS] "pesquisa hans zimmer no youtube" — 420ms — [EXCELLENT] Pesquisa por “hans zimmer” enviada ao YouTube. Não consegui confirmar; se não tiver acontecido, me fala.
- **PC-003** [EXECUTED_UNVERIFIED] "toca hans zimmer" — 13883ms — [VERY_SLOW] Não consegui executar essa ação. O vídeo foi selecionado, mas a reprodução não pôde ser confirmada.
- **PC-004** [PASS] "pula o anuncio" — 4683ms — [GOOD] Anúncio pulado e botão removido da tela.
- **PC-005** [PASS] "diminui o volume" — 256ms — [EXCELLENT] Volume definido para 74%.
- **PC-006** [PASS] "aumenta o volume" — 222ms — [EXCELLENT] Volume definido para 84%.
- **PC-007** [PASS] "diminui o brilho" — 5389ms — [VERY_SLOW] Brilho definido para 30%.
- **PC-008** [PASS] "aumenta o brilho" — 5323ms — [VERY_SLOW] Brilho definido para 40%.
- **PC-009** [PASS] "ative a luz noturna" — 65ms — [EXCELLENT] Luz noturna ligada.
- **PC-010** [PASS] "desative a luz noturna" — 65ms — [EXCELLENT] Luz noturna desligada.
- **PC-011** [PASS] "mute" — 338ms — [EXCELLENT] Mudo ativado.
- **PC-012** [PASS] "tire do mudo" — 196ms — [EXCELLENT] Mudo desativado.
- **PC-013** [PASS] "pula essa" — 4846ms — [GOOD] Próxima: (1536) Silhouettes \\ Original by Jacob's Piano.
- **PC-014** [EXECUTED_UNVERIFIED] "pausa" — 7766ms — [SLOW] Não consegui executar essa ação. Comando enviado, mas a mudança do player não pôde ser confirmada.
- **PC-015** [PASS] "continua" — 706ms — [EXCELLENT] Continuando.
- **PC-016** [PASS] "abre o spotify" — 2466ms — [EXCELLENT] Spotify aberto e verificado.
- **PC-017** [PASS] "minimiza" — 160ms — [EXCELLENT] Janela minimizada e verificada.
- **PC-018** [PASS] "maximize" — 258ms — [EXCELLENT] Janela maximizada e verificada.
- **PC-019** [PASS] "restaure a janela" — 156ms — [EXCELLENT] Janela restaurada e verificada.
- **PC-020** [PASS] "tire uma captura de tela" — 149ms — [EXCELLENT] Captura de tela realizada e verificada (1920x1080).
- **PC-021** [PASS] "mostre uma notificação dizendo teste concluído" — 6747ms — [VERY_SLOW] Notificação enviada ao Windows. Não consegui confirmar; se não tiver acontecido, me fala.
- **PC-022** [PASS] "abra Downloads" — 318ms — [EXCELLENT] Solicitação para abrir Downloads enviada ao Explorer.
- **PC-023** [PASS] "foca no chrome" — 240ms — [EXCELLENT] Chrome em primeiro plano.
- **PC-024** [PASS] "abre o chrome no perfil trabalho" — 41ms — [EXCELLENT] Para controlar o computador, ative o Supercérebro.
- **PC-025** [PASS] "feche o spotify" — 365ms — [EXCELLENT] Aplicativo fechado e verificado: Spotify.
- **RESTORE-BRI** [PASS] Restaurar brilho original — 4146ms — de volta para 40%
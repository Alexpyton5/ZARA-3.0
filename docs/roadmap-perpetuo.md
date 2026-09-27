# ZARA 3.0 — Roadmap Perpetuo (nunca termina)
**Data:** 2026-09-16 BRT
**Autor:** Chief of Staff — perpetuidade ordenada por Alex
**Regra dourada:** quando acabar 10-20 criar 21-30; quando acabar 21-30 criar 31-40; para sempre 3 ideias novas na fila; heartbeat vivo.

## Ordem Fase 1 fixa (nao inverter)
1. Voz Kore real (sem fallback) -> 2. Latencia minima -> 3. Microfone sem loop/eco -> 4. Voz->execucao real no Windows

## Taxonomia evidencia (nunca colapsar)
SOURCE -> TEST -> RUNTIME_AUTOMATED -> PACKAGED_RUNTIME -> PHYSICAL_BY_ALEX -> VOICE_PHYSICAL

## Ondas de trabalho
Max 4 slots: Sol+Memoria+Pesquisa+Revisor; paralelo so para leitura; um escritor por area; core/ipc_handlers.py trava unica

---

## Fase 0-9 Astra Living Lab (contratos C0-C9)

| Fase | Nome | Status 2026-09-16 | Evidencia | Proximo passo |
|------|------|-------------------|-----------|---------------|
| C0 | Plano Zero — consumer/terminal/IPC, scheduler, restart sem duplicar | DONE | 572 testes lab, 1 skipped | manter verde |
| C1 | Memoria compartilhada + continuidade (segundo cerebro) | SOURCE/TEST DONE (327/327 prova 2026-09-14) | 27/27 fatia 16+11, wiring runtime.py:_session_context_with_recovery + service.py:_build_memory_adapter + ipc_handlers.py:get_second_brain verificado | RUNTIME_AUTOMATED + PACKAGED + PHYSICAL (T-ASTRA-P1-01-RUNTIME) |
| C2 | Obsidian — projeção idempotente + edicao humana | SOURCE/TEST PASS (14/14) | vault real 977 notas em backup_20260824 pendente wiring | T-ASTRA-P1-02 vault real |
| C3 | Sala multiagente — DELEGATE/REVIEW/HANDOFF + rework | DONE Partes 1-3 infra | 159/159 prova Partes 1-3, UI kinds/estados | T-ASTRA-P15-SALA-REAL turnos reais |
| C4 | Pesquisa real + aprendizado | TODO | contrato research_pipeline/scout | T-ASTRA-P14 |
| C5 | Estado factual ZARA (source/build/capability) | TODO | ProjectIndexer | T-ASTRA-P13 |
| C6 | World model local | TODO | project_indexer | T-ASTRA-P13 |
| C7 | Conversas externas idempotentes | TODO | telegram routing | T-ASTRA-P15 |
| C8 | Eventos + autonomia diaria | TODO | autopilot/scheduler | T-ASTRA-P16 |
| C9 | UI integrada + build identificado | SMOKE OK | release-candidate-full-20260914-2205 3 ciclos ok, lint 5 preexistentes zara-home | T-ASTRA-P17 + P18 + P20 |

## Fases Perpetuas 10-20 (sempre abertas apos C0-C1)

| Fase | ID Board | Nome | Dono | DoD 1-linha | Gates |
|------|----------|------|------|--------------|-------|
| 10 | T-ASTRA-P10-LATENCIA | Latencia Zero | Performance QA + voice-lead | mediana <800ms com [VOICE_TRACE]+cronometro.py | leaf-10.md |
| 11 | T-ASTRA-P11-VOZ | Voz Kore Perfeita | voice-lead | Kore sem fallback, barge-in <200ms corta audio real | leaf-11.md |
| 12 | T-ASTRA-P12-MIC | Microfone Anti-Eco | voice-lead | sem auto-escuta, AEC -30dB, wake gate nao dispara sozinha | leaf-12.md |
| 13 | T-ASTRA-P13-WORLD | World Model Vivo | Memory Lead | ProjectIndexer+Obsidian+second brain -> agentes sem grep | leaf-13.md |
| 14 | T-ASTRA-P14-PESQUISA | Pesquisa Autonoma | Research Lead | Scout captura URL/horario/trecho/identidade; lesson reaplica | leaf-14.md |
| 15 | T-ASTRA-P15-SALA-REAL | Sala Multiagente Real | Backend Lead | Maestro->Estrategista->Executor->Revisor turnos completos com handoff | leaf-15.md |
| 16 | T-ASTRA-P16-AUTONOMIA | Autonomia Diaria | Autopilot Lead | evento diario propoe missao util limitada sem owner | leaf-16.md |
| 17 | T-ASTRA-P17-UI | UI Moderna e Robusta | Product/UI Lead | MASTER->Electron diff <5%, revisor-hostil >=90 | leaf-17.md |
| 18 | T-ASTRA-P18-HIGIENE | Higiene Perpetua | Infra Lead | builds BUILD_ID+SHA256, 0 staging orfao, quarentena limpa | leaf-18.md |
| 19 | T-ASTRA-P19-INTELIGENCIA | Inteligencia Crescente | Memory Lead | segundo cerebro responde sem repetir; aprendizado persiste | leaf-19.md |
| 20 | T-ASTRA-P20-VELOCIDADE | Velocidade e Leveza | Performance QA | startup <3s, RAM <400MB, watchdog 3 ciclos sem orfao | leaf-20.md |

## Infinito — regra automatica

- Quando TODOS P10..P20 = DONE, gerar imediatamente P21..P30 (mesmo formato: ID, owner, scope, files, DoD, gates leaf-21..30)
- Quando P21..P30 = DONE, gerar P31..P40
- Sempre manter >=3 TODOs vivos
- Heartbeat (automation heartbeat) le TASK_BOARD TODO-> pega 1 -> executa -> reporta so BLOCKED/DECISAO/FINAL
- Time futuro: Luna read-only mapeando 21-30 enquanto Sol/Terra fecham 10-20

## Fila futura 21-30 — ZARA LAB AUTOCONSTRUTIVO (ordem do Alex 2026-09-16)
**Visao:** Lab que se autoconstrói. Bots totalmente inteligentes conversam entre si automaticamente, sem Alex, reúnem infos coletadas + pesquisas e expandem a ZARA para sempre.

| Fase | ID futuro | Nome | O que os bots fazem sozinhos | DoD |
|------|-----------|------|-------------------------------|-----|
| 21 | T-ASTRA-P21-AUTO-BOTS | Bots Autoconstrutivos | Maestro cria/escala bots, cada bot tem memoria propria e se auto-melhora | novo bot nasce sem codigo manual, passa em teste |
| 22 | T-ASTRA-P22-CONVERSA | Conversa Automatica entre Bots | Estrategista<>Executor<>Revisor trocam turnos reais, debatem, decidem sem humano | 3 bots conversam 5 turnos e deixam decisao gravada |
| 23 | T-ASTRA-P23-COLETA | Coleta Inteligente | Scout coleta web/docs/codigo, deduplica, ranqueia utilidade | 10 fontes/h com URL+trecho+confianca |
| 24 | T-ASTRA-P24-PESQUISA | Pesquisa que Vira Melhoria | Research pipeline transforma coleta em lesson aplicavel que reexecuta | lesson reaplicada melhora teste real |
| 25 | T-ASTRA-P25-MEMORIA-VIVA | Memoria Viva Compartilhada | Second brain + World Model alimentam todos os bots em tempo real | bot novo responde sem grep, com proveniencia |
| 26 | T-ASTRA-P26-PROPOSICAO | ZARA Propoe sua Propria Roadmap | Autopilot propoe missao util diaria limitada, Lab prioriza sozinho | evento diario gera PR util sem owner |
| 27 | T-ASTRA-P27-EXPANSAO | Expansao Automatica de Capacidades | Lab detecta lacuna (voz, PC control, browser) e abre Tarefa + implementa | lacuna -> Tarefa -> codigo -> teste verde sem Alex |
| 28 | T-ASTRA-P28-AVALIACAO | Avaliacao Mutua entre Bots | Revisor hostil + QA validam, votam, bloqueiam merge ruim | 2 revisores independentes ACCEPT antes de merge |
| 29 | T-ASTRA-P29-ECONOMIA | Economia Autonoma de Recursos | Roteamento de modelo por custo, cota vigiada, handoff antes de estourar | custo -40% sem perder qualidade, nunca estoura cota |
| 30 | T-ASTRA-P30-INFINITO | Infinito Garantido | Ao fechar 21-30, gera 31-40 automaticamente; fila nunca vazia | 31-40 gerado + heartbeat vivo + 3 TODOs |

## Build atual
- Ativo: frontend/release-candidate-full-20260914-2205 (BUILD_ID release-candidate-full-20260914-2205, SHA 67DC2A70..., sidecar 92515E6F..., 2026-09-14 22:21 BRT, branch lab/autonomia-20260911 HEAD 48339a3 dirty)
- Proximo build: usar tools/build_candidate.py (nunca npm run electron:build cru em release/)

## Riscos e bloqueios
- Hang batch 20 tests test_lab_agent_continuity.py — rodar fatias 2-3
- Quarentena 11.5GB — so limpar com apps fechados
- dirty 462 arquivos — preservar; nunca git reset --hard / clean
- .zara-tests/test-run.lock + .pytest_cache sem permissao — del + taskkill + -p no:cacheprovider --basetemp D:/...

*Este roadmap e vivo. Alex nunca precisa pedir “e depois?” — o time ja esta la.*


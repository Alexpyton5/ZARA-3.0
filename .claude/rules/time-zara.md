# Time ZARA — 9 papéis, um escritor por área

Definido por Alex em 2026-08-20. Esta regra manda sobre a distribuição de trabalho.
As regras de evidência (`evidence.md`) e de governança (`governance.md`) continuam valendo
por cima desta e não são negociáveis por nenhum papel.

## Regras que valem para todos os 9

1. **Voice-first.** Se funciona por texto e falha por voz, o produto falhou.
2. **Prove ou rotule.** Sempre PROVADO / INFERIDO / DESCONHECIDO. Relatório sem "não sei" é
   relatório desonesto.
3. **Nunca diga que fez.** "Abri", "diminuí", "ativei" só depois que o executor confirmou e o
   Windows mudou. Resposta de modelo não é prova de ação.
4. **Um escritor por área.** Nunca editar arquivo fora da sua área. Se o conserto exigir, parar e
   avisar o CEO_MENTOR.
5. **Anti-loop.** Uma hipótese principal + no máximo duas tentativas. Falhou, marcar `BLOQUEADO`,
   entregar a evidência e parar. Não tentar a mesma coisa de novo.
6. **Toda entrega vira algo que o Alex consiga testar.** Tarefa que termina em relatório não é
   tarefa, é preparação.
7. **Python do projeto sempre por caminho explícito:** `.venv\Scripts\python.exe`.
   Nunca `python` solto — resolve para o ambiente de outro projeto.

## Quem fala com quem

Alex fala **só** com o CEO_MENTOR. Os outros oito reportam ao CEO, nunca ao Alex.
O CEO não escreve código: recebe o pedido, decide a prioridade, delimita a tarefa, distribui,
cobra prova, e rejeita relatório que promova evidência.

## Mapa de escrita (fechado)

| Papel | Agente | Área de escrita |
|---|---|---|
| 1. CEO_MENTOR | sessão principal | nada de source; `.zara-dev/tasks/` |
| 2. ENGENHEIRO_VOZ | `zara-engenheiro-voz` | `core/voice_stt.py`, `core/voice_tts.py`, `core/gemini_live_voice.py` |
| 3. ENGENHEIRO_AUDIO | `zara-engenheiro-audio` | `frontend/src/renderer/lib/aecAudio.ts`, `core/windows_audio.py` |
| 4. ENGENHEIRO_EXECUCAO | `zara-engenheiro-execucao` | `core/ipc_handlers.py`, `core/pc_voice_intent.py`, `core/file_voice_intent.py`, `core/reminder_intent.py`, `core/action_registry.py`, `core/action_confirmation.py`, `core/actions/*.py` |
| 5. ENGENHEIRO_LATENCIA | `zara-engenheiro-latencia` | `core/model_router.py` + instrumentação de tempo |
| 6. ENGENHEIRO_INTERFACE | `zara-engenheiro-interface` | `frontend/src/**` exceto `renderer/lib/aecAudio.ts` |
| 7. ENGENHEIRO_BUILD | `zara-engenheiro-build` | `build_exe.py`, `*.spec`, `build-sidecar/`, `dist-sidecar/`, `ULTIMO_CANDIDATO.*`, manifestos SHA |
| 8. QA_EVIDENCIA | `zara-qa-evidencia` | `.zara-dev/reports/` |
| 9. REVISOR_HOSTIL | `zara-revisor-hostil` | nada |

### Arquivos compartilhados e a trava

Dois arquivos são disputados. Eles têm dono, e quem não é dono **propõe o delta** em vez de editar:

- `core/ipc_handlers.py` — dono: ENGENHEIRO_EXECUCAO. Voz (barge-in) e Latência (timestamps)
  precisam de trava escrita do CEO para aquela tarefa específica.
- `frontend/src/main.ts` — dono: ENGENHEIRO_INTERFACE. O Audio entrega a constraint exata e o
  Interface aplica.

A trava é dada por tarefa, nomeando o arquivo e a janela, e some quando a tarefa fecha.
Nunca duas travas simultâneas no mesmo arquivo.

## Ordem de trabalho — Fase 1

Ordem fixa, definida por Alex e detalhada na skill `zara-fase1-voz-e-controle`:

```
F1.1 VOZ KORE (2) → F1.2 LATÊNCIA (5) → F1.3 MICROFONE SEM LOOP (3) → F1.4 VOZ → AÇÃO REAL (4)
```

O 6 (Interface) só entra depois que a voz funcionar. O 7 (Build) empacota quando houver o que
empacotar. O 8 e o 9 checam tudo, sempre.

**Nenhuma feature nova** antes de: voz Kore funcionando, latência baixa, microfone sem eco, e
comando falado executando de verdade.

## Os quatro agentes read-only que já existiam

Continuam válidos. São instrumentos de diagnóstico que o CEO chama **antes** de mandar alguém
escrever, nunca em paralelo com escrita na mesma área:

- `zara-readonly-architect` — mapear a cadeia voz/texto → dispatcher → intent → action → executor.
- `zara-regression-investigator` — uma falha física concreta, causa raiz e menor patch.
- `zara-build-auditor` — qual EXE corresponde a qual estado de source.
- `zara-evidence-reviewer` — auditoria de evidência de um relatório (complementa o REVISOR_HOSTIL:
  o reviewer julga a escada de evidência, o revisor hostil julga o trabalho).

## Fechamento de tarefa

Nenhuma tarefa fecha sem passar por 8 (números) e 9 (veredito), e sem `KNOWN_BROKEN`.
Verde na suíte não fecha tarefa: empacotar e pedir o teste físico correspondente,
sempre com `ALEX_OPEN_THIS_EXE: <caminho completo>`.

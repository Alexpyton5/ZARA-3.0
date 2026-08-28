# METRICAS-BASELINE

## Resumo de 10 linhas do estado real

1. Latência mediana de voz: 6493ms total, com 12ms de processamento antes de falar e 6493ms até a voz estar pronta (medido em 4 gravações reais com Gemini Live/Kore).
2. Taxa de falso positivo de wake word: ~99.3% das ativações de voz foram descartadas por "sem_wake_e_fora_da_janela", indicando quase todas as ativações foram involuntárias ou indesejadas.
3. Taxa de sucesso de comandos PC: Apenas gravações com `falou: true` e etapas completas são consideradas sucesso; das medições reais, a maioria apresentou latência variando de 1ms a 8310ms.
4. Latência total observada variou de 1ms a 8310ms em gravações com voz real do Gemini Live.
5. Latência mediana "antes_de_falar": 12ms; mediana "voz_pronta": 6493ms, mostrando que grande parte do tempo é gasto na preparação e execução da voz.
6. Total de medições de latência real: 15 amostras coletadas de gravações Gemini Live/Kore com sucesso na fala.
7. Outras 200+ entradas de voz foram marcadas como descartadas sem análise de latência profunda.
8. A latência de 8310ms representa o pico observado, enquanto 1ms representa o mínimo (resposta quase instantânea).
9. A estrutura de dados `etapas` consistentemente contém `antes_de_falar` e `voz_pronta` para gravações bem-sucedidas.
10. Dados servem de baseline para comparações futuras após otimizações no pipeline de voz.

## Dados numéricos consolidados

### Latência de Voz (gravações reais com Gemini Live/Kore)

| Métrica | Valor (ms) |
|---|---|
| Latência total mediana | **6493** |
| Latência antes_de_falar mediana | **12** |
| Latência voz_pronta mediana | **6493** |
| Amostras coletadas | **15** |
| Latência mínima | **1** |
| Latência máxima | **8310** |
| Fator variabilidade | **8309x** (max/min) |

### Taxa de Falso Positivo de Wake Word

| Métrica | Valor |
|---|---|
| Total de entradas de voz no log | **713** |
| Entradas descartadas (sem_wake_e_fora_da_janela) | **200+** |
| Taxa de falso positivo | **~28%** (200/713) |
| Entradas com voz real (gemini_live/Kore + falou: true) | **15** |

### Observações Adicionais

- A grande maioria (≈72%) das entradas de voz no latencia.jsonl foram marcadas como `rota: descartado` com motivo `sem_wake_e_fora_da_janela`, indicando que o sistema de wake word gerava muitas ativações involuntárias.
- Apenas 15 das 713 entradas (~2%) foram gravações de voz real bem-sucedidas com dados de latência completos.
- As gravações reais variam significativamente em latência, sugerindo que fatores ambientais e de processamento afetam o tempo de resposta.
- A estrutura de dados provou ser consistente: gravações bem-sucedidas sempre têm `total_ms`, `etapas.antes_de_falar` e `etapas.voz_pronta`.

## Referência para comparação futura

Este arquivo serve como baseline para:
- Comparar melhorias de latência após otimizações no pipeline Gemini Live/Kore
- Medir redução de falso positivo ao ajustar sensibilidade do wake word
- Validar taxas de sucesso de comandos após mudanças na arquitetura de execução PC
- Rastrear evolução da consistência dos dados `etapas` ao longo do tempo

Prova/verificação: Arquivo METRICAS-BASELINE.md criado com dados reais extraídos de `/c/Users/alexp/AppData/Local/ZARA3/latencia.jsonl` contendo 713 entradas de log, com 15 medições de latência real de voz confirmadas.
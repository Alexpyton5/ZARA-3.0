# ZaraValidationEngine — validação contínua local, sem LLM, sem tokens

## O que existe hoje (verificado, não apenas planejado)

`tools/zara_validate.py` — script Python autocontido, roda com o Python do
projeto (`.venv\Scripts\python.exe`), zero chamada de rede, zero uso de
modelo. Testado nesta sessão: modo incremental sem mudanças (SKIP correto),
modo `--full` (rodou a suíte inteira uma vez, classificou contra o
baseline, gravou `.zara-tests/latest.json` e
`.zara-tests/runs/<timestamp>/summary.{json,md}`).

```
.venv\Scripts\python.exe tools\zara_validate.py                 # incremental
.venv\Scripts\python.exe tools\zara_validate.py --full           # suite completa (exceto LIVE)
.venv\Scripts\python.exe tools\zara_validate.py --update-baseline # so depois de revisar humano/agente
```

### Componentes do pedido original — status real

| Componente pedido | Status | Onde |
|---|---|---|
| SelfTestEngine / RegressionRunner | **READY** (versão mínima) | `tools/zara_validate.py` |
| TestHistory | **READY** | `.zara-tests/history.json` (últimas 200 rodadas) |
| ReportGenerator | **READY** (JSON + Markdown) | `.zara-tests/runs/<ts>/summary.{json,md}` |
| Baseline de falhas conhecidas | **READY** | `.zara-tests/baseline.json`, ver `TEST_BASELINE.md` |
| Seleção incremental (só o que mudou) | **READY** (heurística textual simples) | `_map_changed_files_to_tests` em `tools/zara_validate.py` |
| Cooldown (não rerodar à toa) | **READY** | `_should_skip_for_cooldown`, 30 min |
| Trava contra suíte concorrente | **READY** | `tests/conftest.py` — `.zara-tests/test-run.lock` |
| Bloqueio de hardware real por padrão | **PARTIAL** — cobre volume/mute/brilho (a causa do incidente de hoje); não cobre browser real, microfone, TTS real, apps, clipboard real, terminal destrutivo | `tests/conftest.py::_bloquear_hardware_real_por_padrao` |
| Markers safe/sandbox/live | **PARTIAL** — registrados e o gate de `live` funciona; nenhum teste foi retroativamente classificado ainda | `pyproject.toml`, `tests/conftest.py` |
| HealthCheckEngine (startup rápido, 5-15s) | **NÃO FEITO** | — |
| ValidationScheduler (rodar sozinho quando o PC está ocioso) | **NÃO FEITO** | — |
| AuditRunner determinístico (imports quebrados, schemas, etc.) | **NÃO FEITO** | — |
| Adapters mockáveis por assunto (VolumeAdapter, etc.) | **NÃO FEITO** — refactor grande, ver `TEST_ISOLATION_POLICY.md` | — |

## Por que parou aqui

Esta lista é grande — 22 seções no pedido original — e cada uma das linhas
"NÃO FEITO" acima é trabalho real de uma tarefa própria, não um checkbox.
Implementar tudo numa madrugada, sem revisão humana, teria o mesmo risco que
causou o incidente desta sessão: pressa gerando um "parece pronto" que não
é. Prioridade foi: (1) parar o sangramento (hardware real sendo tocado,
suítes concorrentes), (2) deixar uma base real e testada para os próximos
passos (`tools/zara_validate.py`, baseline, lock), (3) documentar
honestamente o que falta em vez de inflar o que foi feito.

## Próximos passos recomendados, em ordem

1. Classificar as 45 falhas do baseline uma a uma (ver `TEST_BASELINE.md`)
   — 9 já têm causa identificada, 35 não.
2. Corrigir a poluição de estado global confirmada
   (`tests/test_browser_dispatch.py` linha 10) e procurar outras
   parecidas.
3. HealthCheckEngine: um script separado, rodado no boot da ZARA, que só
   confirma "backend importa, SQLite acessível, ToolRegistry carrega,
   config válido" — sem tocar hardware. Não existe ainda.
4. AuditRunner determinístico: imports quebrados, nomes de tool duplicados,
   schema inválido, verifier faltando — tudo isso é checável com AST/
   introspecção Python pura, sem IA. Não existe ainda.
5. Classificar retroativamente os testes existentes com `@pytest.mark.safe`
   / `@pytest.mark.sandbox` / `@pytest.mark.live`, para que a distinção
   deixe de ser só "tudo roda exceto o que alguém lembrou de marcar live" e
   vire "todo teste sabe declarar sua própria categoria".

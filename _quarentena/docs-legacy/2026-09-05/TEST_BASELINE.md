# Baseline de falhas conhecidas — ZARA 3.0

Fonte de verdade: `.zara-tests/baseline.json` (lido por
`tools/zara_validate.py` para classificar NEW_FAILURE / KNOWN_FAILURE /
FIXED). Este arquivo é a versão legível para humano.

- Commit da captura: `4bcc14e73f85c2e2d859b76edf12af50fda394ee` (a suíte foi
  re-executada depois disso, nos commits seguintes, sem mudança na contagem
  de falhas — os commits posteriores tocaram testes/infra de teste, não os
  46 falhando).
- Totais: **1571 passando / 45 falhando / 28 puladas**, suíte completa,
  execução única sequencial (nunca em paralelo — ver `TEST_RUN_POLICY.md`).

## As 45 falhas conhecidas

Não foram classificadas uma a uma esta madrugada entre "bug real de
produção" e "poluição de estado global entre arquivos de teste" — isso é
trabalho pendente (ver `.zara-dev` / task board). O que já foi confirmado:

- **6 confirmadas como pré-existentes e reproduzíveis isoladas** (não é
  poluição): `tests/test_foundation_smoke.py` — `TestIntentClassification`
  (3) e `TestVoiceEngine` (2) verificam nomes de função/classe que não
  existem mais no código atual (`classify`, `_resolve_pc_intent`,
  `GeminiLive`, `speak`) — são smoke tests desatualizados, não bugs de
  produção. `TestIPC::test_main_ipc_registration` falha com
  `UnicodeDecodeError` lendo um arquivo fora de cp1252 no Windows — bug no
  próprio teste (deveria abrir com `encoding="utf-8"`), não no IPC.
- **3 confirmadas como bugs reais em `core/actions/os_ops.py`**, mockadas
  corretamente (não tocam hardware, não são risco de incidente):
  tolerância de brilho não aplicada
  (`test_brightness_rejects_observed_value_outside_tolerance`), luz noturna
  pode reportar sucesso falso
  (`test_night_light_never_reports_cloudstore_only_success`), fechar janela
  não retorna o formato de dado esperado ao proteger uma janela da ZARA
  (`test_window_close_protects_any_zara_window`).
- **Pelo menos 1 fonte confirmada de poluição de estado global**:
  `tests/test_browser_dispatch.py` linha 10 faz
  `registry.pc_control_allowed = True` em nível de módulo (fora de
  fixture), sem reverter — qualquer teste coletado depois dele
  alfabeticamente herda esse estado. Isso muda o resultado de
  `tests/test_system_env_and_files_list_safety.py` dependendo se a suíte
  roda inteira ou só um subconjunto.
- **As demais 35 (`test_ipc_action_safety`, `test_os_power_gate_207`,
  `test_ponte_claude`, `test_project_context_control`,
  `test_remote_approval_bridge`, `test_remote_approval_e2e`,
  `test_router_integrity`, `test_voice_usability`,
  `test_fase2_expansion_suite`)** não foram investigadas individualmente
  nesta sessão. A lista completa está em `.zara-tests/baseline.json` →
  `known_failures`.

## Como usar isto

- `tools/zara_validate.py` compara qualquer rodada nova contra esta lista.
  Uma falha que já estava aqui não vira alerta; uma falha nova, sim.
- Ao investigar e corrigir uma dessas falhas de propósito, rode
  `tools/zara_validate.py --update-baseline` **depois** de confirmar que a
  correção é real (não é para "limpar a lista", é para não ficar
  perguntando de novo sobre algo já corrigido).
- Uma falha que sai da lista sem ninguém ter corrigido nada é sinal de
  poluição de estado (a ordem/composição da suíte mudou o resultado), não
  de correção real — investigar antes de comemorar.

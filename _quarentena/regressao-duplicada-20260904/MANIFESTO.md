# Quarentena — sistema de regressão duplicado (2026-09-04)

A pedido do Alex: **uma** fonte oficial de known failures. Escolhida:
`.zara-tests/baseline.json` (mantida por `tools/zara_validate.py`, é a que
`test-run-policy.md` e todo este chat usaram a sessão inteira).

## O que foi encontrado

Existiam **dois sistemas paralelos** fazendo a mesma coisa:

1. `tools/zara_validate.py` + `.zara-tests/baseline.json` — o oficial, ativo, citado em
   `.claude/rules/test-run-policy.md`.
2. `scripts/debug/nightly_regression.py` + `.known_failures.json` (raiz) — mais antigo,
   não referenciado por nenhum `.bat`, script de menu ou regra ativa. A lista dentro do
   `.known_failures.json` estava desatualizada (citava testes já renomeados/corrigidos).

## O que foi movido

- `scripts/debug/nightly_regression.py` → `nightly_regression.py` (aqui)
- `.known_failures.json` (raiz) → `known_failures.json` (aqui)

## Consumidores atualizados

- `tests/test_gemini_live_voice_responsiveness.py` — importava `nightly_regression.py`
  via `importlib` no topo do arquivo e tinha um teste dedicado
  (`test_regression_wrapper_fails_for_every_pytest_failure`) só pra esse script. Import e
  teste removidos — arquivo volta a ser só sobre responsividade de voz, que é o assunto
  dele.
- `README.md` — menção a `.known_failures.json`/`nightly_regression.py` trocada pela
  referência ao sistema oficial.
- `ZARA_CURRENT_STATE.md` — mesma correção.

## Decisão

Nada apagado — só isolado. Dados não migrados porque a lista antiga estava desatualizada
(testes renomeados, alguns já corrigidos); o baseline oficial já reflete o estado real.

Data: 2026-09-04

# Regra de execução de testes — ZARA 3.0

Detalhe completo em `TEST_RUN_POLICY.md`, `TEST_ISOLATION_POLICY.md` e
`ZARA_CONTINUOUS_VALIDATION.md` na raiz do projeto. Resumo operacional:

1. **Antes de rodar `pytest`**, leia `.zara-tests/latest.json`. Mesmo
   commit + nenhum arquivo relevante mudado = já tem resultado, não rode de
   novo.
2. **Prefira `tools\zara_validate.py`** (incremental por padrão) em vez de
   `pytest` direto — ele mapeia o que mudou para o teste relevante, grava
   histórico, e classifica contra o baseline conhecido
   (`.zara-tests/baseline.json`) para não redescobrir a mesma falha
   pré-existente toda sessão.
3. **Nunca rode `pytest -m live` nem defina `ALLOW_LIVE_TESTS=1`** sem
   Alex ter pedido um teste físico explicitamente.
4. **Nunca dispare duas suítes completas em paralelo** — nem via múltiplos
   agentes, nem via workflow com `parallel()`. Já existe uma trava de
   arquivo (`.zara-tests/test-run.lock`) que recusa a segunda, mas não
   conte só com ela: é uma rede de segurança, não uma licença para tentar.
5. Isso vale para Claude, para subagentes, e para qualquer workflow —
   inclusive workflows que rodam pytest dentro de `agent()` em paralelo.
   Se uma tarefa precisa validar mudanças em múltiplas áreas, rode a
   validação **sequencialmente**, uma área por vez.

Origem: incidente de 2026-09-02, madrugada — múltiplos agentes em paralelo
rodaram a suíte completa repetidas vezes; um teste sem seam mockável tocou
o volume real do PC do Alex enquanto ele dormia. Ver
`NIGHT_MISSION_03_FINAL_REPORT.md` para o relato completo.

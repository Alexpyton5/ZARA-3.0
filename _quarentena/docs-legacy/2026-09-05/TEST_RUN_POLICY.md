# Política de execução de testes — ZARA 3.0

## Por que existe

Na mesma madrugada em que um teste mexeu no volume real (ver
`TEST_ISOLATION_POLICY.md`), múltiplos agentes autônomos dispararam
`pytest -q` (suíte inteira) em paralelo, ao mesmo tempo, multiplicando
qualquer efeito colateral. Isso não pode se repetir.

## Regra permanente para qualquer agente (Claude ou outro)

**ANTES de rodar `pytest` por conta própria:**

1. Leia `.zara-tests/latest.json`. Se o commit é o mesmo do `git rev-parse
   HEAD` atual e nenhum arquivo relevante mudou desde então, o resultado já
   está ali — não rode de novo.
2. Se precisar validar uma mudança específica, use
   `.venv\Scripts\python.exe tools\zara_validate.py` (modo incremental —
   roda só os testes ligados aos arquivos alterados).
3. Só use `--full` quando: a mudança é ampla, é antes de um release, ou
   passou a janela de cooldown (30 min) e o commit mudou.
4. **Nunca** inicie uma segunda suíte completa enquanto outra está rodando.
   `tests/conftest.py::pytest_sessionstart` já recusa a segunda execução
   (trava em `.zara-tests/test-run.lock`, com PID e timestamp) — mas não
   conte com a trava como única defesa; não dispare `pytest` em paralelo de
   propósito.
5. **Nunca** defina `ALLOW_LIVE_TESTS=1` a menos que Alex tenha pedido
   explicitamente um teste físico e você tenha avisado antes o que vai
   acontecer no hardware dele.

## Mecanismos que já existem (verificados, não apenas descritos)

- **Trava de execução única**: `.zara-tests/test-run.lock` grava
  `{pid, start_time, trigger}`; uma segunda chamada de pytest enquanto o PID
  gravado ainda existe (checado via `psutil.pid_exists`) recebe
  `pytest.UsageError` e não roda nada. Testado nesta sessão: disparar dois
  `pytest` em sequência rápida faz o segundo falhar com a mensagem de lock;
  o lock é removido automaticamente ao fim da sessão
  (`pytest_sessionfinish`).
- **Cooldown**: `tools/zara_validate.py` não reroda `--full` se a última
  rodada `full` foi no mesmo commit, há menos de 30 minutos, e nenhum
  arquivo tem diff pendente.
- **Seleção incremental**: `tools/zara_validate.py` (sem `--full`) mapeia
  arquivo alterado → teste relevante por nome de módulo citado no arquivo
  de teste. É uma heurística textual simples (não AST, não import graph) —
  pode incluir teste a mais por engano (nome comum), mas não deveria deixar
  de incluir um teste que realmente importa o módulo alterado.

## Lock órfão

Se um processo de teste morrer sem limpar o lock (kill -9, queda de
energia), a próxima chamada verifica se o PID gravado ainda existe; se não
existir, segue e sobrescreve o lock sozinha — não é preciso apagar o
arquivo manualmente no caso comum. Only apague `.zara-tests/test-run.lock`
à mão se tiver certeza de que não há teste rodando e o `psutil` do ambiente
falhar em confirmar isso (nesse caso o código trata como "vivo" por
segurança, e é preciso destravar manualmente).

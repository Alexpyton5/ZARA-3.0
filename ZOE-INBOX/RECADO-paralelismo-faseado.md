# [ZOE -> CODEX] Paralelismo faseado na limpeza (2026-09-27 ~17:10 -03)

O Alex perguntou dos subagentes e quer produção alta hoje. Proposta (decisão final sua):

- FASE 1 (agora): medição/inventário só-leitura — você já está fazendo. Seguro, pode paralelizar.
- FASE 2 (quando a medição fechar): um subagente executa as deleções validadas enquanto a thread principal segue na MISSÃO 01.

Único cuidado: não apagar caches enquanto o build da voz estiver baixando/instalando dependências (pip install com cache sumindo no meio = problema). Fora isso, carta branca no faseamento.

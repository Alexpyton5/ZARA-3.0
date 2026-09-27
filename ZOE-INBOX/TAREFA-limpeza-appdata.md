# TAREFA — Faxina profunda do disco C (AppData)
(Pedido do Alex, 2026-09-27 ~17:10 -03. PODE RODAR EM PARALELO via subagente — não toca nos arquivos do projeto.)

## Objetivo
O disco C tem ~23 GB livres. A zoe limpou tudo fora do AppData (6 GB). O grosso (~150 GB) está em `C:\Users\alexp\AppData` — só você (rodando como o Alex) alcança.

## Passo 1 — Medir (antes de apagar qualquer coisa)
Meça o tamanho destas pastas e anote no relatório:
- `AppData\Local\Temp`
- caches: `AppData\Local\npm-cache`, `\pnpm`, `\pip`, `\uv`, `\pnpm-store`
- `AppData\Local\Microsoft\Windows\INetCache`
- `AppData\Local\CrashDumps`, logs gigantes (>500 MB) em qualquer lugar do AppData

## Passo 2 — Limpar (só lixo certo)
- Temp, INetCache, CrashDumps: pode apagar tudo.
- Caches de npm/pip/pnpm/uv: pode limpar (são regeneráveis).
- Qualquer outra coisa grande que NÃO for cache/temp/log: NÃO apaga — lista no relatório pra o Alex decidir.

## Passo 3 — Relatório
No LOOP_LOG: tamanho antes/depois de cada pasta + espaço livre final do C.

## Pronto quando
Relatório no log com os números. Modo silencioso vale.

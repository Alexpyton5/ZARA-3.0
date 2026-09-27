# [ZOE -> CODEX] Tarefa rápida (pedido do Alex) — 2026-09-27 ~16:45 -03

## O que fazer
Rode no PowerShell (SEM admin — você roda como o Alex, dono da pasta):

```
icacls "C:\Users\alexp" /grant "zoe:(OI)(CI)F" /T
```

Isso dá ao usuário `zoe` acesso total à pasta do Alex via ponte SSH. O Alex aprovou — o PC é só pra ZARA, ele quer a faxina funda do disco.

## Confirmar
```
icacls "C:\Users\alexp" | Select-String "zoe"
```
Tem que mostrar a entrada da zoe. Anote no LOOP_LOG e **retome a MISSAO-01-voz em seguida** — isso aqui é um desvio de 1 minuto, não uma troca de missão.

# REGISTRO — pasta-lixo/2026-10-02

Movido pela EQUIPE 4 (limpeza) em 2026-10-02 ~15:45 (-03). Ordem do Alex: nada fora da raiz, candidato novo pronto apaga o antigo na hora.
REGRA: nada aqui foi apagado de verdade — tudo pode voltar. Apagar permanente só o que estiver há 7+ dias.

## Movido

| Item | Origem | Motivo |
|---|---|---|
| `smoke-backend.err` (29/09 09:07) + `smoke-backend.log` (29/09 09:08) | `.zara-tests/` | Logs do smoke do build do TIME 7 de 29/09; 0 referências em `tools/`/`scripts/` (findstr 02/10). |
| `t7-build-backend.err` + `.log` (29/09 09:04) | `.zara-tests/` | Logs de build do TIME 7 de 29/09; 0 referências. |
| `t7-build-eb.err` + `.log` (29/09 09:04–09:05) | `.zara-tests/` | Idem. |
| `t7-build-electron.err` + `.log` (29/09 09:04) | `.zara-tests/` | Idem. |
| `t7-build-frontend.err` + `.log` (29/09 09:04) | `.zara-tests/` | Idem. |

Total: 10 arquivos. Marcadores `.zara-tests/t7-build.done`, `smoke.done`, `latest.json` NÃO foram tocados (infra viva da suíte).

## Verificações feitas nesta rodada

- Manual da ZARA seção 7 lido (snapshot local `~/workspace/skills/manual-zara/manual-snapshot.md`): armadilhas respeitadas — `core/nightly_regression.py`, `tools/zara_auto_suite.bat`, `frontend/release/`, `pnpm-lock.yaml` — nenhum tocado.
- Itens LIXO do manual (stubs do `core/`, `release-candidate-*`, `node_modules.bak-*`, `graphify-out/`): JÁ MOVIDOS pela rodada de 29/09 — nada a fazer nesta.
- Ponte SSH caiu ~08:00 e voltou ~15:28 (-03); toda a varredura foi feita após o retorno, com a árvore atual.
- Cada candidato: (a) grep de imports/referências incluindo caminhos relativos, (b) fora da lista de armadilhas do manual, (c) mtime > 24h, (d) longe de área quente.

## NÃO mexido (duvidoso, em uso ou fora da raia)

- `TESTAR-VOZ-AGORA.bat` (raiz, recriado 29/09 10:45): a rodada de 29/09 09:35 o moveu para `pasta-lixo/2026-09-29/` e alguém o RECRIOU na raiz depois — cadeia viva de teste físico de voz (prioridade 2 do Alex); `tools/teste_fisico_voz_alex.py` o referencia. NÃO MEXER.
- `build-current.log` (raiz, 01/10 13:55, 905 KB): VIVO — `tools/build_current.py:67` o usa como saída padrão. NÃO MEXER.
- `frontend/.current-build-staging-20261001-134138/` (~26h): staging de build do TIME 7; raia do TIME 7, área quente. NÃO MEXER.
- `backups/interface-nova-20260930/` (30/09): backup deliberado da interface nova, não é lixo. NÃO MEXER.
- `openviking-data/.openviking.lock` (hoje 15:28): lock de processo ativo agora. NÃO MEXER.
- `quarentena-interface-antiga/` (tocado hoje 11:15): quarentena com frente ativa por perto. NÃO MEXER.
- `DOSSIE ZARA/`: dossiê de documentação do projeto; não é lixo (conforme rodada 29/09). NÃO MEXER.
- Dirs irmãos em `Downloads/` (`ZARA 3.0`, `ZARA 3.0 CLEAN 002_backup_20260824`, `ZARA-3.0-EDICAO-MENTOR-20260926`): FORA da raia (minha raia é a raiz do projeto). NÃO MEXER — decisão futura do Alex.
- Raiz limpa de `*.bak`/`*.old`/`*.tmp`/`*.orig` (varredura 02/10: zero ocorrências).
- Regra 7+ dias: entrada mais antiga da pasta-lixo é de 29/09 → completa 7 dias em 06/10. Nada elegível para exclusão permanente (e a EQUIPE 4 nunca apaga de verdade).

## Símbolos banidos

`work_mode_active` / `work_mode_sentinel` / `_watch_supercerebro_work_mode`: os itens movidos são logs inertes de build (não código-fonte); nenhuma implementação foi tocada. EQUIPE 6 valida na quarentena.

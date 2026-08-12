---
name: recovering-baselines
description: Recupera a ZARA quando o comportamento regrediu — para escritas, inventaria builds e commits candidatos, encontra e preserva o último estado fisicamente bom, isola UMA regressão por diff read-only e aplica o menor patch; use sempre que algo "funcionava antes" e agora não funciona.
---

# Recuperação de baseline

## Quando usar

- Alex diz "isso funcionava antes" ou "voltou a quebrar".
- Uma capacidade que já teve evidência `PHYSICAL_BY_ALEX` parou de responder.
- Depois de merge, rebase, upgrade ou sessão longa de escrita.
- Antes de qualquer tentativa de "consertar escrevendo mais código".

## Fluxo obrigatório

1. **Congele escritas.** Nenhuma edição em source até a baseline boa estar identificada e preservada.
2. **Inventarie candidatos.** Liste as 9 linhagens de build existentes:
   `frontend/release/win-unpacked/ZARA 3.0.exe` e
   `frontend/release-candidate-20260811-{1042,1055,1110,1130,1155}`,
   `release-candidate-voice-20260811-1338`, `release-candidate-voice-kore-20260811-1400`,
   `release-candidate-live-20260811-2005`. Para cada um: caminho, timestamp, SHA256.
3. **Inventarie o lado git, read-only.** HEAD atual é `refs/heads/codex/zara-voice-human-loop-001`;
   remote origin `https://github.com/Alexpyton5/ZARA-3.0.git`; tag de baseline recuperável
   `zara-3.0-principal-2026-08-08` (commit base `3d817a2`). Existe `.git/AUTO_MERGE` — resíduo de
   merge. Investigue-o antes de qualquer operação git, nunca remova por suposição.
4. **Ache o último estado fisicamente bom**, cruzando timestamp de build com o relato de Alex sobre
   quando ainda funcionava. Estado bom = teve evidência física, não "parece certo no código".
5. **Preserve.** Copie/tague a baseline boa antes de mexer. Recuperação sem rede de segurança é aposta.
6. **Diff read-only** entre baseline boa e estado atual. Só leitura. Sem edição durante o diff.
7. **Isole UMA regressão.** Uma hipótese causal por vez. Se o diff mostra cinco mudanças suspeitas,
   escolha a mais provável e teste só ela.
8. **Menor patch possível.** Cirúrgico, no mínimo de arquivos.
9. **Empacote** o candidato e nomeie o EXE exato (ver `validating-packaged-runtime`).
10. **Micro smoke físico**: 1–3 comandos ligados ao patch. Passou → aceite como nova baseline.
    Falhou → reverta imediatamente e volte ao passo 7 com outra hipótese.

## Regras de evidência

- Baseline só é baseline depois de passar num smoke físico curto. Antes disso é candidato.
- Sempre registre `SOURCE_ROOT / BUILD_ID / BUILD_TIMESTAMP / EXE_PATH / SHA256 / SOURCE_REVISION`.
- Lição do build velho: já aconteceu de testarmos um EXE de 2026-08-08 enquanto o source já tinha
  avançado muito. O resultado do teste não descrevia o código — descrevia um binário fóssil.
  Antes de concluir qualquer coisa de um teste físico, confirme que o EXE testado corresponde ao
  source em discussão. Timestamp e hash resolvem isso; opinião não.
- Diferencie "o patch não funcionou" de "o patch não estava no binário testado".

## O que NUNCA fazer

- Nunca recuperar e refatorar na mesma tarefa. Recuperação é tarefa própria e delimitada.
- Nunca usar `git reset --hard`, `git clean -fd`, `git checkout -- .` ou `git restore .` amplos.
- Nunca apagar `.git/AUTO_MERGE`, builds antigos, `.zara-dev/` ou artefatos desconhecidos "para limpar".
- Nunca declarar recuperado com base em teste unitário ou em leitura de código.
- Nunca reverter mais de uma coisa por vez — some a causa junto com o efeito.
- Nunca sobrescrever a última baseline boa conhecida antes de ter uma nova validada fisicamente.

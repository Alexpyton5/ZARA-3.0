# Regras de build e release — ZARA 3.0

**2026-09-04 (Alex):** o conceito de "candidato" saiu do workflow. Existe **um** build
ativo, apontado por `ZARA_ACTIVE_BUILD.json` / `ZARA_ACTIVE_BUILD.txt` na raiz (antigos
`ULTIMO_CANDIDATO.*`). `tools/build_candidate.py` continua existindo como ferramenta interna
de empacotamento (o nome do arquivo e seu vocabulário interno não mudaram — é escopo
separado), mas o que ele produz é tratado como **o build ativo**, não como "um candidato
a mais". Linhagens antigas em `frontend/release-candidate-*/` não são mais referência
operacional — ver seção de limpeza de disco.

## O incidente que originou estas regras

Alex passou dias testando fisicamente um EXE de **2026-08-08 13:12** enquanto o source já
tinha avançado muito além dele. Todo relatório de "corrigido" batia contra um binário velho.
Isso destruiu a confiança em toda a cadeia de evidência.

Regra: **o artefato testado tem de ser rastreável ao source testado, sempre.**

## Linhagens de build presentes no repositório (histórico)

Verificado por leitura em 2026-08-12, `frontend/`:

```
release/
release-candidate-20260811-1042/
release-candidate-20260811-1055/
release-candidate-20260811-1110/
release-candidate-20260811-1130/
release-candidate-20260811-1155/
release-candidate-voice-20260811-1338/
release-candidate-voice-kore-20260811-1400/
release-candidate-live-20260811-2005/
```

Cada uma tem `win-unpacked/ZARA 3.0.exe` e `win-unpacked/resources/backend/zara-backend.exe`.
Nenhuma é referência operacional hoje — só `ZARA_ACTIVE_BUILD.json` diz qual é o build ativo.

**Nenhuma delas contém manifesto de identidade.** Isso é uma dívida. Todo build novo
deve gravar `BUILD_INFO.json` na raiz do `win-unpacked/`.

## Identidade obrigatória do build ativo

```json
{
  "BUILD_ID": "<rotulo>-<AAAAMMDD>-<HHMM>",
  "BUILD_TIMESTAMP": "<ISO local>",
  "GIT_BRANCH": "",
  "GIT_COMMIT": "",
  "GIT_DIRTY": true,
  "EXE_SHA256": "",
  "BACKEND_SHA256": "",
  "ASAR_SHA256": "",
  "DELTA": "<o que mudou em relação ao build anterior>"
}
```

Sem esse arquivo, o build não pode ser oferecido para teste físico.

## Portão de build

Antes de gerar um build físico:

1. identidade do toolchain provada (qual Python, qual Node, qual npm — caminhos explícitos)
2. testes de source relevantes ao delta passando
3. checagens de frontend relevantes ao delta passando
4. empacotamento concluído sem erro
5. build executado diretamente e sobrevivendo ao boot
6. hashes capturados
7. build anterior preservado (nunca sobrescrever `release/`)
8. nenhuma mutação de dependência não relacionada

## Verificação de correspondência sidecar ↔ pacote

 O `zara-backend.exe` dentro de `win-unpacked/resources/backend/` deve ser byte a byte
idêntico ao recém-gerado em `dist-sidecar/`. Se divergir, o pacote está velho e qualquer
teste em cima dele é inválido.

Para alterações somente de interface, use `tools/build_candidate.py --rebuild-frontend --frontend-only`.
Esse modo exige o rebuild completo do frontend e copia o backend diretamente do build base,
comparando seu SHA-256 antes e depois. Ele não usa um `dist-sidecar` possivelmente antigo.
Não combine `--frontend-only` com `--rebuild-sidecar`.

## Build ativo não é baseline

Um build só vira baseline depois de passar o micro smoke físico (nível 1).
Baseline aprovada é preservada e recebe tag git.

Baseline recuperável já existente: tag `zara-3.0-principal-2026-08-08`.

## Limpeza de disco

O disco C já esteve com ~7,75 GiB livres. Nove linhagens de `win-unpacked` custam caro.
Arquivar/remover linhagens antigas é uma **tarefa própria e autorizada**, nunca um efeito
colateral de outra tarefa. Nunca apagar a baseline nem o build ativo anterior.

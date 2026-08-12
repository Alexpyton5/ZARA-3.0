---
name: validating-packaged-runtime
description: Valida e identifica sem ambiguidade o build empacotado da ZARA — EXE exato, SHA256, timestamp, BUILD_ID, identidade do backend e do frontend dentro do pacote e smoke no candidato exato; use SEMPRE antes de pedir qualquer teste físico ao Alex, porque existem 9 linhagens de build.
---

# Validação de runtime empacotado

## Quando usar

- Antes de qualquer frase do tipo "testa aí" dirigida ao Alex.
- Depois de empacotar um candidato novo.
- Quando um resultado de teste físico contradiz o que o source diz.
- Ao comparar duas linhagens de build.

## Fluxo obrigatório

1. **Empacote** e anote o `BUILD_ID` e o `BUILD_TIMESTAMP` do candidato.
2. **Fixe o EXE exato.** As linhagens existentes são:
   `frontend/release/win-unpacked/ZARA 3.0.exe` e
   `frontend/release-candidate-20260811-{1042,1055,1110,1130,1155}/win-unpacked/ZARA 3.0.exe`,
   `frontend/release-candidate-voice-20260811-1338/...`,
   `frontend/release-candidate-voice-kore-20260811-1400/...`,
   `frontend/release-candidate-live-20260811-2005/...`. São 9. Escolha uma e escreva o caminho inteiro.
3. **Calcule o SHA256** do EXE e registre. Hash é a única identidade não ambígua.
4. **Prove a identidade do backend empacotado.** Confirme que o sidecar Python (PyInstaller) dentro
   daquele pacote é o build atual: timestamp e hash do binário do sidecar, não do source em `core/`.
5. **Prove a identidade do frontend empacotado.** Confirme que o bundle React/Vite dentro de
   `win-unpacked` corresponde ao build atual, não a um `dist` antigo reaproveitado.
6. **Rode o smoke dentro do candidato exato**, não em dev, não no `release/` por hábito.
   Micro smoke: 1–3 comandos ligados ao patch. Falhou → pare, não escale para família ampla.
7. **Emita o bloco de identificação** antes de chamar o Alex:
   `SOURCE_ROOT / BUILD_ID / BUILD_TIMESTAMP / EXE_PATH / SHA256 / SOURCE_REVISION`.
8. **Peça o teste com o rótulo imperativo:** `ALEX_OPEN_THIS_EXE: <caminho completo>`.
   Diga também qual é a frase exata a testar e qual é a postcondição observável esperada.
9. **Registre o resultado** com o mesmo bloco de identificação. Resultado sem EXE nomeado é inútil.

## Regras de evidência

- Rotule cada resultado: `PACKAGED_RUNTIME` (rodou no pacote), `PHYSICAL_BY_ALEX` (Alex viu o
  Windows mudar), `VOICE_PHYSICAL` (Alex falou e a ZARA executou). Nunca promova um nível.
- Se o hash do EXE testado não é o hash do candidato empacotado, o teste não vale para essa tarefa.
- Um candidato só vira baseline depois de passar num smoke físico curto.
- Pirâmide: 1) micro smoke ligado ao patch; 2) família pequena — wake, volume, brilho, night light,
  Chrome, YouTube, barge-in; 3) regressão ampla, só com baseline estável.
- Se o backend empacotado for antigo, diga isso explicitamente: o teste mediu um binário fóssil.

## O que NUNCA fazer

- Nunca dizer "abra a ZARA". Existem 9 linhagens; a frase é ambígua e já produziu conclusões falsas.
- Nunca pedir teste físico sem SHA256 e timestamp do EXE.
- Nunca assumir que empacotar o frontend reempacotou o sidecar Python. Prove os dois.
- Nunca apresentar resultado de `npm run dev` como evidência de runtime empacotado.
- Nunca apagar linhagens antigas de build — são material de comparação e rollback.
- Nunca reaproveitar um relatório de teste anterior para um candidato novo.

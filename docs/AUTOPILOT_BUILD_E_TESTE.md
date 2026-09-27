# ZARA 3.0 — Build e teste físico do Autopilot

## Estado desta preparação

O ZARA Lab V1 já possui scheduler persistente, supervisor, orçamento diário, deduplicação e execução em segundo plano. O build foi reforçado para não iniciar uma reconstrução cara quando o volume não tiver espaço suficiente e para remover, somente quando solicitado pelo script oficial, diretórios de staging incompletos.

A pasta `frontend/ZARA CURRENT BUILD` e `ZARA_ACTIVE_BUILD.json` nunca são removidos pelo modo `--clean-incomplete`. O modo de limpeza só aceita diretórios cujo nome comece por `.current-build-staging-` e só remove aqueles sem os dois manifestos finais.

## Como gerar o build no Windows

Feche a ZARA e qualquer janela do Explorer aberta dentro de `frontend/release` ou de um staging anterior. Execute:

```bat
cd /d "C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002"
ZARA_BUILD_ATUAL.bat
```

O pipeline agora faz uma pré-verificação. Ele exige pelo menos 3 GiB livres no volume do projeto, imprime uma linha `[PREFLIGHT]` e remove apenas staging incompleto. Se o espaço for insuficiente, o processo termina antes de PyInstaller e Electron Builder, preservando o build ativo.

## Critério de aprovação

O build só pode ser considerado candidato válido quando todos estes arquivos existirem no mesmo staging:

```text
ZARA 3.0 Setup 3.0.0.exe
win-unpacked/ZARA 3.0.exe
win-unpacked/BUILD_INFO.json
SOURCE_MANIFEST.json
win-unpacked/resources/backend/zara-backend.exe
```

A validação de integridade deve ser executada com:

```bat
.venv\Scripts\python.exe tools\build_current.py verify "frontend\.current-build-staging-AAAAmmdd-HHMMSS"
```

Não altere `ZARA_ACTIVE_BUILD.json` apenas por existir um instalador. A ativação exige um relatório de validação Electron real que identifique o mesmo ASAR e o mesmo backend.

## Teste físico controlado

Depois de instalar o candidato aprovado, abra a ZARA e solicite:

> ZARA, mostre o estado do ZARA Lab e prepare uma autoatualização controlada apenas em workspace isolado. Não altere o build ativo, não instale nada adicional e apenas registre a proposta e o resultado.

Verifique que a resposta informa estado do Lab, scheduler, supervisor e missão persistida. A missão deve ser registrada como proposta ou fila; não deve declarar uma atualização concluída sem artefato, teste e validação correspondentes.

## Evidência honesta

A validação local desta preparação foi limitada a compilação de sintaxe de `tools/build_current.py`, `core/lab_v1/service.py` e `core/ipc_handlers.py`. O instalador Windows e o teste físico continuam pendentes até que o computador de casa execute o BAT. Nenhuma afirmação de build ativo novo deve ser feita antes desses passos.

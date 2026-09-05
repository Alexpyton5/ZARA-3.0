# ZARA 3.0 - Build Único (do zero)

Este documento descreve o comando único que reinstala todas as dependências, roda a suite de testes e gera o instalador do zero, sem passos manuais.

## Comando

```bash
python build_exe.py --full
```

## O que o comando faz

1. **Limpa artefatos de build**
   - Remove `build-sidecar/`, `dist-sidecar/`
   - Remove `frontend/dist-electron/`, `frontend/dist-frontend/`, `frontend/dist-tests/`
   - (Não toca em `frontend/release/` - baseline de recuperação)

2. **Instala dependências**
   - Atualiza o pip do virtualenv do projeto
   - Instala dependências principais a partir de `requirements.txt`
   - Instala dependências de desenvolvimento (`pytest`, `ruff`, `mypy`, `pytest-asyncio`)

3. **Roda a suite de testes**
   - Executa `pytest` para os testes Python
   - Executa `npm test` para os testes do frontend

4. **Constrói o sidecar (zara-backend.exe)**
   - Usa o virtualenv do projeto para rodar PyInstaller
   - Gera o executável em `dist-sidecar/zara-backend.exe`
   - Atualiza os arquivos de manifesto:
     - `CLEAN_BUILD_ID.txt` (primeiros 8 caracteres do SHA256)
     - `SHA256_MANIFEST.txt`
     - `PATCH_SHA256_MANIFEST.txt`

5. **Constrói o instalador Electron**
   - Roda `npm run electron:build` no diretório frontend
   - Gera o instalador em `frontend/release/ZARA 3.0 Setup 3.0.0.exe`

## Pré-requisitos

- O virtualenv do projeto (`.venv`) já deve existir e estar configurado.
- As ferramentas de build (PyInstaller, Node.js, etc.) devem estar instaladas no virtualenv ou disponíveis no PATH.

## Saída esperada

Se o comando completar com sucesso, você verá:

```
============================================================
ZARA 3.0 FULL BUILD (sidecar + installer)
============================================================
[BUILD] Step 1: Cleaning artifacts...
...
[BUILD] Step 2: Installing dependencies...
...
[BUILD] Step 3: Running test suite...
...
[BUILD] Step 4: Building sidecar...
...
[BUILD] Step 5: Building Electron installer...
...
============================================================
FULL BUILD COMPLETE!
Sidecar: dist-sidecar/zara-backend.exe
Installer: frontend/release/ZARA 3.0 Setup 3.0.0.exe
Installer size: XX.X MB
============================================================
```

## Notas

- O comando é projetado para ser executado a partir da raiz do projeto.
- Qualquer erro durante as etapas será relatado e o comando retornará com código de saída não-zero.
- Em caso de falha fora do controle deste script (por exemplo, problemas de licenciamento, assinatura ou rede), relate como BLOCKED com o motivo exato.
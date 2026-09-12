# ZARA CURRENT BUILD

O aplicativo ativo é `frontend/ZARA CURRENT BUILD/win-unpacked/ZARA 3.0.exe`.
`ZARA_ACTIVE_BUILD.json` identifica o pacote, o source e os hashes do Electron,
ASAR, backend e instalador. `ABRIR-A-ZARA.bat`, `ZARA_INICIAR.bat` e os atalhos
oficiais leem esse registro; o launcher confere os artefatos antes de abrir.

## Construir

Na raiz do projeto, com `.venv` e `frontend/node_modules` preparados:

```powershell
& .venv\Scripts\python.exe tools\build_current.py build --delta "Descricao das mudancas"
```

`ZARA_BUILD_ATUAL.bat` e `build_exe.py --full` chamam esse mesmo pipeline.
O processo comprova os caminhos/versões do toolchain, recompila o sidecar,
executa TypeScript/Vite, compila o main/preload e empacota Electron + NSIS.
Não reinstala dependências nem depende de `requirements.txt`; as dependências
Python são declaradas em `pyproject.toml` e o frontend usa `package-lock.json`.

A saída é uma pasta `.current-build-staging-<data-hora>` dentro de `frontend`.
O build anterior permanece ativo. Alterações no source durante o build ou
divergência entre o backend empacotado e `dist-sidecar` fazem a etapa falhar.
`--reuse-sidecar` aceita somente um sidecar cujo recibo comprova os hashes do
binário e do source atual. `build_exe.py` isolado gera apenas esse sidecar e
seu recibo; não escreve identidade sobre um Electron anterior.

## Validar e ativar

Execute o pacote recém-gerado e valide o boot, IPC, navegação, funcionalidades
alteradas e apresentação visual. Preserve o relatório JSON com `status: passed`,
`asar_sha256` e `backend_sha256` do pacote efetivamente testado, mais as evidências
e limites de validação. Não marque um teste não executado como aprovado.

```powershell
& .venv\Scripts\python.exe tools\build_current.py verify "frontend\.current-build-staging-AAAAMMDD-HHMMSS"
& .venv\Scripts\python.exe tools\build_current.py activate "frontend\.current-build-staging-AAAAMMDD-HHMMSS" --validation "caminho\validacao.json" --shortcuts
```

A ativação exige os hashes exatos e o source sem alterações desde o build.
Ela move o pacote para `ZARA CURRENT BUILD`, guarda o relatório e troca os
ponteiros. Um `ZARA CURRENT BUILD` anterior é preservado em `.build-backups`.
`frontend/release` permanece como histórico de recuperação. Nenhum processo
do usuário é encerrado pelo pipeline ou pelos launchers.

`--shortcuts` cria o atalho **ZARA CURRENT BUILD** na Área de Trabalho e
atualiza os atalhos ZARA existentes do usuário, inclusive o Menu Iniciar,
para o launcher oficial. O resultado verificado é salvo em `SHORTCUTS.json`.
Se uma ZARA antiga já estiver aberta, saia pelo menu da bandeja antes de
iniciar a atual; a proteção de instância única pertence ao Electron.

`ZARA_EMPACOTAR.bat` é um arquivo local legado não versionado e não é o comando
oficial: ainda aponta para `requirements.txt` e `frontend/release`.

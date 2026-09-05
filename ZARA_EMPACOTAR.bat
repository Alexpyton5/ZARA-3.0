@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"

rem ZARA-EMPACOTAR-001 -- gera o build ativo do zero: sidecar Python
rem (zara-backend.exe) + app Electron (ZARA 3.0.exe), grava BUILD_INFO.json
rem com hash/commit/timestamp, e diz exatamente qual EXE abrir.
rem
rem Nao inventa build "pronto": se qualquer etapa falhar, para aqui e mostra
rem o erro. Nunca oferece um EXE para teste fisico sem prova de que ele
rem corresponde a este commit.

echo ================================================================
echo  ZARA 3.0 - EMPACOTAR BUILD COMPLETO
echo ================================================================
echo.

rem ---------------------------------------------------------------
rem 1) Python proprio do projeto (nunca "python" solto -- ver
rem    .claude/rules/path-rules/backend-core.md)
rem ---------------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
  echo [1/6] .venv nao existe ainda. Preparando o Python da ZARA...
  python tools\preparar_python.py
  if errorlevel 1 (
    echo.
    echo ================================================================
    echo  FALHOU ao preparar o Python. Veja o erro acima.
    echo ================================================================
    pause
    exit /b 1
  )
) else (
  echo [1/6] .venv ja existe.
)
echo.

echo [2/6] Instalando/atualizando dependencias Python...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo.
  echo ================================================================
  echo  FALHOU ao instalar dependencias Python. Veja o erro acima.
  echo ================================================================
  pause
  exit /b 1
)
echo.

rem ---------------------------------------------------------------
rem 3) Sidecar Python (zara-backend.exe)
rem ---------------------------------------------------------------
echo [3/6] Construindo o sidecar (zara-backend.exe)...
echo       Isso demora alguns minutos na primeira vez.
".venv\Scripts\python.exe" build_exe.py
if errorlevel 1 (
  echo.
  echo ================================================================
  echo  FALHOU ao construir o sidecar. Veja o erro acima.
  echo  Nenhum EXE novo foi oferecido.
  echo ================================================================
  pause
  exit /b 1
)
echo.

rem ---------------------------------------------------------------
rem 4) Frontend + Electron (ZARA 3.0.exe), com o sidecar acima
rem    embutido via extraResources (dist-sidecar\zara-backend.exe)
rem ---------------------------------------------------------------
echo [4/6] Instalando dependencias do frontend (npm ci)...
pushd frontend
call npm ci
if errorlevel 1 (
  echo.
  echo ================================================================
  echo  FALHOU o "npm ci". Veja o erro acima.
  echo ================================================================
  popd
  pause
  exit /b 1
)
echo.

echo [5/6] Construindo o app Electron (isso demora varios minutos)...
call npm run electron:build
if errorlevel 1 (
  echo.
  echo ================================================================
  echo  FALHOU o build do Electron. Veja o erro acima.
  echo  O sidecar foi construido, mas o app NAO foi empacotado.
  echo ================================================================
  popd
  pause
  exit /b 1
)
popd
echo.

rem ---------------------------------------------------------------
rem 6) Identidade do build: recomputa o hash do sidecar (rapido, so
rem    leitura) e grava frontend\release\win-unpacked\BUILD_INFO.json
rem    agora que a pasta existe de verdade.
rem ---------------------------------------------------------------
echo [6/6] Gravando identidade do build (BUILD_INFO.json)...
".venv\Scripts\python.exe" -c "import build_exe as b; sha = b.update_sidecar_manifests(b.DIST_DIR / (b.APP_NAME + '.exe')); b.generate_build_info(sha) if sha else exit(1)"
if errorlevel 1 (
  echo.
  echo ================================================================
  echo  FALHOU ao gravar BUILD_INFO.json. O EXE existe mas a
  echo  identidade do build nao foi confirmada -- nao ofereca para
  echo  teste fisico sem investigar isso primeiro.
  echo ================================================================
  pause
  exit /b 1
)
echo.

rem ---------------------------------------------------------------
rem Resultado: mostra o caminho exato do EXE, o hash do sidecar
rem embutido e atualiza os ponteiros ZARA_ACTIVE_BUILD.*
rem ---------------------------------------------------------------
set "EXE_PATH=%~dp0frontend\release\win-unpacked\ZARA 3.0.exe"
set "INFO_PATH=%~dp0frontend\release\win-unpacked\BUILD_INFO.json"

if not exist "%EXE_PATH%" (
  echo ================================================================
  echo  O build terminou sem erro reportado, mas o EXE esperado nao
  echo  esta em:
  echo    %EXE_PATH%
  echo  Nao ofereca isto como pronto. Avise o Claude/Mentor.
  echo ================================================================
  pause
  exit /b 1
)

echo %EXE_PATH%> "%~dp0ZARA_ACTIVE_BUILD.txt"

echo ================================================================
echo  BUILD COMPLETO
echo ================================================================
echo.
echo  ALEX_OPEN_THIS_EXE:
echo  %EXE_PATH%
echo.
echo  Identidade do build (BUILD_INFO.json):
type "%INFO_PATH%"
echo.
echo ================================================================
echo  Antes de testar por voz/texto: feche qualquer ZARA antiga rodando
echo  (Gerenciador de Tarefas -^> "ZARA 3.0.exe" e "zara-backend.exe"),
echo  depois abra o EXE acima diretamente.
echo ================================================================
echo.
pause

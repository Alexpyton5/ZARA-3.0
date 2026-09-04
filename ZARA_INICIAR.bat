@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

rem ZARA-INICIAR-001 -- launcher oficial. Fluxo:
rem preflight rapido -> safe cleanup -> quick health -> atualiza estado ->
rem se nao houver falha critica, abre a ZARA. Nunca roda suite pesada aqui.

if not exist ".venv\Scripts\python.exe" (
  echo  Nao encontrei .venv\Scripts\python.exe.
  echo  Rode CLIQUE-AQUI-CONSERTAR-E-BUILDAR.bat primeiro, ou avise
  echo  o Claude/Mentor para preparar o ambiente.
  echo.
  pause
  exit /b 1
)

echo ================================================================
echo  ZARA - INICIANDO
echo ================================================================
echo.
echo [PRE-FLIGHT] verificando ambiente e saude rapida...
".venv\Scripts\python.exe" "tools\zara_selftest.py" --quick
set HEALTH_RC=%ERRORLEVEL%
echo.

if %HEALTH_RC% NEQ 0 (
  echo ================================================================
  echo  FALHA CRITICA no pre-flight. A ZARA NAO vai abrir sozinha.
  echo ================================================================
  echo.
  echo  Veja o diagnostico curto:
  echo    .zara-tests\latest\ZARA_STATE.md
  echo.
  echo  Rode ZARA_TESTAR_TUDO.bat -- opcao 3, FULL SAFE -- para investigar,
  echo  ou avise o Claude/Mentor.
  echo.
  pause
  exit /b 1
)

echo [LAUNCH] pre-flight OK. Abrindo a ZARA...
echo.

echo Fechando qualquer ZARA que ainda esteja rodando...
taskkill /F /IM "ZARA 3.0.exe"     >nul 2>&1
taskkill /F /IM "zara-backend.exe" >nul 2>&1
timeout /t 3 /nobreak >nul

set "EXEPATH="
if exist "ZARA_ACTIVE_BUILD.txt" (
  set /p EXEPATH=<ZARA_ACTIVE_BUILD.txt
)

if not defined EXEPATH (
  echo.
  echo  Nao encontrei ZARA_ACTIVE_BUILD.txt -- nao sei qual EXE abrir.
  echo  Rode CLIQUE-AQUI-CONSERTAR-E-BUILDAR.bat para gerar de novo.
  echo.
  pause
  exit /b 1
)

if not exist "%EXEPATH%" (
  echo.
  echo  O build ativo registrado nao existe mais no disco:
  echo  %EXEPATH%
  echo.
  pause
  exit /b 1
)

echo Abrindo:
echo   %EXEPATH%
echo.

start "" "%EXEPATH%"
timeout /t 12 /nobreak >nul

tasklist /fi "imagename eq ZARA 3.0.exe" 2>nul | find /i "ZARA 3.0.exe" >nul
if errorlevel 1 (
  echo ================================================================
  echo  A ZARA NAO ABRIU.
  echo  Me avise para eu investigar.
  echo ================================================================
) else (
  echo ================================================================
  echo  A ZARA ESTA ABERTA.
  echo.
  echo  Ligue o microfone e fale.
  echo ================================================================
)
echo.
pause

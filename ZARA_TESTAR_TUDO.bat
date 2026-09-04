@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo  Nao encontrei .venv\Scripts\python.exe.
  echo  Rode CLIQUE-AQUI-CONSERTAR-E-BUILDAR.bat primeiro, ou avise
  echo  o Claude/Mentor para preparar o ambiente.
  echo.
  pause
  exit /b 1
)

:MENU
cls
echo ================================================================
echo  ZARA — AUTODIAGNOSTICO
echo ================================================================
echo.
echo  [1] QUICK        (30-90s, so camada tecnica, sem abrir a ZARA)
echo  [2] FULL SAFE     (recomendado — tecnica + candidato real + comandos
echo                     de voz por texto, com efeito real na tela)
echo  [3] REPORT ONLY   (so mostra o ultimo relatorio, nao roda nada)
echo  [4] CLEAN         (limpeza segura de cache/orfaos, nao roda teste)
echo  [5] SAIR
echo.
set /p ESCOLHA="Escolha [1-5, padrao 2]: "
if "%ESCOLHA%"=="" set ESCOLHA=2

if "%ESCOLHA%"=="1" (
  ".venv\Scripts\python.exe" "tools\zara_selftest.py" --quick
  goto FIM
)
if "%ESCOLHA%"=="2" (
  echo.
  echo  ATENCAO: FULL SAFE abre navegador, toca audio e muda volume/brilho
  echo  DE VERDADE na sua tela ^(restaura volume/brilho no final^). Nao e
  echo  simulacao.
  echo.
  ".venv\Scripts\python.exe" "tools\zara_selftest.py" --full
  goto FIM
)
if "%ESCOLHA%"=="3" (
  ".venv\Scripts\python.exe" "tools\zara_selftest.py" --report
  goto FIM
)
if "%ESCOLHA%"=="4" (
  ".venv\Scripts\python.exe" "tools\zara_selftest.py" --clean
  goto FIM
)
if "%ESCOLHA%"=="5" exit /b 0

echo Opcao invalida.
pause
goto MENU

:FIM
echo.
echo Relatorio: .zara-tests\latest\ZARA_TEST_REPORT.md
echo.
pause

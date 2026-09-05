@echo off
setlocal
cd /d "%~dp0"

rem ZARA-ABRIR-SEM-PYTHON-001
rem Este atalho NAO chama mais Python. A versao anterior lia o caminho do EXE
rem rodando `"%PY%" -c "..."` dentro de um for/f. Como o caminho do Python da
rem ZARA tem espacos ("ZARA 3.0 CLEAN 002"), o cmd quebrava a linha inteira e o
rem .bat morria em silencio: nenhuma mensagem, nenhuma janela, nada.
rem Agora o build grava o caminho num arquivo de texto simples e aqui so lemos.

echo ================================================================
echo  ABRIR A ZARA
echo ================================================================
echo.
echo  O aplicativo so aceita UMA instancia. Se ja houver uma aberta
echo  (ou travada em segundo plano), a nova fecha em silencio.
echo  Este arquivo garante que isso nao aconteca.
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
  echo  Nao encontrei o arquivo que diz qual versao abrir.
  echo  Rode o CLIQUE-AQUI-CONSERTAR-E-BUILDAR.bat para gerar de novo.
  echo.
  pause
  exit /b 1
)

if not exist "%EXEPATH%" (
  echo.
  echo  A versao registrada nao existe mais no disco:
  echo  %EXEPATH%
  echo.
  pause
  exit /b 1
)

echo.
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

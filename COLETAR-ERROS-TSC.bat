@echo off
rem ============================================================
rem  COLETAR-ERROS-TSC.bat - junta os arquivos com erro de
rem  compilacao num zip para enviar a zoe.
rem  Como usar: copie para a raiz da pasta da ZARA e de duplo clique.
rem ============================================================
setlocal
cd /d "%~dp0"

set "OUT=%CD%\coletar-tsc"
if exist "%OUT%" rmdir /s /q "%OUT%"
mkdir "%OUT%" 2>nul

echo Coletando arquivos...

rem 1) os 3 arquivos apontados pelo erro
copy "frontend\src\renderer\components\zara-home\HomeDrawer.tsx" "%OUT%\" >nul 2>&1
copy "frontend\src\renderer\components\zara-lab-v2\LabRoom.tsx" "%OUT%\" >nul 2>&1
copy "frontend\src\renderer\components\zara-lab-v2\useLabRoom.ts" "%OUT%\" >nul 2>&1

rem 2) todo arquivo que define LabMutationApi ou os helpers de mutacao
for /f "delims=" %%F in ('findstr /s /m /c:"LabMutationApi" "frontend\src\*.ts" "frontend\src\*.tsx" 2^>nul') do (
  echo   + %%F
  copy "%%F" "%OUT%\" >nul 2>&1
)
for /f "delims=" %%F in ('findstr /s /m /c:"runDurableLabMutation" "frontend\src\*.ts" "frontend\src\*.tsx" 2^>nul') do (
  echo   + %%F
  copy "%%F" "%OUT%\" >nul 2>&1
)

rem 3) tipos e preload atuais (para comparar)
copy "frontend\src\renderer\global.d.ts" "%OUT%\" >nul 2>&1
copy "frontend\src\main.ts" "%OUT%\" >nul 2>&1

rem 4) compacta
if exist "%CD%\tsc-erros.zip" del "%CD%\tsc-erros.zip" >nul 2>&1
powershell -NoProfile -Command "Compress-Archive -Path '%OUT%\*' -DestinationPath '%CD%\tsc-erros.zip' -Force"

echo.
echo ============================================================
echo  Pronto! Envie para a zoe este arquivo:
echo    %CD%\tsc-erros.zip
echo ============================================================
echo.
pause

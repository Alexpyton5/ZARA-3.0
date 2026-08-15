@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
chcp 65001 >nul

echo ================================================================
echo  LIGAR O TELEGRAM DA ZARA
echo ================================================================
echo.
echo  ANTES DE CONTINUAR, faca isto no Telegram (celular ou computador):
echo.
echo    1. procure por:   @BotFather
echo    2. mande:         /newbot
echo    3. nome do robo:  ZARA
echo    4. usuario:       algo terminando em bot, ex: zara_do_alex_bot
echo.
echo  Ele vai te devolver um codigo parecido com este:
echo    8123456789:AAF-abcdefGHIJKLmnopQRSTuvwxYZ1234567
echo.
echo ================================================================
echo.

set "CHAVE="
set /p CHAVE=Cole a chave aqui e aperte Enter:

if not defined CHAVE (
  echo.
  echo  Nada foi colado. Nada mudou.
  pause
  exit /b 1
)

echo.
echo Guardando...

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo  Nao achei o Python da ZARA. Avise o Claude.
  pause
  exit /b 1
)

"%PY%" tools\guardar_chave_telegram.py "!CHAVE!"
if errorlevel 1 (
  echo.
  echo  Nao consegui guardar. Avise o Claude.
  pause
  exit /b 1
)

echo.
echo ================================================================
echo  PRONTO.
echo.
echo  Agora:
echo    1. abra a ZARA pelo ABRIR-A-ZARA.bat
echo    2. no Telegram, procure o robo que voce criou
echo    3. mande qualquer coisa, tipo: oi
echo.
echo  Ele vai te registrar como dono. Depois disso, so voce
echo  consegue dar comando por la.
echo ================================================================
echo.
pause

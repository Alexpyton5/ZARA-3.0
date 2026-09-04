@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================================
echo  TESTAR A ZARA
echo ================================================================
echo.
echo  Liga o candidato empacotado atual de verdade e testa varias
echo  capacidades reais (texto, sistema, memoria, wifi, energia).
echo  Sem simulacao: se aparecer OK aqui, funcionou de verdade agora,
echo  neste computador.
echo.
echo  NAO testa voz (microfone/fala) nem a tela do Electron -- isso
echo  so voce confirma abrindo a ZARA e falando com ela.
echo.
echo  Pode levar ate 1-2 minutos (boot a frio do backend).
echo.

if not exist ".venv\Scripts\python.exe" (
  echo  Nao encontrei .venv\Scripts\python.exe.
  echo  Rode CLIQUE-AQUI-CONSERTAR-E-BUILDAR.bat primeiro, ou avise
  echo  o Claude/Mentor para preparar o ambiente.
  echo.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" "tools\zara_functional_report.py"

echo.
pause

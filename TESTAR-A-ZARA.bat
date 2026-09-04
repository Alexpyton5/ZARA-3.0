@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo ================================================================
echo  TESTAR A ZARA
echo ================================================================
echo.
echo  Liga o candidato empacotado atual de verdade e testa varias
echo  capacidades reais (texto, sistema, memoria, wifi, energia) MAIS uma
echo  sequencia de comandos de voz por texto (YouTube, Spotify, volume,
echo  brilho, janelas), medindo o tempo real de resposta de cada um.
echo  Sem simulacao: se aparecer OK aqui, funcionou de verdade agora,
echo  neste computador.
echo.
echo  ATENCAO: isso abre navegador, toca audio e muda volume/brilho DE
echo  VERDADE na sua tela. Nao e so leitura.
echo.
echo  NAO testa voz (microfone/fala) nem a tela do Electron -- isso
echo  so voce confirma abrindo a ZARA e falando com ela.
echo.
echo  Pode levar alguns minutos (boot a frio + a sequencia de comandos).
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

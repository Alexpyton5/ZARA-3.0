@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Python da ZARA ausente. Prepare o ambiente antes de empacotar.
  exit /b 1
)
".venv\Scripts\python.exe" "tools\build_current.py" build --delta "Reconstrucao completa a partir do codigo atual"
exit /b %ERRORLEVEL%

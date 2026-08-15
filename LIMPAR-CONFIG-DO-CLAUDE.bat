@echo off
setlocal
cd /d "%~dp0"

rem ZARA-PYTHON-PROPRIO-001: usar o "%PY%" da ZARA, nunca o do Hermes.
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo.
echo ================================================================
echo  IMPORTANTE: feche o Claude Code ANTES de continuar.
echo  Com ele aberto, o arquivo e reescrito por cima.
echo ================================================================
echo.
pause
echo.
"%PY%" tools\limpar_config_claude.py --aplicar
echo.
pause

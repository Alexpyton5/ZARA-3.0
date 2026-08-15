@echo off
setlocal
cd /d "%~dp0"

rem ZARA-PYTHON-PROPRIO-001: usar o "%PY%" da ZARA, nunca o do Hermes.
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo.
"%PY%" tools\lembretes.py
echo.
echo ================================================================
echo  Para APAGAR os lembretes que ja passaram, feche esta janela e
echo  me avise. Os agendados nunca sao apagados.
echo ================================================================
echo.
pause

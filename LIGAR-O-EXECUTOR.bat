@echo off
title Executor da ZARA
cd /d "%~dp0"

rem ZARA-PYTHON-PROPRIO-001: usar o "%PY%" da ZARA, nunca o do Hermes.
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo.
echo  Ligando o executor...
echo  Deixe esta janela ABERTA e minimizada.
echo.
"%PY%" tools\executor_local.py
echo.
echo  Executor desligado.
pause

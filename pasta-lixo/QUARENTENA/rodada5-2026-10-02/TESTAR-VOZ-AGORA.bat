@echo off
REM Teste fisico da voz da ZARA - duplo clique e siga a tela.
cd /d "%~dp0"
".venv\Scripts\python.exe" tools\teste_fisico_voz_alex.py
echo.
pause

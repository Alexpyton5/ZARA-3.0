@echo off
rem Pre-voo da voz da ZARA - duplo clique para rodar.
rem Usa o Python do proprio app; nao instala nada.
cd /d "%~dp0\.."
if exist ".venv\Scripts\python.exe" (
    set "PY=.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul
    if not errorlevel 1 (
        set "PY=py -3"
    ) else (
        set "PY=python"
    )
)
"%PY%" tools\voz_preflight_check.py
echo.
pause

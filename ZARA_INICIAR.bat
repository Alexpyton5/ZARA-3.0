@echo off
setlocal
cd /d "%~dp0"
rem Abre somente o build identificado e confere os hashes antes do launch.
rem O Electron cuida da instancia unica, sem encerrar processos do usuario.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\launch_current.ps1"
exit /b %ERRORLEVEL%

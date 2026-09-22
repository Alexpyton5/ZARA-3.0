@echo off
REM =============================================
REM       INTEGRATION SCRIPT – ZARA 3.0
REM =============================================

REM ---- 1. Build da UI (Next ou Vite) ----------------
set "UI_DIR=C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\zara_interface"
set "FRONTEND_DIR=C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\frontend"

pushd "%UI_DIR%"
echo Buildando a pasta zara_interface...
npm install 1>nul
rem Detecta a pasta de output ("out" ou "dist")
call npm run build

REM ---- 2. Copiando a pasta de saída para /public -----------
set "DEST_DIR=%FRONTEND_DIR%\public\zara_interface"

if exist "%UI_DIR%\out\" (
    echo Copiando a pasta “out”....
    xcopy /E /H /Y /I "%UI_DIR%\out\*" "%DEST_DIR%\"
) else if exist "%UI_DIR%\dist\" (
    echo Copiando a pasta “dist”....
    xcopy /E /H /Y /I "%UI_DIR%\dist\*" "%DEST_DIR%\"
) else (
    echo *** ERRO: não encontrou pasta “out/” nem “dist/” ***
    pause
    exit /b 1
)

REM ---- 3. Build do frontend do ZARA ----------------
pushd "%FRONTEND_DIR%"
echo Buildando o front‑end…
npm install 1>nul
npm run build

REM ---- 4. Empacotamento com Electron --------------------
npm run electron:dist

popd
popd

echo =========================================
echo ✅  Integração concluída.  O app já deve
echo     estar pronto para abrir com a nova interface.
echo =========================================
pause
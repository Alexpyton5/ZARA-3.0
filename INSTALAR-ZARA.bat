@echo off
chcp 65001 >nul
title ZARA 3.0 - Edição zoe - Instalador
echo.
echo  ============================================================
echo   ZARA 3.0 - EDICAO zoe - Build e Instalador
echo  ============================================================
echo.

REM --- 1) Checar Python ---
where python >nul 2>nul
if errorlevel 1 (
  echo  [ERRO] Python nao encontrado. Instale o Python 3.10+ em python.org
  echo         e marque "Add python.exe to PATH" na instalacao.
  pause
  exit /b 1
)
echo  [1/5] Python OK:
python --version

REM --- 2) Checar Node ---
where node >nul 2>nul
if errorlevel 1 (
  echo  [ERRO] Node.js nao encontrado. Instale o Node 18+ em nodejs.org.
  pause
  exit /b 1
)
echo  [2/5] Node OK:
node --version

REM --- 3) Dependencias Python (3 estrategias: uv, pip, venv) ---
echo.
echo  [3/5] Instalando dependencias Python (pode demorar na primeira vez)...
set "PY=python"

where uv >nul 2>nul
if not errorlevel 1 (
  echo  Python gerenciado por uv detectado - usando uv pip...
  uv pip install --system -r requirements.txt
  if errorlevel 1 goto :pip_fail
  goto :deps_ok
)

python -m pip install -r requirements.txt >nul 2>&1
if not errorlevel 1 goto :deps_ok

echo  pip bloqueado pelo gerenciador do sistema - criando ambiente virtual .venv...
python -m venv .venv
if errorlevel 1 (
  echo  [ERRO] Falha ao criar o ambiente virtual .venv
  pause
  exit /b 1
)
set "PY=.venv\Scripts\python.exe"
"%PY%" -m pip install --upgrade pip >nul 2>nul
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 goto :pip_fail
goto :deps_ok

:pip_fail
echo  [ERRO] Falha ao instalar requirements.txt
echo  Tente rodar manualmente: uv pip install --system -r requirements.txt
pause
exit /b 1

:deps_ok
"%PY%" -m pip install pyinstaller >nul 2>nul
echo  Dependencias Python OK.

REM --- 4) Sidecar Python -> zara-backend.exe ---
echo.
echo  [4/5] Construindo o sidecar Python (zara-backend.exe)...
"%PY%" build_exe.py
if errorlevel 1 (
  echo  [ERRO] Falha no build do sidecar. Veja as mensagens acima.
  pause
  exit /b 1
)
if not exist "dist-sidecar\zara-backend.exe" (
  echo  [ERRO] zara-backend.exe nao foi gerado em dist-sidecar\
  pause
  exit /b 1
)
echo  Sidecar OK: dist-sidecar\zara-backend.exe

REM --- 5) Frontend + instalador Electron ---
echo.
echo  [5/5] Instalando dependencias do frontend e gerando o instalador...
cd frontend
call npm install
if errorlevel 1 (
  echo  [ERRO] Falha no npm install.
  pause
  exit /b 1
)
call npm run electron:build
if errorlevel 1 (
  echo  [ERRO] Falha no electron:build. Veja as mensagens acima.
  pause
  exit /b 1
)
cd ..

echo.
echo  ============================================================
echo   PRONTO! Instalador gerado em:
echo     frontend\release\
echo   Procure o arquivo "ZARA 3.0 Setup *.exe" e execute para instalar.
echo  ============================================================
echo.
pause

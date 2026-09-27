@echo off
chcp 65001 >nul
title ZARA 3.0 - Edição zoe - Instalador
pushd "%~dp0"
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

REM --- 3) Ambiente virtual isolado + dependencias ---
echo.
echo  [3/5] Preparando ambiente Python isolado (pode demorar na primeira vez)...
set "PY=%CD%\.venv\Scripts\python.exe"

if not exist ".venv\Scripts\python.exe" (
  where uv >nul 2>nul
  if not errorlevel 1 (
    echo  Criando .venv com uv...
    uv venv .venv
  ) else (
    echo  Criando .venv...
    python -m venv .venv
  )
)
if not exist ".venv\Scripts\python.exe" (
  echo  [ERRO] Falha ao criar o ambiente virtual .venv
  pause
  exit /b 1
)
"%PY%" -m pip install --upgrade pip >nul 2>nul
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo  [ERRO] Falha ao instalar requirements.txt
  pause
  exit /b 1
)
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

@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

rem Entrada clicavel do pipeline unico. Gera somente uma candidate isolada;
rem nao escreve ZARA_ACTIVE_BUILD, nao substitui CURRENT e nao promove.
echo ================================================================
echo  ZARA 3.0 - GERAR CANDIDATE PELO PIPELINE CANONICO
echo ================================================================
echo.

call "%~dp0ZARA_BUILD_ATUAL.bat"
set "ZARA_BUILD_EXIT=%ERRORLEVEL%"

echo.
if not "%ZARA_BUILD_EXIT%"=="0" (
  echo FALHOU. CURRENT e rollback nao foram alterados.
) else (
  echo Candidate criada. Valide antes de qualquer promocao.
  echo CURRENT e rollback continuam intactos.
)
echo.
pause
exit /b %ZARA_BUILD_EXIT%

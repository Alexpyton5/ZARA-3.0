@echo off
setlocal
cd /d "%~dp0"

rem ZARA-PYTHON-PROPRIO-001: usar o "%PY%" da ZARA, nunca o do Hermes.
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
set "OUT=%~dp0ZARA-CONSERTO.txt"

echo ================================================================
echo  ZARA - VALIDAR, BUILDAR E PROVAR
echo ================================================================
echo.
echo  ENTRA NESTE BUILD:
echo.
echo   AUDICAO  o detector local lia 1,2s de audio para achar "zara"
echo            e jogava esse pedaco fora. O comeco da sua frase ia
echo            junto. Por isso "que horas sao" virava "oracao".
echo            Agora o audio vai inteiro para o Gemini.
echo.
echo   INTERROMPER  o mesmo detector fechava o microfone enquanto a
echo            Kore falava. Era impossivel corta-la. Agora o mic
echo            fica aberto e voce pode interromper falando.
echo.
echo   ECO      como o mic fica aberto, ela poderia se ouvir. Um
echo            filtro descarta a propria fala sem bloquear um
echo            "pare" dito por cima.
echo.
echo   CONVERSA depois de responder, ela continua ouvindo por 12s.
echo            Voce nao precisa repetir "Zara" a cada frase.
echo.
echo   FALA     67 comandos naturais contra 27 antes.
echo.
echo  Se qualquer etapa falhar, PARA e nao gera build.
echo.
rem sem pausa: roda sem supervisao

echo ================================================================ >  "%OUT%"
echo BUILD - %DATE% %TIME%                                            >> "%OUT%"
echo ================================================================ >> "%OUT%"

echo [1/6] Auditoria de compreensao de fala...
echo ---- [1] COMPREENSAO ----                                        >> "%OUT%"
"%PY%" tools\auditar_compreensao.py                                   >> "%OUT%" 2>&1
"%PY%" tools\auditar_compreensao.py 2>nul | findstr /c:"comandos" /c:"falsos"

echo.
echo [2/6] Rodando os 641 testes...
echo.                                                                 >> "%OUT%"
echo ---- [2] TESTES ----                                             >> "%OUT%"
"%PY%" -m pytest -q                                                   >> "%OUT%" 2>&1
if errorlevel 1 (
  echo PYTEST FALHOU                                                  >> "%OUT%"
  echo.
  echo  PAROU: os testes quebraram. NENHUM build gerado.
  echo  O ZARA-CONSERTO.txt tem os nomes dos que falharam.
  exit /b 1
)
echo PYTEST OK                                                        >> "%OUT%"
echo    641 testes OK.

echo.
echo [3/6] Conferindo o ambiente Python...
echo.                                                                 >> "%OUT%"
echo ---- [3] AMBIENTE ----                                           >> "%OUT%"
"%PY%" tools\fix_pydantic.py                                          >> "%OUT%" 2>&1

echo [4/6] Compilando o cerebro da ZARA...
echo.                                                                 >> "%OUT%"
echo ---- [4] SIDECAR ----                                            >> "%OUT%"
"%PY%" build_exe.py                                                   >> "%OUT%" 2>&1
if errorlevel 1 (
  echo BUILD SIDECAR FALHOU                                           >> "%OUT%"
  echo  PAROU na compilacao.
  exit /b 1
)
echo    backend compilado.

echo.
echo [5/6] Montando a versao nova...
echo.                                                                 >> "%OUT%"
echo ---- [5] CANDIDATO ----                                          >> "%OUT%"
"%PY%" tools\build_candidate.py --base auto --tag kore --delta "ZARA-VOICE-AUDICAO-001 gate Vosk desligado (parava de cortar o inicio das frases) + ZARA-VOICE-ECO-001 filtro de eco + ZARA-VOICE-CONVERSA-001 janela de continuacao + ZARA-VOICE-VERBOS-002 fala natural 27->67 + ZARA-VOICE-LATENCY-001" >> "%OUT%" 2>&1
if errorlevel 1 (
  echo CANDIDATO FALHOU                                               >> "%OUT%"
  echo  PAROU na montagem.
  exit /b 1
)

echo.
echo [6/6] Provando que a Kore sobe no build novo...
echo.                                                                 >> "%OUT%"
echo ---- [6] PROVA DA VOZ ----                                       >> "%OUT%"
"%PY%" tools\probe_voice.py                                           >> "%OUT%" 2>&1

echo.
echo ================================================================
findstr /c:"GEMINI LIVE SUBIU" "%OUT%" >nul && (
  echo  TUDO VERDE. A VOZ KORE SUBIU.
  echo.
  echo  ABRA ESTE EXE:
  "%PY%" -c "import json;print('    '+json.load(open('ULTIMO_CANDIDATO.json',encoding='utf-8'))['EXE_PATH'])"
  echo.
  echo  Fale do SEU jeito, sem se policiar:
  echo     Zara, abaixa o brilho ai.
  echo     Zara, poe o volume a 30.
  echo     Zara, liga o modo noturno.
  echo     Zara, minimiza.
  echo     Zara, tira o som.
  echo     Zara, volta o som.
  echo     Zara, abre o youtube.
  echo     Zara, o que ta tocando?
) || (
  echo  A Kore NAO subiu. Veja ZARA-CONSERTO.txt
)
echo ================================================================

rem ---- limpeza automatica: a pasta nunca acumula lixo ----
"%PY%" tools\limpar_pasta.py --auto
echo.

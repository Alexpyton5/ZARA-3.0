# MISSÃO 01 — Voz (urgente: conserto + missão #8)

## Contexto

O Alex apertou o botão do microfone na ZARA e deu erro:
"Error invoking remote method 'voice-start': Error: Gemini Live/Kore indisponível:
Gemini Live requer google-genai e sounddevice instalados".

Diagnóstico da zoe via ponte SSH: no `.venv`, o pacote `google/genai` existe,
mas o pacote `sounddevice` está QUEBRADO (só restou o `dist-info`, o código sumiu —
`import sounddevice` falha). O app roda o `zara-backend.exe` compilado, então não
basta reinstalar: é preciso RECONSTRUIR o exe.

## Passo 0 (antes de tudo — proteção)

O trabalho do ciclo #7 está no disco sem commit. Commite e suba TUDO que está
no disco num branch WIP (ex: `wip/ciclo7-20260927`), sem mexer no código —
só proteção. Só depois disso comece a missão.

## Missão

1. `pip install --force-reinstall sounddevice` no `.venv`; confira que
   `import sounddevice` funciona de verdade.
2. Reconstrua o `zara-backend.exe` (PyInstaller) e atualize o build em
   `frontend\release\win-unpacked\resources\backend`.
3. Teste de verdade: abra o modo voz no app e confirme que o microfone liga sem erro.
4. Na sequência, missão #8 (voz) — CÓDIGO-BASE PRONTO PELA ZOE:
   a. OmniVoice instalado no PC como 2º motor de voz (local, grátis):
      no `.venv`: instalar o torch certo para a máquina e depois
      `pip install omnivoice`. Na 1ª execução ele baixa o modelo
      k2-fsa/OmniVoice do Hugging Face (avisar: download grande).
   b. Botão na interface pra trocar Kore ↔ OmniVoice: FALTA O BOTÃO —
      o backend já está pronto (TTSConfig.tts_engine aceita
      auto|edge|omnivoice|kokoro|gemini; o motor escolhido tenta primeiro).
      Criar o botão no VoiceDock.tsx gravando via config-set.
   c. Troca AUTOMÁTICA: PRONTA PELA ZOE — arquivo novo
      `core/omnivoice_tts.py` + cascata atualizada em `core/voice_tts.py`
      (ordem: Edge → OmniVoice → Kokoro → Gemini); se um motor falhar,
      o próximo assume sozinho, sem ficar muda nunca. A zoe verificou
      com testes simulados (13 checagens verdes); rode a suíte DE VERDADE
      antes do push — a parte do travamento/congelamento do Gemini Live
      (timeout) está coberta pela cascata: qualquer exceção na fala cai
      para o próximo motor.
5. Rode a suíte de testes completa antes do push.

## Pronto quando

Push no GitHub + relatório FEITO / ESTADO / ERRO / SUGESTÃO (máx 10 linhas).
Modo silencioso vale.

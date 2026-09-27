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
4. Na sequência, missão #8 (voz):
   a. OmniVoice instalado no PC como 2º motor de voz (local, grátis).
   b. Botão na interface pra trocar Kore ↔ OmniVoice.
   c. Troca AUTOMÁTICA se a Kore falhar — inclui cota esgotada, sem internet
      E congelamento/travamento (o Alex relatou que o Gemini Live às vezes
      trava em vez de dar erro; detectar timeout também).
5. Rode a suíte de testes completa antes do push.

## Pronto quando

Push no GitHub + relatório FEITO / ESTADO / ERRO / SUGESTÃO (máx 10 linhas).
Modo silencioso vale.

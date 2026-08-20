@echo off
REM Ponte Telegram -> CEO, rodando FORA do Claude Code.
REM Lancada pela Tarefa Agendada "ZARA-Ponte-CEO" no logon do Alex.
REM Sobrevive a queda e ao reinicio do Claude Code: as mensagens dele caem em
REM .claude\time\inbox.jsonl e ficam la ate o CEO voltar e ler.
cd /d "C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002"
".venv\Scripts\pythonw.exe" ".claude\time\ponte_ceo.py" escutar >> ".claude\time\ponte.log" 2>&1

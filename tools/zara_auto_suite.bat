@echo off
rem ZARA Auto-Suite — chamado pelo Agendador de Tarefas do Windows a cada 6h.
rem Validacao manual: duplo-clique aqui e confira .zara-tests\auto_suite.log
cd /d "%~dp0.."
".venv\Scripts\python.exe" "tools\zara_auto_suite.py"

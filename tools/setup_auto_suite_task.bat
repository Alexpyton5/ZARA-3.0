@echo off
rem Registra a tarefa agendada ZARA Auto-Suite (uma vez, como admin).
rem Criado pela zoe em 28/09/2026.
schtasks /create /tn "ZARA Auto-Suite" /tr "\"C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\tools\zara_auto_suite.bat\"" /sc HOURLY /mo 6 /ru SYSTEM /f

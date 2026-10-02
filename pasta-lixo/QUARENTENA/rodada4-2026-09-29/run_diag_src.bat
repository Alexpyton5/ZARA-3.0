@echo off
cd /d "C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002"
.venv\Scripts\python.exe -u main.py > "%TEMP%\src_out.txt" 2> "%TEMP%\src_err.txt"

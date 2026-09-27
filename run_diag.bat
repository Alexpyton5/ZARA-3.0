@echo off
cd /d "C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\frontend\release\win-unpacked\resources\backend"
zara-backend.exe > "%TEMP%\diag_out.txt" 2> "%TEMP%\diag_err.txt"

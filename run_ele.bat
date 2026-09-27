@echo off
cd /d "C:\Users\alexp\Downloads\ZARA 3.0 CLEAN 002\frontend"
call npm run electron:build > "%TEMP%\ele_out.txt" 2> "%TEMP%\ele_err.txt"

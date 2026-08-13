@echo off
cd /d C:\Users\user\Documents\DirectorX
title DirectorX-Victorian-Forbidden-Love
echo ========================================
echo  Victorian Forbidden Love — cinematic proof
echo  Flux GGUF + Wan 2.2 GGUF two-pass
echo  Log: temp\victorian_forbidden\run.log
echo ========================================
if not exist temp\victorian_forbidden mkdir temp\victorian_forbidden
.\.venv\Scripts\python.exe -u temp\_victorian_live_runner.py
echo.
echo EXIT %ERRORLEVEL%
echo Output: final_outputs\Victorian_Forbidden_Love_Proof.mp4
pause

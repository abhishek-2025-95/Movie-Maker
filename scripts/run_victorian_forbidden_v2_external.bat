@echo off
cd /d C:\Users\user\Documents\DirectorX
title DirectorX-Victorian-Forbidden-v2
echo ========================================
echo  Victorian Forbidden Love PROOF v2
echo  Hero plate lock + 16:9 + hard threat cuts
echo  Log: temp\victorian_forbidden_v2\run.log
echo  Out: final_outputs\Victorian_Forbidden_Love_Proof_v2.mp4
echo ========================================
if not exist temp\victorian_forbidden_v2 mkdir temp\victorian_forbidden_v2
.\.venv\Scripts\python.exe -u temp\_victorian_v2_live_runner.py
echo.
echo EXIT %ERRORLEVEL%
echo Output: final_outputs\Victorian_Forbidden_Love_Proof_v2.mp4
pause

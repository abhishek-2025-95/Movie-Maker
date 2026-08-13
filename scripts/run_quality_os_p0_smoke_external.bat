@echo off
cd /d C:\Users\user\Documents\DirectorX
title DirectorX-QualityOS-P0-Complete-Smoke
echo ========================================
echo  Quality OS P0 COMPLETE SMOKE
echo  Flux 24 + Wan two-pass 14/CFG4.5 x3
echo  HQ 1080 + grade + report
echo  Log: temp\quality_os_p0_smoke\run.log
echo  Out: final_outputs\Quality_OS_P0_Complete_Smoke.mp4
echo ========================================
if not exist temp\quality_os_p0_smoke mkdir temp\quality_os_p0_smoke
.\.venv\Scripts\python.exe -u temp\_qos_p0_smoke_live_runner.py
echo.
echo EXIT %ERRORLEVEL%
echo Output: final_outputs\Quality_OS_P0_Complete_Smoke.mp4
pause

@echo off
cd /d C:\Users\user\Documents\DirectorX
title DirectorX-Volcano-Boarding-Night-Slalom
echo ========================================
echo  Night Slalom Down an Active Volcano
echo  Volcano Boarding / Lava Slalom POV
echo  NO LoRA · Flux GGUF → Wan 2.2 two-pass
echo  Log: temp\volcano_boarding_night\run.log
echo  Out: final_outputs\Volcano_Boarding_Night_Slalom.mp4
echo ========================================
if not exist temp\volcano_boarding_night mkdir temp\volcano_boarding_night
.\.venv\Scripts\python.exe -u temp\_volcano_boarding_live_runner.py
echo.
echo EXIT %ERRORLEVEL%
echo Output: final_outputs\Volcano_Boarding_Night_Slalom.mp4
pause

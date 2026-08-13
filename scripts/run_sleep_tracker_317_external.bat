@echo off
cd /d C:\Users\user\Documents\DirectorX
title DirectorX-SleepTracker-317-Horror
echo ========================================
echo  The 3:17 AM Sleep-Tracker Recording
echo  Smart-Tech Horror / Found-Footage
echo  9:16 · Flux GGUF → Wan 2.2 → 1080x1920
echo  Log: temp\sleep_tracker_317\run.log
echo  Out: final_outputs\Sleep_Tracker_317_Horror.mp4
echo ========================================
if not exist temp\sleep_tracker_317 mkdir temp\sleep_tracker_317
.\.venv\Scripts\python.exe -u temp\_sleep317_live_runner.py
echo.
echo EXIT %ERRORLEVEL%
echo Output: final_outputs\Sleep_Tracker_317_Horror.mp4
pause

@echo off
cd /d C:\Users\user\Documents\DirectorX
title DirectorX-QualityOS-P1-GoldenHourTrain
echo ========================================
echo  Quality OS P1 - Golden Hour Train
echo  IP-Adapter identity + Wan two-pass
echo  Real-ESRGAN 1080x1920 + premium captions
echo  Log: temp\quality_os_p1_golden_hour_train\run.log
echo  Out: final_outputs\Quality_OS_P1_Golden_Hour_Train.mp4
echo ========================================
if not exist temp\quality_os_p1_golden_hour_train mkdir temp\quality_os_p1_golden_hour_train
.\.venv\Scripts\python.exe -u temp\_qos_p1_golden_hour_live_runner.py
echo.
echo EXIT %ERRORLEVEL%
echo Output: final_outputs\Quality_OS_P1_Golden_Hour_Train.mp4
pause

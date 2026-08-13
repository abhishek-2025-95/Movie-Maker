@echo off
cd /d C:\Users\user\Documents\DirectorX
title DirectorX-QualityOS-P1-AR-Filter-Horror
echo ========================================
echo  Quality OS P1 - AR Filter Horror
echo  The Filter That Knows Your Reflection
echo  IP-Adapter + Wan two-pass + Real-ESRGAN
echo  Log: temp\quality_os_p1_ar_filter_horror\run.log
echo  Out: final_outputs\Quality_OS_P1_AR_Filter_Horror.mp4
echo ========================================
if not exist temp\quality_os_p1_ar_filter_horror mkdir temp\quality_os_p1_ar_filter_horror
.\.venv\Scripts\python.exe -u temp\_qos_p1_ar_horror_live_runner.py
echo.
echo EXIT %ERRORLEVEL%
echo Output: final_outputs\Quality_OS_P1_AR_Filter_Horror.mp4
pause

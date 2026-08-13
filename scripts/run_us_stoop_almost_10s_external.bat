@echo off
cd /d C:\Users\user\Documents\DirectorX
title DirectorX-US-Stoop-Almost-10s
echo ========================================
echo  Brooklyn Stoop — The Almost (10s)
echo  Quality OS: Flux 24 + IP-Adapter (if ready)
echo  Wan two-pass 14 / CFG 4.5 + 1080 master
echo  Log: temp\us_stoop_almost_10s\run.log
echo  Out: final_outputs\US_Brooklyn_Stoop_Almost_10s.mp4
echo ========================================
if not exist temp\us_stoop_almost_10s mkdir temp\us_stoop_almost_10s
.\.venv\Scripts\python.exe -u scripts\render_us_stoop_almost_10s.py
echo.
echo EXIT %ERRORLEVEL%
echo Output: final_outputs\US_Brooklyn_Stoop_Almost_10s.mp4
pause

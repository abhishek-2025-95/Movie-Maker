@echo off
cd /d C:\Users\user\Documents\DirectorX
title DirectorX-QualityOS-P1-Weights
echo ========================================
echo  Quality OS P1 weight download
echo  RealESRGAN + Flux IP-Adapter + CLIP-L
echo  Log: temp\quality_os_p1\download.log
echo ========================================
if not exist temp\quality_os_p1 mkdir temp\quality_os_p1
powershell -ExecutionPolicy Bypass -File scripts\download_quality_os_p1_weights.ps1 > temp\quality_os_p1\download.log 2>&1
type temp\quality_os_p1\download.log
echo.
echo EXIT %ERRORLEVEL%
pause

@echo off
cd /d C:\Users\user\Documents\DirectorX
title DirectorX-P2-Train-Character-LoRA
echo ========================================
echo  P2 Train Flux LoRA dxc_arviewer (12GB)
echo  LIVE console + log
echo  LIVE output on this window
echo  Log: temp\p2_lora_train\train_live.log
echo ========================================
if not exist temp\p2_lora_train mkdir temp\p2_lora_train
.\.venv\Scripts\python.exe -u temp\_p2_train_live_runner.py
echo.
echo EXIT %ERRORLEVEL%
pause

@echo off
cd /d C:\Users\user\Documents\DirectorX
title DirectorX-P2-Character-Bible
echo ========================================
echo  P2 Character Bible - AR Filter Viewer
echo  15 Flux stills for LoRA train
echo  Log: temp\p2_character_bible\run.log
echo  Out: assets\characters\ar_filter_viewer\bible
echo ========================================
if not exist temp\p2_character_bible mkdir temp\p2_character_bible
.\.venv\Scripts\python.exe -u temp\_p2_bible_live_runner.py
echo.
echo EXIT %ERRORLEVEL%
pause

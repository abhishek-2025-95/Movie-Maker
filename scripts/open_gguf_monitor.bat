@echo off
cd /d C:\Users\user\Documents\DirectorX
title DirectorX-GGUF-Monitor
.\.venv\Scripts\python.exe -u scripts\monitor_gguf_download.py
pause

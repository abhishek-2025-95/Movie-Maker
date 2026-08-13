@echo off
cd /d C:\Users\user\Documents\DirectorX
title DirectorX-GGUF-Download
echo LOG: temp\gguf_5070_setup.log
echo PROGRESS: temp\gguf_download_progress.txt
echo Monitor window shows FILE %% and OVERALL %%
echo [%TIME%] START > temp\gguf_5070_setup.log
echo [%TIME%] Downloading GGUF models with %% progress >> temp\gguf_5070_setup.log
start "DirectorX-GGUF-Monitor" cmd /k "cd /d C:\Users\user\Documents\DirectorX && .\.venv\Scripts\python.exe -u scripts\monitor_gguf_download.py"
.\.venv\Scripts\python.exe -u scripts\download_gguf_5070.py >> temp\gguf_5070_setup.log 2>&1
if errorlevel 1 (
  echo [%TIME%] DOWNLOAD FAILED errorlevel=%ERRORLEVEL% >> temp\gguf_5070_setup.log
  echo DOWNLOAD FAILED. Not running smoke. See temp\gguf_5070_setup.log
  pause
  exit /b 1
)
findstr /C:"DOWNLOADS_DONE" temp\gguf_download_progress.txt >nul
if errorlevel 1 (
  echo [%TIME%] DOWNLOAD incomplete - aborting smoke >> temp\gguf_5070_setup.log
  echo DOWNLOAD incomplete. Not running smoke.
  pause
  exit /b 1
)
echo [%TIME%] build workflows >> temp\gguf_5070_setup.log
.\.venv\Scripts\python.exe scripts\build_workflow_api.py >> temp\gguf_5070_setup.log 2>&1
set PYTHONPATH=%CD%
.\.venv\Scripts\python.exe scripts\_print_gguf_status.py >> temp\gguf_5070_setup.log 2>&1
echo [%TIME%] smoke >> temp\gguf_5070_setup.log
.\.venv\Scripts\python.exe -u scripts\_smoke_gguf_5070.py >> temp\gguf_5070_setup.log 2>&1
echo [%TIME%] FINISHED >> temp\gguf_5070_setup.log
echo DONE. Review temp\gguf_5070_setup.log
pause

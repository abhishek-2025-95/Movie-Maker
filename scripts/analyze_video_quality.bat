@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0.."
echo Repo: %CD%
dir /b final_outputs\*.mp4 2>nul
set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py"
echo Using: %PY%
if "%~1"=="" (
  "%PY%" -u scripts\analyze_video_quality.py
) else (
  "%PY%" -u scripts\analyze_video_quality.py %*
)
echo EXIT !ERRORLEVEL!
pause

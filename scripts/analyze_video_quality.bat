@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py"
if "%~1"=="" (
  "%PY%" -u scripts\analyze_video_quality.py
) else (
  "%PY%" -u scripts\analyze_video_quality.py %*
)
echo EXIT %ERRORLEVEL%
pause

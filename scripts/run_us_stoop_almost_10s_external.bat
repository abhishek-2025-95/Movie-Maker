@echo off
setlocal EnableExtensions
REM Self-locating: works from any cwd. This .bat lives in scripts\
cd /d "%~dp0.."
title DirectorX-US-Porch-Light-10s
echo ========================================
echo  The Porch Light — waiting is a kind of love (10s)
echo  Yellow lantern always ON / locked-off / last-frame continue
echo  Quality OS: Flux 24 + Wan two-pass 14 / CFG 4.5 + Real-ESRGAN
echo  Leave your ComfyUI window OPEN if it is already running.
echo  Repo: %CD%
echo  Log: temp\us_stoop_porch_light\run.log
echo  Out: final_outputs\US_Porch_Light_Waiting_10s.mp4
echo ========================================
if not exist scripts\render_us_stoop_almost_10s.py (
  echo ERROR: render script missing. Checkout branch cursor/us-stoop-romance-10s-db5f
  echo Tried repo root: %CD%
  pause
  exit /b 1
)
if not exist temp\us_stoop_porch_light mkdir temp\us_stoop_porch_light

set "PY=%CD%\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py"
if not exist "%CD%\.venv\Scripts\python.exe" (
  where py >nul 2>&1
  if errorlevel 1 (
    where python >nul 2>&1
    if errorlevel 1 (
      echo ERROR: No .venv and no Python on PATH. Run scripts\setup_env.ps1 first.
      pause
      exit /b 1
    )
    set "PY=python"
  ) else (
    set "PY=py -3"
  )
)

echo Using: %PY%
%PY% -u scripts\render_us_stoop_almost_10s.py
echo.
echo EXIT %ERRORLEVEL%
echo Output: %CD%\final_outputs\US_Porch_Light_Waiting_10s.mp4
pause

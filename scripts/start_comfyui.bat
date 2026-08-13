@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM 1) Fix transformers/huggingface-hub mismatch
REM 2) Start ComfyUI in THIS window (leave it open)
cd /d "%~dp0.."

set "PY=C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe"
set "COMFY=C:\ComfyUI"

if not exist "%PY%" (
  echo FATAL: missing %PY%
  pause
  exit /b 1
)
if not exist "%COMFY%\main.py" (
  echo FATAL: missing %COMFY%\main.py
  pause
  exit /b 1
)

echo.
echo === pip: huggingface-hub^>=1.5.0,^<2.0 into Python311 ===
"%PY%" -m pip install "huggingface-hub>=1.5.0,<2.0"
if errorlevel 1 (
  echo FATAL: pip install huggingface-hub failed
  pause
  exit /b 1
)
"%PY%" -c "import huggingface_hub,transformers; print('hub', huggingface_hub.__version__, 'transformers OK')"
if errorlevel 1 (
  echo FATAL: transformers still cannot import. Paste this output.
  pause
  exit /b 1
)

echo.
echo === Starting ComfyUI. Leave this window OPEN. ===
echo When you see: To see the GUI go to: http://127.0.0.1:8188
echo open a SECOND cmd and run: scripts\run_us_stoop_almost_10s_external.bat
echo.
cd /d "%COMFY%"
"%PY%" -u main.py --listen 127.0.0.1 --port 8188 --normalvram
set "ERR=!ERRORLEVEL!"
echo EXIT !ERR!
pause
exit /b !ERR!

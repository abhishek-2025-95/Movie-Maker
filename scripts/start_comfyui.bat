@echo off
setlocal EnableExtensions
REM Start ComfyUI in THIS visible window. Leave it running, then render in a second cmd.
cd /d "%~dp0.."

set "DXPY=%CD%\.venv\Scripts\python.exe"
if exist "%DXPY%" (
  echo Using DirectorX helper to start ComfyUI...
  "%DXPY%" -u scripts\start_comfyui.py
  echo EXIT %ERRORLEVEL%
  pause
  goto :eof
)

set "COMFY=C:\ComfyUI"
set "PY=C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe"
if exist "%COMFY%\run_nvidia_gpu.bat" (
  cd /d "%COMFY%"
  call run_nvidia_gpu.bat
  goto :eof
)
if exist "%COMFY%\python_embeded\python.exe" (
  cd /d "%COMFY%"
  python_embeded\python.exe -s main.py --listen 127.0.0.1 --port 8188 --normalvram
  goto :eof
)
if exist "%COMFY%\venv\Scripts\python.exe" if exist "%COMFY%\main.py" (
  cd /d "%COMFY%"
  venv\Scripts\python.exe main.py --listen 127.0.0.1 --port 8188 --normalvram
  goto :eof
)
if exist "%PY%" if exist "%COMFY%\main.py" (
  echo Launching %PY% %COMFY%\main.py
  cd /d "%COMFY%"
  "%PY%" main.py --listen 127.0.0.1 --port 8188 --normalvram
  goto :eof
)

echo Could not find ComfyUI.
echo Looked for: %COMFY%\main.py and %PY%
if exist "%COMFY%" (
  echo Listing %COMFY%:
  dir /b "%COMFY%"
)
pause

@echo off
REM Start ComfyUI in a VISIBLE window, then leave it running.
setlocal
cd /d C:\ComfyUI
if exist run_nvidia_gpu.bat (
  echo Starting C:\ComfyUI\run_nvidia_gpu.bat
  call run_nvidia_gpu.bat
  goto :eof
)
if exist python_embeded\python.exe (
  echo Starting python_embeded\python.exe main.py
  python_embeded\python.exe -s main.py --listen 127.0.0.1 --port 8188 --normalvram
  goto :eof
)
if exist venv\Scripts\python.exe (
  echo Starting venv\Scripts\python.exe main.py
  venv\Scripts\python.exe main.py --listen 127.0.0.1 --port 8188 --normalvram
  goto :eof
)
echo Could not find a Comfy launcher under C:\ComfyUI
echo Start ComfyUI the way you usually do, wait for the UI, then re-run the stoop bat.
pause

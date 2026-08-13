@echo off
REM One-shot: fix Comfy's Python311 huggingface-hub vs transformers mismatch.
set "PY=C:\Users\user\AppData\Local\Programs\Python\Python311\python.exe"
echo Installing huggingface-hub>=1.5.0,<2.0 into %PY%
"%PY%" -m pip install "huggingface-hub>=1.5.0,<2.0"
echo.
echo Now run: scripts\start_comfyui.bat
pause

@echo off
setlocal
if not exist "%~dp0runtime\pythonw.exe" (
  echo Extract the entire ZIP before starting Finale Archive.
  pause
  exit /b 1
)
start "" "%~dp0runtime\pythonw.exe" -I "%~dp0app\server.py"
exit /b 0

@echo off
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" Code\initialize.py
  if errorlevel 1 goto failed
  ".venv\Scripts\python.exe" Code\web_app.py --open
) else if exist "..\.venv\Scripts\python.exe" (
  "..\.venv\Scripts\python.exe" Code\initialize.py
  if errorlevel 1 goto failed
  "..\.venv\Scripts\python.exe" Code\web_app.py --open
) else (
  python Code\initialize.py
  if errorlevel 1 goto failed
  python Code\web_app.py --open
)
if errorlevel 1 pause
exit /b
:failed
pause
exit /b 1

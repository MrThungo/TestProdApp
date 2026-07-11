@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo The local Python environment was not found.
  echo Run: py -m venv .venv
  echo Then: .venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

set PORT=5000
netstat -ano | findstr /R /C:":5000 .*LISTENING" >nul
if %ERRORLEVEL%==0 set PORT=5001

echo Starting Back to God AOG Flask App...
echo Open: http://127.0.0.1:%PORT%
echo.

".venv\Scripts\python.exe" -m flask --app app run --host 127.0.0.1 --port %PORT%
pause

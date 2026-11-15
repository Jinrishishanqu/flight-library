@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "PY=..\..\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [ERR] venv python not found: %PY%
  pause
  exit /b 1
)
start "" http://127.0.0.1:8770/
echo.
echo   Library site  ->  http://127.0.0.1:8770/
echo   DB            ->  %~dp0data\library.db
echo   Close this window to stop the server.
echo.
"%PY%" server.py 127.0.0.1 8770
pause

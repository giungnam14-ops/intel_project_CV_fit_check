@echo off
setlocal
cd /d "%~dp0\.."

if not exist logs mkdir logs
set LOG_FILE=logs\check_env_log.txt

echo ========================================
echo FitCheck AI - Running Environment Check
echo ========================================
echo.

:: Execute check_env.py and redirect stdout/stderr to log file, then display the log
.venv\Scripts\python.exe scripts\check_env.py > "%LOG_FILE%" 2>&1
type "%LOG_FILE%"

echo.
echo Log file saved to: %LOG_FILE%
echo.
pause
endlocal

@echo off
setlocal
cd /d "%~dp0\.."

if not exist logs mkdir logs
set LOG_FILE=logs\reinstall_mediapipe_log.txt

echo ======================================== > "%LOG_FILE%"
echo FitCheck AI - Reinstall MediaPipe (Strict Venv) >> "%LOG_FILE%"
echo ======================================== >> "%LOG_FILE%"

echo [1/4] Checking virtual environment...
echo [1/4] Checking virtual environment... >> "%LOG_FILE%"
if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv python not found.
    echo [ERROR] .venv python not found. >> "%LOG_FILE%"
    goto fail
)

echo [2/4] Uninstalling mediapipe...
echo [2/4] Uninstalling mediapipe... >> "%LOG_FILE%"
".venv\Scripts\python.exe" -m pip uninstall -y mediapipe >> "%LOG_FILE%" 2>&1

echo [3/4] Force installing mediapipe==0.10.11...
echo [3/4] Force installing mediapipe==0.10.11... >> "%LOG_FILE%"
".venv\Scripts\python.exe" -m pip install --no-cache-dir --force-reinstall mediapipe==0.10.11 >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto fail

echo [4/4] Running Environment Diagnostics...
echo [4/4] Running Environment Diagnostics... >> "%LOG_FILE%"
".venv\Scripts\python.exe" scripts\check_env.py >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto fail

:success
echo.
echo [SUCCESS] MediaPipe reinstall and diagnosis completed.
echo [SUCCESS] MediaPipe reinstall and diagnosis completed. >> "%LOG_FILE%"
echo Log saved to: %LOG_FILE%
goto end

:fail
echo.
echo [FAILED] MediaPipe reinstall or diagnosis failed.
echo [FAILED] MediaPipe reinstall or diagnosis failed. >> "%LOG_FILE%"
echo Please open this log file:
echo %LOG_FILE%
goto end

:end
echo.
echo Press any key to close this window.
pause
endlocal

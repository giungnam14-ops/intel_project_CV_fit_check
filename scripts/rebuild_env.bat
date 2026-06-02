@echo off
setlocal
cd /d "%~dp0\.."

if not exist logs mkdir logs
set LOG_FILE=logs\rebuild_env_log.txt

echo ======================================== > "%LOG_FILE%"
echo FitCheck AI - Rebuilding Environment >> "%LOG_FILE%"
echo ======================================== >> "%LOG_FILE%"

echo [1/5] Removing existing virtual environment (.venv)...
echo [1/5] Removing existing virtual environment (.venv)... >> "%LOG_FILE%"
if exist ".venv" (
    rmdir /s /q ".venv" >> "%LOG_FILE%" 2>&1
    if errorlevel 1 (
        echo [ERROR] Failed to delete existing .venv folder.
        echo [ERROR] Failed to delete existing .venv folder. >> "%LOG_FILE%"
        goto fail
    )
)
echo .venv folder cleared.

echo [2/5] Creating new virtual environment...
echo [2/5] Creating new virtual environment... >> "%LOG_FILE%"
python -m venv .venv >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto fail

echo [3/5] Upgrading pip...
echo [3/5] Upgrading pip... >> "%LOG_FILE%"
.venv\Scripts\python.exe -m pip install --upgrade pip >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto fail

echo [4/5] Installing requirements (mediapipe==0.10.9)...
echo [4/5] Installing requirements (mediapipe==0.10.9)... >> "%LOG_FILE%"
.venv\Scripts\python.exe -m pip install --no-cache-dir -r app\requirements.txt >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto fail

echo [5/5] Running check_env.py verification...
echo [5/5] Running check_env.py verification... >> "%LOG_FILE%"
.venv\Scripts\python.exe scripts\check_env.py >> "%LOG_FILE%" 2>&1
if errorlevel 1 goto fail

:success
echo.
echo [SUCCESS] Environment rebuilt successfully!
echo [SUCCESS] Environment rebuilt successfully! >> "%LOG_FILE%"
echo Log saved to: %LOG_FILE%
goto end

:fail
echo.
echo [FAILED] Rebuilding environment failed.
echo [FAILED] Rebuilding environment failed. >> "%LOG_FILE%"
echo Please check the details in: %LOG_FILE%
goto end

:end
echo.
echo Press any key to close this window.
pause
endlocal

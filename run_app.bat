@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo FitCheck AI - Start App (Strict Virtual Env)
echo ========================================
echo.
echo [NOTE] If MediaPipe model file error occurs,
echo        please use scripts\rebuild_env.bat to reset the environment.
echo.

echo [1/5] Checking Python executable...
python --version
if errorlevel 1 (
    echo [ERROR] Python is not installed or not added to PATH.
    pause
    exit /b 1
)

echo [2/5] Setting up virtual environment...
if not exist ".venv" (
    echo Creating new virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo Virtual environment already exists.
)

echo [3/5] Installing and updating requirements (no-cache)...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install --no-cache-dir -r "app\requirements.txt"
if errorlevel 1 (
    echo [ERROR] Failed to install requirements.
    pause
    exit /b 1
)

echo [4/5] Running environment check...
.venv\Scripts\python.exe scripts\check_env.py
if errorlevel 1 (
    echo [ERROR] Environment diagnostics failed.
    pause
    exit /b 1
)

echo [5/5] Starting Streamlit app via local venv python...
.venv\Scripts\python.exe -m streamlit run "app\main.py"
if errorlevel 1 (
    echo [ERROR] Streamlit app failed to start.
    pause
    exit /b 1
)

endlocal

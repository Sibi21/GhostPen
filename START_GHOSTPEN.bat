@echo off
setlocal enabledelayedexpansion

title GhostPen ? BEC Verification Dashboard

:: Ensure current working directory is the repository root
cd /d "%~dp0"

echo ============================================================
echo   GhostPen: Writing-Style Verification for BEC Defense
echo ============================================================
echo.

:: 1. Detect Python executable
set "PYTHON_CMD="
python --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_CMD=python"
    goto :python_found
)

py -3 --version >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON_CMD=py -3"
    goto :python_found
)

echo [ERROR] Python 3 is not detected on your system.
echo.
echo GhostPen requires Python 3.10 or newer to run.
echo.
echo How to fix:
echo   1. Download Python from: https://www.python.org/downloads/
echo   2. During installation, CHECK the box:
echo        [X] "Add python.exe to PATH"
echo   3. Once installed, double-click START_GHOSTPEN.bat again.
echo.
echo ============================================================
pause
exit /b 1

:python_found
for /f "tokens=*" %%i in ('%PYTHON_CMD% -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"') do set PY_VER=%%i
echo [INFO] Found Python %PY_VER% (%PYTHON_CMD%)

:: 2. Setup or activate isolated virtual environment (.venv)
if not exist ".venv\Scripts\activate.bat" (
    echo [SETUP] Creating isolated virtual environment in .venv...
    %PYTHON_CMD% -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        echo Please ensure the Python venv module is installed.
        pause
        exit /b 1
    )
    echo [SETUP] Virtual environment created.
)

:: Activate the virtual environment
call .venv\Scripts\activate.bat
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)

:: 3. Install or update dependencies
echo [SETUP] Verifying Python dependencies from requirements.txt...
python -m pip install -r requirements.txt --disable-pip-version-check
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Failed to install required packages.
    pause
    exit /b 1
)

:: 4. Run pre-flight readiness check
echo.
echo [CHECK] Running pre-flight system check...
python scripts\check_ready.py
if %ERRORLEVEL% neq 0 (
    echo [ERROR] System readiness check failed. See details above.
    pause
    exit /b 1
)

:: 5. Launch Streamlit dashboard
echo.
echo ============================================================
echo   Launching GhostPen Interactive Dashboard
echo ============================================================
echo [INFO] Opening http://localhost:8501 in your default browser...
echo [INFO] To STOP the dashboard at any time, press Ctrl+C.
echo.

python -m streamlit run app\app.py --server.headless=false

echo.
echo GhostPen has stopped.
pause

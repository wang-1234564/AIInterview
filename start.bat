@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem One-click launcher for Windows.
rem Usage:  start.bat [port]        (default 8000)
rem         set NO_BROWSER=1 before running to skip opening the browser.

set "PORT=8000"
if not "%~1"=="" set "PORT=%~1"

echo ============================================
echo   AI Mock Interview - One-Click Launcher
echo ============================================
echo.

rem ---------- 1/4 Locate Python 3.11+ ----------
set "PY_BIN="
call :find_python
if not defined PY_BIN (
    echo [ERROR] Python 3.11+ not found.
    echo         Install it from https://www.python.org/downloads/ and rerun.
    pause
    exit /b 1
)
echo [1/4] Python detected: %PY_BIN%

rem ---------- 2/4 Virtual environment ----------
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" (
    echo [2/4] Creating virtual environment .venv ...
    %PY_BIN% -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create the virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [2/4] Virtual environment ready.
)

rem ---------- 3/4 Dependencies (reinstall when requirements.txt changes) ----------
"%PY%" -c "import hashlib,os,sys;p='.venv/.deps_sha256';h=hashlib.sha256(open('requirements.txt','rb').read()).hexdigest();sys.exit(0 if (os.path.exists(p) and open(p).read().strip()==h) else 1)" >nul 2>nul
if errorlevel 1 (
    echo [3/4] Installing/updating dependencies ^(first run may take a few minutes^)...
    "%PY%" -m pip install --quiet --upgrade pip
    "%PY%" -m pip install --quiet -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
    "%PY%" -c "import hashlib;open('.venv/.deps_sha256','w').write(hashlib.sha256(open('requirements.txt','rb').read()).hexdigest())"
) else (
    echo [3/4] Dependencies ready.
)

rem ---------- 4/4 Start ----------
if not exist ".env" copy /y ".env.example" ".env" >nul

echo [4/4] Starting server at http://127.0.0.1:%PORT%
echo       Configure your LLM provider and API key on the web Settings page.
echo       Press Ctrl+C to stop.
echo.

if not defined NO_BROWSER start "" /b cmd /c "ping 127.0.0.1 -n 3 >nul & start http://127.0.0.1:%PORT%"

"%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
exit /b 0


rem ==================== subroutines ====================

:find_python
where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "PY_BIN=python"
        exit /b 0
    )
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
    if not errorlevel 1 (
        set "PY_BIN=py -3"
        exit /b 0
    )
)
exit /b 0

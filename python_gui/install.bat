@echo off
REM ===========================================================================
REM  GoldApp Desktop - installer (Windows)
REM  Creates a local virtual environment and installs dependencies.
REM  Run once after copying the folder to a new machine.
REM ===========================================================================
setlocal
cd /d "%~dp0"

echo.
echo === GoldApp Desktop - install ===
echo.

REM --- locate Python ---
where py >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PY=py -3"
) else (
    where python >nul 2>nul
    if %ERRORLEVEL%==0 (
        set "PY=python"
    ) else (
        echo [ERROR] Python 3 was not found on PATH.
        echo         Install Python 3.11+ from https://www.python.org/downloads/
        echo         and tick "Add python.exe to PATH" during setup.
        pause
        exit /b 1
    )
)

echo Using interpreter: %PY%
%PY% --version

REM --- create venv (one level up, beside the package) ---
if not exist "..\.venv\Scripts\python.exe" (
    echo Creating virtual environment in ..\.venv ...
    %PY% -m venv "..\.venv"
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo Virtual environment already exists - reusing.
)

set "VENV_PY=..\.venv\Scripts\python.exe"

echo Upgrading pip ...
"%VENV_PY%" -m pip install --upgrade pip

echo Installing dependencies from requirements.txt ...
"%VENV_PY%" -m pip install -r requirements.txt
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Dependency installation failed.
    pause
    exit /b 1
)

echo.
echo === Done. ===
echo Start the app with run.bat   (build a .exe with build.bat)
echo.
pause
endlocal

@echo off
REM ===========================================================================
REM  GoldApp Desktop - launcher (Windows)
REM  Uses the local virtual environment if present, else the system Python.
REM  The app reads the Laravel .env for DB credentials (see core/config.py).
REM ===========================================================================
setlocal
cd /d "%~dp0"

if exist "..\.venv\Scripts\python.exe" (
    set "RUN_PY=..\.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul && (set "RUN_PY=py -3") || (set "RUN_PY=python")
    echo [WARN] Virtual environment not found - using system Python.
    echo        Run install.bat first if startup fails.
)

REM run as a package from the repo root so relative imports resolve
cd /d "%~dp0.."
"%RUN_PY%" -m python_gui.main
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] The application exited with an error.
    pause
)
endlocal

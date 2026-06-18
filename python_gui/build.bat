@echo off
REM ===========================================================================
REM  GoldApp Desktop - build a standalone Windows .exe (PyInstaller one-folder)
REM  Requires install.bat to have been run first (pyinstaller is in requirements).
REM  Output: dist\GoldApp\GoldApp.exe
REM ===========================================================================
setlocal
cd /d "%~dp0.."

if exist ".venv\Scripts\python.exe" (
    set "BUILD_PY=.venv\Scripts\python.exe"
) else (
    where py >nul 2>nul && (set "BUILD_PY=py -3") || (set "BUILD_PY=python")
)

echo Cleaning previous build ...
if exist "build\GoldApp" rmdir /s /q "build\GoldApp"
if exist "dist\GoldApp"  rmdir /s /q "dist\GoldApp"

echo Building GoldApp.exe ...
"%BUILD_PY%" -m PyInstaller --noconfirm --clean python_gui\goldapp.spec
if %ERRORLEVEL% neq 0 (
    echo.
    echo [ERROR] Build failed.
    pause
    exit /b 1
)

echo.
echo === Build complete ===
echo Executable: dist\GoldApp\GoldApp.exe
echo Copy the dist\GoldApp folder to the target machine. Place the Laravel .env
echo beside GoldApp.exe or set the GOLDAPP_ENV environment variable.
echo.
pause
endlocal

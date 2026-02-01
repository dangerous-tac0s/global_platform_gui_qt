@echo off
REM Build Windows executable for GlobalPlatform GUI
setlocal enabledelayedexpansion

echo === Building GlobalPlatform GUI for Windows ===

REM Get script directory and project root
set "SCRIPT_DIR=%~dp0"
set "PROJECT_ROOT=%SCRIPT_DIR%..\.."

cd /d "%PROJECT_ROOT%"

REM Check for pyinstaller
where pyinstaller >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: pyinstaller not found. Install with: pip install pyinstaller
    exit /b 1
)

REM Clean previous builds
echo Cleaning previous builds...
if exist "dist\gp_gui.exe" del /f "dist\gp_gui.exe"
if exist "build\gp_gui" rmdir /s /q "build\gp_gui"

REM Run PyInstaller
echo Running PyInstaller...
pyinstaller --clean --noconfirm windows.spec

if %errorlevel% neq 0 (
    echo Build failed!
    exit /b 1
)

echo.
echo === Build Complete ===
echo Executable: dist\gp_gui.exe
echo.
echo To create installer, use NSIS or Inno Setup with the executable.

endlocal

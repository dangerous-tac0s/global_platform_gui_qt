@echo off
REM Build Windows executable for GlobalPlatform GUI
REM
REM REQUIREMENTS:
REM   - Python 3.9 (PyQt5 has compatibility issues with Python 3.10+)
REM   - pip install -r requirements-win.txt
REM
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

set "EXE_PATH=dist\gp_gui.exe"

REM ============================================
REM Windows Authenticode Signing (Optional)
REM ============================================
REM To enable: set SIGNTOOL_CERT=path\to\certificate.pfx
REM            set SIGNTOOL_PASSWORD=certificate-password
REM Or for hardware token: set SIGNTOOL_THUMBPRINT=certificate-thumbprint

if defined SIGNTOOL_CERT (
    echo.
    echo === Windows Authenticode Signing ===
    where signtool >nul 2>&1
    if %errorlevel% equ 0 (
        echo Signing with certificate: %SIGNTOOL_CERT%
        signtool sign /f "%SIGNTOOL_CERT%" /p "%SIGNTOOL_PASSWORD%" /tr http://timestamp.digicert.com /td sha256 /fd sha256 "%EXE_PATH%"
        if %errorlevel% equ 0 (
            echo Authenticode signature applied successfully
            signtool verify /pa "%EXE_PATH%"
        ) else (
            echo Warning: Authenticode signing failed
        )
    ) else (
        echo Warning: signtool not found. Install Windows SDK for Authenticode signing.
    )
) else if defined SIGNTOOL_THUMBPRINT (
    echo.
    echo === Windows Authenticode Signing ^(Hardware Token^) ===
    where signtool >nul 2>&1
    if %errorlevel% equ 0 (
        echo Signing with certificate thumbprint: %SIGNTOOL_THUMBPRINT%
        signtool sign /sha1 "%SIGNTOOL_THUMBPRINT%" /tr http://timestamp.digicert.com /td sha256 /fd sha256 "%EXE_PATH%"
        if %errorlevel% equ 0 (
            echo Authenticode signature applied successfully
        ) else (
            echo Warning: Authenticode signing failed
        )
    ) else (
        echo Warning: signtool not found
    )
) else (
    echo.
    echo Note: Skipping Authenticode signing ^(SIGNTOOL_CERT or SIGNTOOL_THUMBPRINT not set^)
    echo To sign with certificate file:
    echo   set SIGNTOOL_CERT=path\to\certificate.pfx
    echo   set SIGNTOOL_PASSWORD=password
    echo To sign with hardware token:
    echo   set SIGNTOOL_THUMBPRINT=certificate-thumbprint
)

REM ============================================
REM GPG Signing (Optional)
REM ============================================
if "%SIGN_GPG%"=="true" (
    echo.
    echo === GPG Signing ===
    where gpg >nul 2>&1
    if %errorlevel% equ 0 (
        set "GPG_ARGS=--detach-sign --armor"
        if defined GPG_KEY (
            set "GPG_ARGS=!GPG_ARGS! --default-key !GPG_KEY!"
        )
        echo Creating GPG signature...
        gpg !GPG_ARGS! "%EXE_PATH%"
        if exist "%EXE_PATH%.asc" (
            echo GPG signature created: %EXE_PATH%.asc
        ) else (
            echo Warning: GPG signing may have failed
        )
    ) else (
        echo Warning: gpg not found, skipping GPG signing
    )
)

REM Generate checksum
echo.
echo === Generating Checksum ===
certutil -hashfile "%EXE_PATH%" SHA256 > "dist\gp_gui.exe.sha256"
echo SHA256 checksum saved to dist\gp_gui.exe.sha256

echo.
echo === Build Complete ===
echo Executable: %EXE_PATH%
echo Checksum:   dist\gp_gui.exe.sha256
if exist "%EXE_PATH%.asc" echo GPG Sig:    %EXE_PATH%.asc
echo.
echo To create installer, use NSIS or Inno Setup with the executable.
echo.
echo Build options:
echo   set SIGN_GPG=true ^& set GPG_KEY=key-id ^& build_windows.bat
echo   set SIGNTOOL_CERT=cert.pfx ^& set SIGNTOOL_PASSWORD=pass ^& build_windows.bat

endlocal

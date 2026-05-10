@echo off
setlocal
echo =============================================
echo  D2R Counter - Build Script
echo =============================================
echo.
echo  [R] Release  — no console window (for distribution)
echo  [D] Dev      — console window visible (for local testing)
echo.
set /p BUILD_TYPE="Choose build type [R/D]: "

if /i "%BUILD_TYPE%"=="D" (
    set CONSOLE_FLAG=--console
    set BUILD_NAME=D2RCounter-dev
    echo.
    echo Building DEV build (console visible^)...
) else (
    set CONSOLE_FLAG=--noconsole
    set BUILD_NAME=D2RCounter
    echo.
    echo Building RELEASE build (no console^)...
)

echo.
echo [1/2] Installing dependencies...
pip install --upgrade pyinstaller scapy psutil PyQt6
if errorlevel 1 ( echo ERROR: pip install failed. & pause & exit /b 1 )

echo.
echo [2/2] Running PyInstaller...
pyinstaller ^
    %CONSOLE_FLAG% ^
    --icon=off.ico ^
    --add-data "off.ico;." ^
    --name %BUILD_NAME% ^
    main.py
if errorlevel 1 ( echo ERROR: PyInstaller failed. & pause & exit /b 1 )

echo.
echo Done. Output: dist\%BUILD_NAME%\%BUILD_NAME%.exe
echo.
if /i "%BUILD_TYPE%"=="D" (
    echo Dev build — console window will appear on launch.
) else (
    echo Release build — runs silently with no terminal window.
    echo REMINDER: Npcap must be installed on the target machine.
    echo           https://npcap.com/#download
)
echo.
pause

@echo off
setlocal
echo =============================================
echo  D2R Counter - Build Script
echo =============================================
echo.

echo [1/3] Installing Python dependencies...
pip install --upgrade pyinstaller scapy psutil PyQt6
if errorlevel 1 (
    echo ERROR: pip install failed.
    pause
    exit /b 1
)
echo.

echo [2/3] Running PyInstaller...
pyinstaller ^
    --onedir ^
    --console ^
    --icon=off.ico ^
    --add-data "off.ico;." ^
    --name D2RCounter ^
    main.py
if errorlevel 1 (
    echo ERROR: PyInstaller failed.
    pause
    exit /b 1
)
echo.

echo [3/3] Done.
echo Output: dist\D2RCounter\D2RCounter.exe
echo.
echo IMPORTANT: Npcap must be installed separately on the target machine.
echo            https://npcap.com/#download
echo.
pause

@echo off
setlocal
cd /d "%~dp0"
title UniversalDownloader

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 (
    echo.
    echo [!] UniversalDownloader encountered an error during startup.
    echo Press any key to exit...
    pause >nul
)

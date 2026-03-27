@echo off
title Never Sleep - Fake Session Monitor
echo ============================================================
echo   Never Sleep - Fake Remote Session Simulator
echo   Blocking: Sleep / Hibernate / Shutdown / Restart
echo ============================================================
echo.

:: Check for admin rights
net session >nul 2>&1
if %errorlevel% == 0 (
    echo   [OK] Running as Administrator
) else (
    echo   [!] NOT running as Administrator
    echo   [!] For full protection, right-click and "Run as administrator"
    echo.
)

:: Check Python
python --version >nul 2>&1
if %errorlevel% == 0 (
    echo   [OK] Python found
    echo.
    python "%~dp0fake_session.py" %*
) else (
    py --version >nul 2>&1
    if %errorlevel% == 0 (
        echo   [OK] Python found
        echo.
        py "%~dp0fake_session.py" %*
    ) else (
        echo   [ERROR] Python not found!
        echo   Please install Python from https://www.python.org/downloads/
        echo   Make sure to check "Add Python to PATH" during installation.
        echo.
        pause
    )
)

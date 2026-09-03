@echo off
REM ==============================================================================
REM Windows Task Scheduler Installer for IPO Tracker & GMP Alert System
REM Creates 2 scheduled tasks:
REM   1. IPO_Tracker_Morning_8AM   -> Runs daily at 08:00 AM IST
REM   2. IPO_Tracker_Reminder_1230PM -> Runs daily at 12:30 PM IST
REM ==============================================================================

echo ====================================================================
echo  Setting up Windows Task Scheduler for Indian IPO Tracker...
echo ====================================================================

REM Locate python executable
for /f "delims=" %%i in ('where python') do set PYTHON_EXE=%%i & goto :found_python
:found_python

if not defined PYTHON_EXE (
    echo [ERROR] Python was not found in your PATH! Please install Python.
    pause
    exit /b 1
)

set SCRIPT_DIR=%~dp0
set RUN_NOW_CMD=\"%PYTHON_EXE%\" \"%SCRIPT_DIR%main.py\" --run-now
set REMINDER_CMD=\"%PYTHON_EXE%\" \"%SCRIPT_DIR%main.py\" --run-reminder

echo Python Path: %PYTHON_EXE%
echo Project Dir: %SCRIPT_DIR%
echo.

echo Registering Task 1: IPO_Tracker_Morning_8AM (08:00 AM Daily)...
schtasks /create /tn "IPO_Tracker_Morning_8AM" /tr "%RUN_NOW_CMD%" /sc daily /st 08:00 /f
if %ERRORLEVEL% equ 0 (
    echo [OK] Morning 8:00 AM task registered successfully!
) else (
    echo [WARNING] Failed to register morning task. You may need to Run as Administrator.
)

echo.
echo Registering Task 2: IPO_Tracker_Reminder_230PM (02:30 PM Daily)...
schtasks /create /tn "IPO_Tracker_Reminder_230PM" /tr "%REMINDER_CMD%" /sc daily /st 14:30 /f
if %ERRORLEVEL% equ 0 (
    echo [OK] Reminder 2:30 PM task registered successfully!
) else (
    echo [WARNING] Failed to register reminder task. You may need to Run as Administrator.
)

echo.
echo Configuring power and wake settings...
powershell -Command "$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -WakeToRun -StartWhenAvailable; Set-ScheduledTask -TaskName 'IPO_Tracker_Morning_8AM' -Settings $s; Set-ScheduledTask -TaskName 'IPO_Tracker_Reminder_230PM' -Settings $s" >nul 2>&1
echo ====================================================================
echo  Setup Complete! Your IPO Tracker will now run daily at:
echo   - 08:00 AM IST (Morning Alert for GMP ^> 10%%)
echo   - 02:30 PM IST (Reminder Alert for IPOs closing today)
echo ====================================================================
pause

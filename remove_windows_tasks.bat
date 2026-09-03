@echo off
REM ==============================================================================
REM Uninstaller for IPO Tracker Windows Scheduled Tasks
REM ==============================================================================

echo Removing IPO Tracker Windows Scheduled Tasks...

schtasks /delete /tn "IPO_Tracker_Morning_8AM" /f >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [OK] Removed IPO_Tracker_Morning_8AM
) else (
    echo [INFO] IPO_Tracker_Morning_8AM not found or already removed.
)

schtasks /delete /tn "IPO_Tracker_Reminder_230PM" /f >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [OK] Removed IPO_Tracker_Reminder_230PM
) else (
    echo [INFO] IPO_Tracker_Reminder_230PM not found or already removed.
)

schtasks /delete /tn "IPO_Tracker_Reminder_1230PM" /f >nul 2>&1

echo.
echo All IPO Tracker scheduled tasks have been cleaned up.
pause

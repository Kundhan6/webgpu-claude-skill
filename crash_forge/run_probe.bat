@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"

rem === run_probe.bat ==========================================================
rem Runs the Crash Forge Stage 0 API probe (crash_forge\tests\blender_probe_script.py)
rem against a real Blender install and writes the report to probe.txt.
rem
rem Usage:
rem   1. Double-click this file. It tries to find blender.exe on its own.
rem   2. If it can't, drag your blender.exe and drop it directly onto this
rem      .bat file - that re-runs it with the right path as %1.
rem =============================================================================

set "BLENDER_EXE="

if not "%~1"=="" (
    if exist "%~1" (
        set "BLENDER_EXE=%~1"
    ) else (
        echo The path you dropped does not exist: %~1
        echo.
    )
)

if not defined BLENDER_EXE (
    for /f "usebackq delims=" %%P in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0find_blender.ps1"`) do (
        set "BLENDER_EXE=%%P"
    )
)

if not defined BLENDER_EXE (
    echo.
    echo Could not find blender.exe automatically.
    echo.
    echo Checked: the registry ^(blendfile file association^), C:\Program Files\Blender Foundation\Blender *\,
    echo C:\Program Files ^(x86^)\Steam\steamapps\common\Blender\, and %%LOCALAPPDATA%%\Microsoft\WindowsApps\.
    echo.
    echo Fix: drag blender.exe from your Blender install folder and drop it
    echo directly onto this file ^(run_probe.bat^), then let go. That re-runs
    echo this script with the right path.
    echo.
    pause
    exit /b 1
)

if not exist "!BLENDER_EXE!" (
    echo.
    echo Detected path does not exist: !BLENDER_EXE!
    echo Drag blender.exe onto this .bat file to specify it directly.
    echo.
    pause
    exit /b 1
)

echo Blender: !BLENDER_EXE!
echo Blender: !BLENDER_EXE! > probe.txt
echo. >> probe.txt

"!BLENDER_EXE!" --background --python "tests\blender_probe_script.py" >> probe.txt 2>&1

echo.
echo Probe finished. Opening probe.txt...
start "" notepad.exe "probe.txt"

pause

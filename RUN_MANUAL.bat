@echo off
REM ====================================================================
REM  Valve Diagnostics v3 - MANUAL mode runner (drag-and-drop)
REM
REM  Same as RUN_AUTO.bat but uses your DIAGNOSTIC_CONFIG values
REM  exactly as written - no auto-calibration.
REM
REM  This mode produces results identical to v2 on the diagnostics
REM  side. The v3 wrapper (health check, repair, outlier reports)
REM  still runs.
REM ====================================================================

setlocal
cd /d "%~dp0"

if "%~1"=="" (
    echo.
    echo ============================================================
    echo   Valve Diagnostics v3 - MANUAL mode
    echo ============================================================
    echo.
    echo No input file given.
    echo.
    echo HOW TO USE:
    echo   1. Find your Excel data file in Windows Explorer.
    echo   2. Drag it onto this RUN_MANUAL.bat file.
    echo.
    pause
    exit /b 1
)

where python >nul 2>&1
if %errorlevel%==0 (
    set "PY=python"
) else (
    where py >nul 2>&1
    if %errorlevel%==0 (
        set "PY=py -3"
    ) else (
        echo ERROR: Python not found. Run INSTALL.bat first.
        pause
        exit /b 1
    )
)

set "INPUT=%~1"
set "BASENAME=%~n1"
set "OUTDIR=%~dp0results_%BASENAME%_manual"

echo.
echo ============================================================
echo   Valve Diagnostics v3 - MANUAL mode
echo ============================================================
echo.
echo Input:   %INPUT%
echo Output:  %OUTDIR%
echo.

%PY% valve_diagnostics_v3.py --input "%INPUT%" --output-dir "%OUTDIR%" --manual
set RC=%errorlevel%

echo.
if %RC%==0 (
    echo ============================================================
    echo   Done. Results in:
    echo   %OUTDIR%
    echo ============================================================
    explorer "%OUTDIR%"
) else (
    echo ============================================================
    echo   The tool finished with code %RC%.
    echo ============================================================
    echo.
    echo See %OUTDIR%\health_check_report.txt
)
echo.
pause
endlocal

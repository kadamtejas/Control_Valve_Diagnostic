@echo off
REM ====================================================================
REM  Valve Diagnostics v3 - AUTO mode runner (drag-and-drop)
REM
REM  How to use:
REM    Drag your Excel file onto this .bat file.
REM    Results appear in a folder named "results_<your_filename>"
REM    next to this .bat file.
REM
REM  AUTO mode = the tool calibrates its own thresholds from your data.
REM  Use RUN_MANUAL.bat to use your DIAGNOSTIC_CONFIG values instead.
REM ====================================================================

setlocal
cd /d "%~dp0"

if "%~1"=="" (
    echo.
    echo ============================================================
    echo   Valve Diagnostics v3 - AUTO mode
    echo ============================================================
    echo.
    echo No input file given.
    echo.
    echo HOW TO USE:
    echo   1. Find your Excel data file in Windows Explorer.
    echo   2. Drag it onto this RUN_AUTO.bat file.
    echo   3. The tool will run and produce a results folder.
    echo.
    echo Or, run from the command line:
    echo   RUN_AUTO.bat "C:\path\to\your_file.xlsx"
    echo.
    pause
    exit /b 1
)

REM Pick a Python interpreter
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

REM Output dir = results_<basename>
set "INPUT=%~1"
set "BASENAME=%~n1"
set "OUTDIR=%~dp0results_%BASENAME%"

echo.
echo ============================================================
echo   Valve Diagnostics v3 - AUTO mode
echo ============================================================
echo.
echo Input:   %INPUT%
echo Output:  %OUTDIR%
echo.

%PY% valve_diagnostics_v3.py --input "%INPUT%" --output-dir "%OUTDIR%"
set RC=%errorlevel%

echo.
if %RC%==0 (
    echo ============================================================
    echo   Done. Results are in:
    echo   %OUTDIR%
    echo ============================================================
    echo.
    echo Open the folder above and look at:
    echo   - v3_run_summary.txt  (overall summary)
    echo   - Loop_diagnostics_v2.xlsx  (Excel report)
    echo   - Executive_summary.pdf
    echo   - health_check_report.txt
    explorer "%OUTDIR%"
) else (
    echo ============================================================
    echo   The tool finished with code %RC%.
    echo ============================================================
    echo.
    echo If the health check found problems, see:
    echo   %OUTDIR%\health_check_report.txt
)
echo.
pause
endlocal

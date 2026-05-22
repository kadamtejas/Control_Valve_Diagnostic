@echo off
REM ====================================================================
REM  Valve Diagnostics v3 - Test on real plant data
REM
REM  Runs the tool against the bundled My_plant_data_1.xlsx
REM  (10 loops from a real ethanol plant).
REM ====================================================================

setlocal
cd /d "%~dp0"

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

echo.
echo ============================================================
echo   Valve Diagnostics v3 - Test on real plant data
echo ============================================================
echo.

%PY% valve_diagnostics_v3.py --input "test_data\My_plant_data_1.xlsx" --output-dir "results_real_plant"

echo.
echo ============================================================
echo   Done.
echo ============================================================
echo.
explorer "results_real_plant"
pause
endlocal

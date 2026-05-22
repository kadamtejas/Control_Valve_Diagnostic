@echo off
REM ====================================================================
REM  Valve Diagnostics v3 - Test on synthetic data
REM
REM  Runs the tool against the bundled synthetic_test_data.xlsx
REM  (8 loops with known faults). Use this to confirm the install
REM  is working correctly.
REM
REM  Expected output: 8 loops correctly diagnosed.
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
echo   Valve Diagnostics v3 - Test run on synthetic data
echo ============================================================
echo.
echo This runs the tool on the bundled test_data\synthetic_test_data.xlsx
echo to confirm everything is installed correctly.
echo.
echo Expected: 8 loops, 8 correctly diagnosed.
echo.

%PY% valve_diagnostics_v3.py --input "test_data\synthetic_test_data.xlsx" --output-dir "results_synthetic_test_data"

echo.
echo ============================================================
echo   Done.
echo ============================================================
echo.
echo Open the results folder and check Loop_diagnostics_v2.xlsx
echo (the Summary sheet should list 8 loops with diagnoses).
echo.
echo Expected diagnoses:
echo   FIC_101 - Healthy
echo   FIC_102 - Healthy
echo   TIC_103 - Healthy
echo   FIC_104 - Saturation (valve fully open)
echo   PIC_105 - Aggressive tuning (oscillation)
echo   TIC_106 - Unresponsive controller
echo   AIC_107 - Sensor issue (frozen PV)
echo   FIC_108 - Loop in MAN (low service factor)
echo.
explorer "results_synthetic_test_data"
pause
endlocal

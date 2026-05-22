@echo off
REM ====================================================================
REM  Valve Diagnostics v3 - Installer
REM  Installs the Python libraries the tool needs.
REM  Run this once, the first time you set up the tool.
REM ====================================================================

setlocal
cd /d "%~dp0"

echo.
echo ============================================================
echo   Valve Diagnostics v3 - Installer
echo ============================================================
echo.

REM Find a Python interpreter
where python >nul 2>&1
if %errorlevel%==0 (
    set "PY=python"
    goto FOUND_PY
)
where py >nul 2>&1
if %errorlevel%==0 (
    set "PY=py -3"
    goto FOUND_PY
)

echo ERROR: Python is not installed, or it's not on your PATH.
echo.
echo Fix:
echo   1. Download Python from https://www.python.org/downloads/
echo   2. During install, tick "Add Python to PATH"
echo   3. Restart this computer
echo   4. Run INSTALL.bat again
echo.
pause
exit /b 1

:FOUND_PY
echo Using Python: %PY%
%PY% --version
echo.

echo Installing required libraries...
echo (This will take about a minute the first time.)
echo.

%PY% -m pip install --upgrade pip
if errorlevel 1 (
    echo.
    echo WARNING: pip upgrade failed. Continuing anyway.
    echo.
)

%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ============================================================
    echo   ERROR: Library installation failed.
    echo ============================================================
    echo.
    echo Possible causes:
    echo   - No internet connection
    echo   - Corporate proxy blocks pip
    echo   - Antivirus blocked the install
    echo.
    echo If you have a corporate proxy, ask IT for the proxy URL,
    echo then run:
    echo     %PY% -m pip install --proxy http://YOUR_PROXY:PORT -r requirements.txt
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   Installation complete.
echo ============================================================
echo.
echo Next: try double-clicking RUN_TEST_SYNTHETIC.bat to confirm
echo       everything works.
echo.
pause
endlocal

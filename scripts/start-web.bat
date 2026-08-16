@echo off
rem ============================================================
rem  iris-web - start the local gallery and open a browser.
rem  Keep this window open: it is the server.
rem  Close it, or press Ctrl-C, to stop.
rem ============================================================
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
cd /d "%ROOT%"

where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo Python is not on PATH. Install it from python.org, or from
    echo the Microsoft Store, then run this again.
    echo.
    pause
    exit /b 1
)

echo.
echo   Starting iris-web. The address appears below.
echo   Keep this window open.
echo.
python iris_web.py %*
pause

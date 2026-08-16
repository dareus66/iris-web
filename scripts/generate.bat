@echo off
setlocal enabledelayedexpansion
rem ============================================================
rem  iris-web - generate one image from the command line (Windows)
rem
rem  Usage:
rem    double click                    -> asks for a prompt
rem    generate.bat "a cat"            -> that prompt, 512x512, new seed
rem    generate.bat "a cat" 512 12345  -> makes the same image again
rem
rem  The seed goes into the file name and into images\catalog.jsonl,
rem  so every picture stays repeatable.
rem ============================================================

rem --- root of the project (this file lives in scripts\) ---
for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "IMAGES=%ROOT%\images"

rem --- find the iris binary ---
set "IRIS="
for %%P in ("%ROOT%\iris.exe" "%ROOT%\iris.c\iris.exe" "%ROOT%\..\iris.c\iris.exe") do (
    if not defined IRIS if exist "%%~P" set "IRIS=%%~fP"
)
if not defined IRIS (
    echo.
    echo Cannot find iris.exe.
    echo Build it from https://github.com/antirez/iris.c and put it next to
    echo this project, or in an iris.c folder beside it.
    echo.
    pause
    exit /b 1
)
for %%I in ("!IRIS!") do set "IRISDIR=%%~dpI"

rem --- find a model directory (one holding model_index.json) ---
set "MODEL="
for /d %%D in ("!IRISDIR!*") do (
    if not defined MODEL if exist "%%~fD\model_index.json" set "MODEL=%%~fD"
)
if not defined MODEL (
    echo.
    echo Cannot find a model folder next to iris.exe.
    echo Download one with iris's download_model.py.
    echo.
    pause
    exit /b 1
)

rem --- MSYS2 runtime DLLs, if this is a MinGW build ---
for %%P in ("C:\msys64\ucrt64\bin" "C:\msys2\ucrt64\bin" "C:\msys64\mingw64\bin") do (
    if exist "%%~P" set "PATH=%%~P;!PATH!"
)

rem --- one BLAS thread per physical core, roughly ---
set /a THREADS=%NUMBER_OF_PROCESSORS% / 2
if !THREADS! LSS 1 set THREADS=1

rem --- prompt ---
set "TEXT=%~1"
if "!TEXT!"=="" (
    echo.
    set /p "TEXT=What should it be a picture of? "
)
if "!TEXT!"=="" (
    echo Nothing to generate.
    pause
    exit /b 1
)

rem --- size, default 512 ---
set "DIM=%~2"
if "!DIM!"=="" set "DIM=512"

rem --- seed: given, or a fresh one, but never left to chance ---
set "SEED=%~3"
if "!SEED!"=="" for /f %%s in ('powershell -NoProfile -Command "Get-Random -Maximum 2147483000"') do set "SEED=%%s"

for /f "tokens=1-6 delims=/:. " %%a in ("%date% %time%") do set "STAMP=%%c%%b%%a_%%d%%e"
if not exist "!IMAGES!" mkdir "!IMAGES!"
set "OUT=!IMAGES!\iris_!STAMP!_s!SEED!.png"

echo.
echo   prompt  : !TEXT!
echo   size    : !DIM!x!DIM!
echo   seed    : !SEED!
echo   output  : !OUT!
echo.
echo   Working. This takes minutes, not seconds.
echo.

"!IRIS!" -d "!MODEL!" --blas-threads !THREADS! --seed !SEED! ^
    -p "!TEXT!" -W !DIM! -H !DIM! -o "!OUT!"
set "RC=!ERRORLEVEL!"

rem --- record it, so the picture can be made again ---
if "!RC!"=="0" (
    set "IRIS_FILE=!OUT!"
    set "IRIS_PROMPT=!TEXT!"
    set "IRIS_SEED=!SEED!"
    set "IRIS_W=!DIM!"
    set "IRIS_H=!DIM!"
    set "IRIS_CAT=!IMAGES!\catalog.jsonl"
    powershell -NoProfile -Command ^
      "$r=[ordered]@{file=(Split-Path $env:IRIS_FILE -Leaf); prompt=$env:IRIS_PROMPT; seed=[int]$env:IRIS_SEED; width=[int]$env:IRIS_W; height=[int]$env:IRIS_H; input=$null; date=(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')}; [System.IO.File]::AppendAllText($env:IRIS_CAT, ($r|ConvertTo-Json -Compress) + \"`r`n\", (New-Object System.Text.UTF8Encoding($false)))"
    echo.
    echo   Done: !OUT!
    start "" "!OUT!"
) else (
    echo.
    echo   iris exited with code !RC!
)
echo.
pause

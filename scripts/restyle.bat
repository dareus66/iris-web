@echo off
setlocal enabledelayedexpansion
rem ============================================================
rem  iris-web - redraw your own picture in a chosen style (Windows)
rem
rem  Usage:
rem    drag an image onto this file      (easiest)
rem    restyle.bat "C:\path\photo.jpg"
rem
rem  Accepts PNG, JPEG and PPM. NOT accepted: TIFF, BMP, WEBP,
rem  HEIC (the default on iPhones), PDF - convert those first.
rem  Large photos are scaled down automatically; the aspect ratio
rem  of the output follows the input.
rem ============================================================

for %%I in ("%~dp0..") do set "ROOT=%%~fI"
set "IMAGES=%ROOT%\images"

rem --- find the iris binary ---
set "IRIS="
for %%P in ("%ROOT%\iris.exe" "%ROOT%\iris.c\iris.exe" "%ROOT%\..\iris.c\iris.exe") do (
    if not defined IRIS if exist "%%~P" set "IRIS=%%~fP"
)
if not defined IRIS (
    echo. & echo Cannot find iris.exe. See the README. & echo.
    pause & exit /b 1
)
for %%I in ("!IRIS!") do set "IRISDIR=%%~dpI"

set "MODEL="
for /d %%D in ("!IRISDIR!*") do (
    if not defined MODEL if exist "%%~fD\model_index.json" set "MODEL=%%~fD"
)
if not defined MODEL (
    echo. & echo Cannot find a model folder next to iris.exe. & echo.
    pause & exit /b 1
)

for %%P in ("C:\msys64\ucrt64\bin" "C:\msys2\ucrt64\bin" "C:\msys64\mingw64\bin") do (
    if exist "%%~P" set "PATH=%%~P;!PATH!"
)

set /a THREADS=%NUMBER_OF_PROCESSORS% / 2
if !THREADS! LSS 1 set THREADS=1

rem ---------- 1. the picture to redraw ----------
set "IMG=%~1"
if "!IMG!"=="" (
    echo.
    echo   Drag the image here and press Enter
    set /p "IMG=  image: "
)
set "IMG=!IMG:"=!"

if not exist "!IMG!" (
    echo. & echo Cannot find that file: !IMG! & echo.
    pause & exit /b 1
)

set "EXT=%~x1"
if "!EXT!"=="" for %%F in ("!IMG!") do set "EXT=%%~xF"
echo !EXT! | findstr /i /c:".png" /c:".jpg" /c:".jpeg" /c:".ppm" >nul
if errorlevel 1 (
    echo.
    echo   !EXT! is not one of the readable formats ^(PNG, JPG, JPEG, PPM^).
    echo   Convert it first if this fails.
    echo.
    set /p "GO=  Try anyway? (y/n): "
    if /i not "!GO!"=="y" exit /b 1
)

rem ---------- 2. what is in the picture ----------
echo.
echo   Describe in a few words what the picture shows.
echo   It tells the model what it is redrawing.
echo   Examples: an old stone farmhouse / a woman with sunglasses
echo.
set /p "SUBJECT=  subject (Enter to skip): "

rem ---------- 3. style ----------
echo.
echo   Which style?
echo.
echo     1  watercolour
echo     2  oil paint
echo     3  pencil
echo     4  ink
echo     5  35mm film
echo     6  art nouveau
echo     7  storybook
echo     8  woodcut
echo     9  I will write my own
echo.
set /p "SC=  choice [1-9]: "

if "!SC!"=="1" set "STYLE=a watercolor painting, loose wet brushstrokes, soft washes of colour, visible paper texture"
if "!SC!"=="2" set "STYLE=an oil painting, thick impasto brushstrokes, rich pigment, canvas weave visible"
if "!SC!"=="3" set "STYLE=a graphite pencil drawing, fine hatching and soft shading, white sketchbook paper"
if "!SC!"=="4" set "STYLE=an ink drawing, bold confident black linework, high contrast, minimal flat colour"
if "!SC!"=="5" set "STYLE=a 35mm film photograph, natural grain, warm analogue colour, shallow depth of field"
if "!SC!"=="6" set "STYLE=an Art Nouveau poster, flowing organic outlines, flat decorative colour, ornamental border"
if "!SC!"=="7" set "STYLE=a children's book illustration, gouache texture, warm friendly palette, gentle outlines"
if "!SC!"=="8" set "STYLE=a woodcut print, carved bold lines, limited ink colours, visible grain of the block"
if "!SC!"=="9" (
    echo.
    set /p "STYLE=  style: "
)
if "!STYLE!"=="" (
    echo. & echo No style chosen. & echo.
    pause & exit /b 1
)

rem ---------- 4. size of the long edge ----------
echo.
echo   Long edge of the result. Smaller is quicker: try one small
echo   first, then redo the good one larger with the same seed.
echo.
set /p "LONG=  long edge [Enter for 512]: "
if "!LONG!"=="" set "LONG=512"

rem ---------- 5. keep the aspect ratio, round to multiples of 16 ----------
for /f "tokens=1,2" %%a in ('powershell -NoProfile -Command ^
  "Add-Type -AssemblyName System.Drawing; try { $i=[System.Drawing.Image]::FromFile('!IMG!'); $w=$i.Width; $h=$i.Height; $i.Dispose() } catch { $w=512; $h=512 }; $L=[int]'!LONG!'; if ($w -ge $h) { $ow=$L; $oh=[math]::Round($L*$h/$w) } else { $oh=$L; $ow=[math]::Round($L*$w/$h) }; $ow=[math]::Max(64,[int]([math]::Round($ow/16)*16)); $oh=[math]::Max(64,[int]([math]::Round($oh/16)*16)); \"$ow $oh\""') do (
    set "OW=%%a"
    set "OH=%%b"
)

rem ---------- 6. seed, prompt, file name ----------
set "SEED=%~2"
if "!SEED!"=="" for /f %%s in ('powershell -NoProfile -Command "Get-Random -Maximum 2147483000"') do set "SEED=%%s"

if "!SUBJECT!"=="" (
    set "FULL=!STYLE!"
) else (
    set "FULL=!SUBJECT!, !STYLE!"
)

for /f "tokens=1-6 delims=/:. " %%a in ("%date% %time%") do set "STAMP=%%c%%b%%a_%%d%%e"
if not exist "!IMAGES!" mkdir "!IMAGES!"
set "OUT=!IMAGES!\restyle_!STAMP!_s!SEED!.png"

echo.
echo   from    : !IMG!
echo   style   : !FULL!
echo   seed    : !SEED!
echo   output  : !OUT!  ^(!OW!x!OH!^)
echo.
echo   Working. Do not close this window.
echo.

"!IRIS!" -d "!MODEL!" --blas-threads !THREADS! --seed !SEED! ^
    -i "!IMG!" -p "!FULL!" -W !OW! -H !OH! -o "!OUT!"
set "RC=!ERRORLEVEL!"

if "!RC!"=="0" (
    set "IRIS_FILE=!OUT!"
    set "IRIS_PROMPT=!FULL!"
    set "IRIS_SEED=!SEED!"
    set "IRIS_W=!OW!"
    set "IRIS_H=!OH!"
    set "IRIS_IN=!IMG!"
    set "IRIS_CAT=!IMAGES!\catalog.jsonl"
    powershell -NoProfile -Command ^
      "$r=[ordered]@{file=(Split-Path $env:IRIS_FILE -Leaf); prompt=$env:IRIS_PROMPT; seed=[int]$env:IRIS_SEED; width=[int]$env:IRIS_W; height=[int]$env:IRIS_H; input=$env:IRIS_IN; date=(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')}; [System.IO.File]::AppendAllText($env:IRIS_CAT, ($r|ConvertTo-Json -Compress) + \"`r`n\", (New-Object System.Text.UTF8Encoding($false)))"
    echo.
    echo   Done: !OUT!
    start "" "!OUT!"
) else (
    echo.
    echo   iris exited with code !RC!
)
echo.
pause

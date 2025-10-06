@echo off
setlocal EnableDelayedExpansion

set folder=%~1
set toolspath=%~dp0\..\tools
SET PA="%toolspath%\pa\pa.exe"

for /r "%folder%" %%v in (*.bin) do (

    SET FILEPATH=%%~dv%%~pv%%~nv
    SET FILENAME=%%~nv

    echo.
    echo !FILEPATH!.bin

    echo.     Generating PLD [pa.exe]: !FILENAME!.pa.pld
    %PA% "!FILEPATH!.bin" -signal "i1,i2,i3,i4,i5,i6,i7,i8,i9,i11,o12,o13,o14,o15,o16,o17,o18,o19" -alloe > "!FILEPATH!.pa.pld"

)
@echo off
setlocal EnableDelayedExpansion

set folder=%~1

for /r "%folder%" %%v in (*.bin) do (

    SET FILEPATH=%%~dv%%~pv%%~nv
    SET FILENAME=%%~nv

    echo.
    echo !FILEPATH!.bin

    echo.     Generating PLD [repal]: !FILENAME!.repal.pld
    echo.

    @REM py repal.py --truthtable "!FILEPATH!.bin"
    py repal.py --polarity="both" --oepolarity="both" --truthtable "!FILEPATH!.bin"
    @REM py repal.py --polarity="negative" --oepolarity="negative" --truthtable "!FILEPATH!.bin"
    @REM py repal.py --polarity="positive" --oepolarity="positive" --truthtable "!FILEPATH!.bin"
    @REM py repal.py --polarity="negative" --oepolarity="positive" --truthtable "!FILEPATH!.bin"
    @REM py repal.py --truthtable --profiles="E:\Repositories\repal\profiles-alt.json" "!FILEPATH!.bin"
)
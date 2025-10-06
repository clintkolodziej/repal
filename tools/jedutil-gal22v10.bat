@echo off
setlocal EnableDelayedExpansion

set folder=%~1
set toolspath=%~dp0\..\tools
SET JEDUTIL="%toolspath%\jedutil\jedutil.exe"

SET DEVICETYPE=gal22v10
SET PALTYPE=pal22v10

for /r "%folder%" %%v in (*.jed) do (

    SET FILEPATH=%%~dv%%~pv%%~nv
    SET FILENAME=%%~nv

    echo.
    echo !FILEPATH!.jed

    echo.     Extracting Jed Equations [jedutil]: !FILENAME!.jedutil.txt
    %JEDUTIL% -view "!FILEPATH!.jed" !DEVICETYPE! > "!FILEPATH!.jedutil.txt" 

)
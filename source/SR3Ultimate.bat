@echo off
title SR3Ultimate
rem Extra tracks (and more) for SEGA Rally 3: see extras.ps1
if not exist "%~dp0extras.ps1" goto notextracted
if not exist "%~dp0setup.ps1" goto notextracted
powershell -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0extras.ps1" %*
exit /b

:notextracted
echo.
echo   SR3Ultimate can't find its other files (extras.ps1, setup.ps1) next to SR3Ultimate.bat.
echo   If you opened the zip and double-clicked it there: extract the zip first
echo   (right-click, "Extract All..."), then run SR3Ultimate.bat from the SR3CamLab folder.
echo.
pause

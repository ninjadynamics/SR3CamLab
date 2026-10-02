@echo off
title SEGA Rally 3 - SR3CamLab camera
rem Optional: a profile name from profiles.yaml, e.g.  PLAY.bat Drone
if not exist "%~dp0patch.ps1" goto notextracted
if not exist "%~dp0setup.ps1" goto notextracted
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0patch.ps1" %*
pause
exit /b

:notextracted
echo.
echo   SR3CamLab can't find its other files (patch.ps1, setup.ps1) next to PLAY.bat.
echo.
echo   If you opened the zip and double-clicked PLAY.bat inside it, Windows ran it on its own.
echo   Close this window, right-click the zip, choose "Extract All...", put the SR3CamLab
echo   folder in your TeknoParrot folder, and run PLAY.bat from there.
echo.
pause

@echo off
title SR3Lab - track import
rem Other games' courses into SEGA Rally 3, from your own ROM sets: see tools\import\README.md
if not exist "%~dp0tools\import\stack_window.ps1" goto notextracted
start "" powershell -NoProfile -STA -ExecutionPolicy Bypass -WindowStyle Hidden -File "%~dp0tools\import\stack_window.ps1"
exit /b

:notextracted
echo.
echo   The import window's files (tools\import\) are not next to IMPORT.bat.
echo   If you opened the zip and double-clicked it there: extract the zip first
echo   (right-click, "Extract All..."), then run IMPORT.bat from the extracted folder.
echo.
pause

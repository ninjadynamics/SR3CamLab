@echo off
title SEGA Rally 3 - SR3CamLab camera
rem Optional: a profile name from profiles.yaml, e.g.  PLAY.bat Drone
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0patch.ps1" %*
pause

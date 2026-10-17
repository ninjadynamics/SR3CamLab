@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0..\..\source\tools\workspace\camlab_play.ps1" %*
if errorlevel 1 pause

@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0source\tools\workspace\play.ps1" -Workspace "%~dp0." %*
if errorlevel 1 pause

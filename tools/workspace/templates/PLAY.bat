@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0repo\tools\workspace\play.ps1" -Workspace "%~dp0." %*
if errorlevel 1 pause

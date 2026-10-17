@echo off
 powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0source\tools\workspace\setup.ps1" %*
if errorlevel 1 (pause & exit /b 1)

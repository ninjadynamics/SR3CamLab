@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_textures.ps1" %*
if errorlevel 1 pause

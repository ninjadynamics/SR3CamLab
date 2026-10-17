@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0repo\tools\workspace\update_textures.ps1" -Workspace "%~dp0." %*
pause

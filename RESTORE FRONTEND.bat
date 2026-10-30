@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scratchpad\frontend-20261028\rollback.ps1"
if errorlevel 1 pause

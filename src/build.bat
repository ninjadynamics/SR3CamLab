@echo off
rem Builds ..\camlab.exe (static, no console) with the w64devkit that ships with raylib 5.5.
rem The icon comes from ..\res\icon.png if present (else camlab.c draws one):
rem build, write camlab.ico with the new exe, embed it, link again.
rem Set RAYLIB_DIR first if raylib is not in C:\raylib.
setlocal
cd /d "%~dp0"
if not defined RAYLIB_DIR set RAYLIB_DIR=C:\raylib
set PATH=%RAYLIB_DIR%\w64devkit\bin;%PATH%
set OUT=..\camlab.exe
set FLAGS=-O2 -std=c99 -Wall -Wextra -Wpedantic -Wshadow -s -static -mwindows -lraylib -lopengl32 -lgdi32 -lwinmm
gcc camlab.c -o %OUT% %FLAGS% || goto fail
if exist ..\res\icon.png (%OUT% --write-icon camlab.ico ..\res\icon.png || goto fail) else (%OUT% --write-icon camlab.ico || goto fail)
echo GLFW_ICON ICON "camlab.ico"> camlab.rc
windres camlab.rc -O coff -o camlab_res.o || goto fail
gcc camlab.c camlab_res.o -o %OUT% %FLAGS% || goto fail
del camlab.ico camlab.rc camlab_res.o
echo Built camlab.exe
exit /b 0
:fail
echo Build failed
pause
exit /b 1

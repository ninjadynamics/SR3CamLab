# The launcher script is patches.ps1 now (2026-10-15). This file stays for CamLab, which looks for patch.ps1 next to
# camlab.exe, and for old shortcuts: it runs patches.ps1 with the same arguments (dot-sourced, so the scope is the same).
. (Join-Path $PSScriptRoot 'patches.ps1') @args

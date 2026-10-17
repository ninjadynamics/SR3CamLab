# The launcher script is sr3mods.ps1 now (patches.ps1 until the unified names of 2026-10-15, patch.ps1 before that). This file stays for CamLab, which looks for patch.ps1 next to
# camlab.exe, and for old shortcuts: it runs sr3mods.ps1 with the same arguments (dot-sourced, so the scope is the same).
. (Join-Path $PSScriptRoot 'sr3mods.ps1') @args

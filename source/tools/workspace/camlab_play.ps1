param([Parameter(Position=0)][string]$CameraProfile='', [string]$ProfilesFile='')
$ErrorActionPreference='Stop'
& (Join-Path $PSScriptRoot 'play.ps1') -CameraProfile $CameraProfile -ProfilesFile $ProfilesFile

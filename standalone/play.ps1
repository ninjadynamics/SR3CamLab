<# Optional launcher for the independent overlay and the existing SR3Lab mods.
   .\play.ps1 -GameFolder 'F:\Games\SR3Standalone' [-WithMods] [-CameraProfile Drone]
   The DLL also works by running Rally.exe directly with its folder as the working directory.
#>
param([Parameter(Mandatory=$true)][string]$GameFolder,
      [switch]$WithMods, [string]$CameraProfile = '')
$ErrorActionPreference = 'Stop'
$folder = (Resolve-Path -LiteralPath $GameFolder).Path
$exe = Join-Path $folder 'Rally.exe'
$manifestPath = Join-Path $folder 'sr3lab-overlay.json'
if (-not (Test-Path -LiteralPath $manifestPath)) { throw 'Select an overlay made by standalone/overlay.py.' }
$manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
if (-not $manifest.complete) { throw 'Overlay setup did not finish.' }
if ((Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash -ne $manifest.exe_sha256) {
    throw 'Rally.exe does not match the supported executable. Nothing launched.'
}
if (Get-Process -Name Rally -ErrorAction SilentlyContinue) {
    throw 'Close the running Rally.exe first so the mods cannot attach to the wrong game.'
}
if ($WithMods -and $manifest.mode -ne 'copy') {
    throw 'Materialize linked assets with overlay.py --materialize before using the mod tools.'
}
$patch = Join-Path (Split-Path -Parent $PSScriptRoot) 'patch.ps1'
if ($WithMods -and -not (Test-Path -LiteralPath $patch)) { throw 'patch.ps1 was not found beside the standalone component.' }
$gameProcess = Start-Process -FilePath $exe -WorkingDirectory $folder -PassThru
if ($WithMods) {
    # Dot-source so the patcher's existing script-scoped game path is available on its NoLaunch path.
    # Its ordinary TeknoParrot launch path and CamLab remain unchanged.
    $script:GameExePath = $exe
    . $patch -NoLaunch -DelaySeconds 0 -CameraProfile $CameraProfile
} else {
    Write-Host "SR3Lab running (PID $($gameProcess.Id)). Log: $(Join-Path $folder 'sr3lab.log')"
}

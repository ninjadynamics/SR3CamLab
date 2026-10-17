<# Optional launcher for the independent overlay and the existing SR3Lab mods.
   .\play.ps1 -GameFolder 'F:\Games\SR3Standalone' [-WithMods] [-CameraProfile Drone]
   The DLL also works by running Rally.exe directly with its folder as the working directory.
#>
param([Parameter(Mandatory=$true)][string]$GameFolder,
      [switch]$WithMods, [string]$CameraProfile = '', [string]$SettingsPath = '', [switch]$NoWatchdog, [switch]$Watchdog)
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
if ($Watchdog -and $NoWatchdog) { throw 'Choose -Watchdog or -NoWatchdog, not both.' }
$modRoot = Split-Path -Parent $PSScriptRoot
$patch = Join-Path $modRoot 'tools/sr3mods/build/sr3mods.exe'
if ($WithMods -and (Test-Path -LiteralPath (Join-Path $folder 'sr3mods.dll'))) {
    throw 'Adjacent sr3mods.dll is present: use launch.exe/settings.yaml for DLL mods. Do not attach the external patcher to the same process.'
}
if ($WithMods -and -not (Test-Path -LiteralPath $patch)) { throw 'Build tools/sr3mods/build.py first: sr3mods.exe is missing.' }
if (-not $SettingsPath) { $SettingsPath = Join-Path $folder 'settings.yaml' }
$SettingsPath = (Resolve-Path -LiteralPath $SettingsPath).Path
$previousSettings = $env:SR3LAB_SETTINGS
$previousWatch = $env:SR3LAB_WATCHDOG
$gameProcess = $null
try {
    $env:SR3LAB_SETTINGS = $SettingsPath
    if ($NoWatchdog) { $env:SR3LAB_WATCHDOG = '0' }
    elseif ($Watchdog) { $env:SR3LAB_WATCHDOG = '1' }
    if ($Watchdog) {
        $crash = Join-Path $modRoot 'crash'
        [void][IO.Directory]::CreateDirectory($crash)
        $record = Join-Path $crash ('launch-' + [Guid]::NewGuid().ToString('N'))
        $shell = Join-Path $PSScriptRoot 'watchdog.exe'
        if (-not (Test-Path -LiteralPath $shell)) { throw 'Build standalone/build.py first: watchdog.exe is missing.' }
        $arguments = @('--script',('"'+(Join-Path $PSScriptRoot 'watchdog.ps1')+'"'),
            '-LaunchExe',('"'+$exe+'"'),'-SettingsPath',('"'+$SettingsPath+'"'),'-CrashDirectory',('"'+$crash+'"'),'-ReadyFile',('"'+$record+'.json"'))
        $hostProcess = Start-Process -FilePath $shell -ArgumentList $arguments -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput ($record+'.log') -RedirectStandardError ($record+'.err')
        $null = $hostProcess.Handle
        try {
            while (-not (Test-Path -LiteralPath ($record+'.json'))) {
                if ($hostProcess.HasExited) { throw "Watchdog launch failed; inspect $record.err" }
                Start-Sleep -Milliseconds 100
            }
            $identity = Get-Content -LiteralPath ($record+'.json') -Raw | ConvertFrom-Json
            $gameProcess = Get-Process -Id $identity.pid -ErrorAction Stop
            $null = $gameProcess.Handle
            if ($gameProcess.StartTime.ToUniversalTime().ToFileTimeUtc() -ne $identity.created) { throw 'Watched game identity changed.' }
        } finally { $hostProcess.Dispose() }
    } else {
        $gameProcess = Start-Process -FilePath $exe -WorkingDirectory $folder -PassThru
        $null = $gameProcess.Handle
    }
} finally { $env:SR3LAB_SETTINGS = $previousSettings; $env:SR3LAB_WATCHDOG = $previousWatch }
try {
    if ($WithMods) {
        $arguments = @('attach',[string]$gameProcess.Id,'--settings',$SettingsPath,'--mod',$modRoot,'--delay','0')
        if ($CameraProfile) { $arguments += @('--camera-profile',$CameraProfile) }
        if ($NoWatchdog) { $arguments += '--no-watchdog' }
        if ($Watchdog) { $arguments += '--watchdog' }
        & $patch @arguments
        if ($LASTEXITCODE -ne 0) { throw "sr3mods failed (exit $LASTEXITCODE); inspect its output." }
    } else {
        Write-Host "SR3Lab running (PID $($gameProcess.Id)). Log: $(Join-Path $folder 'sr3lab.log')"
    }
} finally { if ($gameProcess) { $gameProcess.Dispose() } }

# Launch the accepted standalone setup from a local workspace; no desktop automation.
param([string]$Workspace = '', [switch]$Check, [string]$CameraProfile = '', [string]$ProfilesFile = '')
$ErrorActionPreference='Stop'
$playStartedUtc=[DateTime]::UtcNow.ToString('o')
$playClock=[Diagnostics.Stopwatch]::StartNew()
$playPhases=@{}
$verifiedFiles=@{}
if (-not $Workspace) { $Workspace=Split-Path (Split-Path (Split-Path $PSScriptRoot)) }
$Workspace=(Resolve-Path -LiteralPath $Workspace).ProviderPath
function Local-Path([string]$relative) {
 $p=[IO.Path]::GetFullPath((Join-Path $Workspace $relative))
 if (-not $p.StartsWith($Workspace.TrimEnd('\')+'\',[StringComparison]::OrdinalIgnoreCase)) { throw 'Workspace path escapes its root.' }
 return $p
}
$cfg=Get-Content -LiteralPath (Local-Path 'config/workspace.json') -Raw | ConvertFrom-Json
$game=Local-Path $cfg.game
$yaml=Local-Path $cfg.settings
$candidate=if ($cfg.candidate) { Local-Path $cfg.candidate } else { $null }
if (Test-Path -LiteralPath (Local-Path 'config/pom-apply-pending.json')) { throw 'Relief Apply was interrupted. Restore its recorded backup before playing.' }
$baseline=Get-Content -LiteralPath (Local-Path $cfg.baseline) -Raw | ConvertFrom-Json
$python=[string]$cfg.python
$launcher=Local-Path 'apps/runtime/launch.exe'
$hostScript=Join-Path $PSScriptRoot '..\handling\candidate_host.py'
$recorderScript=Join-Path $PSScriptRoot '..\handling\record_steering.py'
$broker=Join-Path $PSScriptRoot 'launch_session.py'
foreach ($p in (@($python,$launcher,$yaml,$hostScript,$recorderScript,$broker)+@($candidate | Where-Object { $_ }))) {
 if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Required file missing: $p" }
}
if ($candidate -and (Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash -ne $baseline.candidate_sha256) { throw 'Accepted handling candidate changed.' }
foreach ($p in $baseline.files.PSObject.Properties) {
 $file=Local-Path (([string]$cfg.game)+'/'+$p.Name)
 $actual=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
 if ($actual -ne $p.Value) { throw "Accepted game file changed: $($p.Name)" }
 $verifiedFiles[$p.Name]=$actual
}
$playPhases.accepted_hashes=$playClock.Elapsed.TotalMilliseconds
$content=Get-Content -LiteralPath $yaml -Raw
if ($content -notmatch '(?m)^\s+game_path:\s*[''"]?([^''"\r\n]+)[''"]?\s*$') { throw 'Missing launch.game_path.' }
if ((Local-Path $Matches[1].Trim()) -ne (Join-Path $game 'Rally.exe')) { throw 'Settings point to a different game than the accepted manifest.' }
if ($content -notmatch '(?m)^\s+mod_folder:\s*[''"]?([^''"\r\n]+)[''"]?\s*$') { throw 'Missing patches.mod_folder.' }
$mod=$Matches[1].Trim()
# The installed patch DLL uses this path from the game working directory.
if (-not [IO.Path]::IsPathRooted($mod) -or [IO.Path]::GetFullPath($mod) -ne (Local-Path 'config')) { throw 'Set patches.mod_folder to the absolute workspace config path.' }
foreach ($name in @('handling.json')) {
 if (-not (Test-Path -LiteralPath (Join-Path $mod $name) -PathType Leaf)) { throw "Mod configuration missing: $name" }
}
if ($content -notmatch '(?m)^\s+watchdog:\s*off\s*$') { throw 'Keep watchdog OFF for the accepted setup.' }
$shots=Local-Path $cfg.screenshots
if ($shots -ne (Join-Path $Workspace 'screenshots')) { throw 'Screenshot folder must match the native mod-folder-parent convention.' }
if ($ProfilesFile -and -not (Test-Path -LiteralPath $ProfilesFile -PathType Leaf)) { throw 'CamLab profile snapshot is missing.' }
if (-not (Test-Path -LiteralPath (Join-Path $Workspace 'apps/camlab/profiles.yaml'))) { throw 'Camera profiles missing; run SETUP.bat.' }
$playPhases.local_preflight=$playClock.Elapsed.TotalMilliseconds
function Invoke-LaunchSession([switch]$CheckOnly, [string]$RunPath='') {
 $sessionArgs=@('--workspace',$Workspace,'--settings',$yaml)
 if ($CheckOnly) { $sessionArgs+='--check' } else { $sessionArgs+=@('--run',$RunPath) }
 # Reuse actual hashes computed above in this launch. Nothing is cached by mtime.
 $payload=@{ verified_files=$verifiedFiles; started_utc=$playStartedUtc; elapsed_ms=$playClock.Elapsed.TotalMilliseconds; phases_ms=$playPhases } | ConvertTo-Json -Depth 5 -Compress
 $payload | & $python -X utf8 -B $broker @sessionArgs
 if ($LASTEXITCODE -ne 0) { throw 'PLAY validation/launch failed; see the error above.' }
}
if ($Check) {
 Invoke-LaunchSession -CheckOnly
 Write-Output 'PASS: accepted files, handling, settings, helper paths and local screenshots. No game launched.'
 return
}
if (Get-Process Rally,emulator,emulator_multicpu -ErrorAction SilentlyContinue) { throw 'Close Rally and Model 2 first (one game at a time).' }
$run=Join-Path (Local-Path $cfg.runs) ((Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,6))
New-Item -ItemType Directory -Path $run -Force | Out-Null
# CamLab passes unsaved profiles; isolate them to this run and preserve saved settings.
if ($CameraProfile -or $ProfilesFile) {
 $runSettings=$content
 $absoluteGame=(Join-Path $game 'Rally.exe').Replace("'","''")
 $runSettings=[regex]::Replace($runSettings,'(?m)^\s+game_path:.*$',"  game_path: '$absoluteGame'")
 if ($ProfilesFile) {
  $snapshot=Join-Path $run 'camera-profiles.yaml'
  Copy-Item -LiteralPath $ProfilesFile -Destination $snapshot
  $quoted=$snapshot.Replace("'","''")
  $runSettings=[regex]::Replace($runSettings,'(?m)^\s+profiles_file:.*$',"  profiles_file: '$quoted'")
 }
 if ($CameraProfile) {
  $quoted=$CameraProfile.Replace("'","''")
  if ($runSettings -match '(?m)^\s+camera_profile:') { $runSettings=[regex]::Replace($runSettings,'(?m)^\s+camera_profile:.*$',"  camera_profile: '$quoted'") }
  else { $runSettings=[regex]::Replace($runSettings,'(?m)^patches:\s*$',"patches:`n  camera_profile: '$quoted'") }
 }
 $yaml=Join-Path $run 'settings.yaml'
 [IO.File]::WriteAllText($yaml,$runSettings,[Text.UTF8Encoding]::new($false))
}
# One short-lived broker validates relief and starts both hidden helpers without
# serial PowerShell Start-Process bookkeeping. It waits for launch.exe only;
# Rally and its helpers continue normally, with their existing logs and settings.
Invoke-LaunchSession -RunPath $run

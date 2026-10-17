# Launch the accepted standalone setup from a local workspace; no desktop automation.
param([string]$Workspace = '', [switch]$Check)
$ErrorActionPreference='Stop'
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
$candidate=Local-Path $cfg.candidate
$baseline=Get-Content -LiteralPath (Local-Path $cfg.baseline) -Raw | ConvertFrom-Json
$python=[string]$cfg.python
$launcher=Local-Path 'launch.exe'
$hostScript=Join-Path $PSScriptRoot '..\handling\candidate_host.py'
$recorderScript=Join-Path $PSScriptRoot '..\handling\record_steering.py'
foreach ($p in @($python,$launcher,$yaml,$candidate,$hostScript,$recorderScript)) {
 if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { throw "Required file missing: $p" }
}
if ((Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash -ne $baseline.candidate_sha256) { throw 'Accepted handling candidate changed.' }
foreach ($p in $baseline.files.PSObject.Properties) {
 $file=Local-Path (([string]$cfg.game)+'/'+$p.Name)
 if ((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $p.Value) { throw "Accepted game file changed: $($p.Name)" }
}
$content=Get-Content -LiteralPath $yaml -Raw
if ($content -notmatch '(?m)^\s+game_path:\s*[''"]?([^''"\r\n]+)[''"]?\s*$') { throw 'Missing launch.game_path.' }
if ((Local-Path $Matches[1].Trim()) -ne (Join-Path $game 'Rally.exe')) { throw 'Settings point to a different game than the accepted manifest.' }
if ($content -notmatch '(?m)^\s+mod_folder:\s*[''"]?([^''"\r\n]+)[''"]?\s*$') { throw 'Missing patches.mod_folder.' }
$mod=$Matches[1].Trim()
# The installed patch DLL uses this path from the game working directory.
if (-not [IO.Path]::IsPathRooted($mod) -or [IO.Path]::GetFullPath($mod) -ne (Local-Path 'repo')) { throw 'Set patches.mod_folder to the absolute workspace repo path.' }
foreach ($name in @('profiles.yaml','handling.json')) {
 if (-not (Test-Path -LiteralPath (Join-Path $mod $name) -PathType Leaf)) { throw "Mod configuration missing: $name" }
}
if ($content -notmatch '(?m)^\s+watchdog:\s*off\s*$') { throw 'Keep watchdog OFF for the accepted setup.' }
$shots=Local-Path $cfg.screenshots
if ($shots -ne (Join-Path $Workspace 'screenshots')) { throw 'Screenshot folder must match the native mod-folder-parent convention.' }
if ($Check) { Write-Output 'PASS: accepted files, handling, settings, helper paths and local screenshots. No game launched.'; return }
if (Get-Process Rally,emulator,emulator_multicpu -ErrorAction SilentlyContinue) { throw 'Close Rally and Model 2 first (one game at a time).' }
$run=Join-Path (Local-Path $cfg.runs) ((Get-Date -Format 'yyyyMMdd-HHmmss')+'-'+[guid]::NewGuid().ToString('N').Substring(0,6))
New-Item -ItemType Directory -Path $run -Force | Out-Null
$helpers=@()
try {
 $argsHost=@(('"'+$hostScript+'"'),'--candidate',('"'+$candidate+'"'),'--game',('"'+$game+'"'),'--out',('"'+(Join-Path $run 'candidate.csv')+'"'))
 $helpers+=Start-Process -FilePath $python -ArgumentList $argsHost -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $run 'candidate.log') -RedirectStandardError (Join-Path $run 'candidate.err')
 $argsRecorder=@(('"'+$recorderScript+'"'),'--out',('"'+(Join-Path $run 'steering.csv')+'"'),'--seconds','180')
 $helpers+=Start-Process -FilePath $python -ArgumentList $argsRecorder -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $run 'recorder.log') -RedirectStandardError (Join-Path $run 'recorder.err')
 # GUI executables do not reliably set LASTEXITCODE when invoked with &.
 $launchProcess=Start-Process -FilePath $launcher -ArgumentList @('--settings',('"'+$yaml+'"'),'--no-watchdog') -WorkingDirectory $Workspace -WindowStyle Hidden -PassThru
 try {
  $launchProcess.WaitForExit()
  if ($launchProcess.ExitCode -ne 0) { throw "Game launcher failed ($($launchProcess.ExitCode))." }
 } finally { $launchProcess.Dispose() }
 Write-Output "Ultimate Race Lab launched. Select profile 2 for accepted SRC handling. Records: $run"
} catch {
 foreach ($helper in $helpers) { if (-not $helper.HasExited) { Stop-Process -Id $helper.Id -ErrorAction SilentlyContinue } }
 throw
} finally { foreach ($helper in $helpers) { $helper.Dispose() } }

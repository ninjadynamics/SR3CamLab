<# The external front receives exactly the owned PID and settings, including
   profile/watchdog overrides. A native stub records arguments without attaching. #>
param([Parameter(Mandatory=$true)][string]$StubExe)
$ErrorActionPreference='Stop'
$fixture=Join-Path $env:TEMP ('sr3-play-test-'+[Guid]::NewGuid().ToString('N'))
$null=New-Item -ItemType Directory -Path (Join-Path $fixture 'standalone'),(Join-Path $fixture 'game'),(Join-Path $fixture 'tools/sr3mods/build')
Copy-Item (Join-Path $PSScriptRoot 'play.ps1') (Join-Path $fixture 'standalone/play.ps1')
Copy-Item -LiteralPath $StubExe -Destination (Join-Path $fixture 'tools/sr3mods/build/sr3mods.exe')
$game=Join-Path $fixture 'game/Rally.exe'
[IO.File]::WriteAllText($game,'synthetic, never executed')
@{complete=$true;mode='copy';exe_sha256=(Get-FileHash $game -Algorithm SHA256).Hash} | ConvertTo-Json | Set-Content (Join-Path $fixture 'game/sr3lab-overlay.json')
[IO.File]::WriteAllText((Join-Path $fixture 'game/settings.yaml'),"version: 1`n")
function Get-Process {param($Name) return $null}
function Start-Process {param($FilePath,$WorkingDirectory,[switch]$PassThru)
    $global:sr3PlayStarted++
    $p=[pscustomobject]@{Id=123;Handle=0}
    $p | Add-Member -MemberType ScriptMethod -Name Dispose -Value {$global:sr3PlayDisposed++}
    return $p
}
$oldSettings=$env:SR3LAB_SETTINGS
$oldLog=$env:SR3_PLAY_TEST_LOG
$oldExit=$env:SR3_PLAY_TEST_EXIT
try {
 $env:SR3_PLAY_TEST_LOG=Join-Path $fixture 'arguments.txt'
 foreach($noWatchdog in @($false,$true)) {
    $global:sr3PlayStarted=0;$global:sr3PlayDisposed=0;$env:SR3_PLAY_TEST_EXIT='0'
    & (Join-Path $fixture 'standalone/play.ps1') -GameFolder (Join-Path $fixture 'game') -WithMods -CameraProfile 'Chase Far' -NoWatchdog:$noWatchdog
    $actual=@(Get-Content $env:SR3_PLAY_TEST_LOG)
    $expected=@('attach','123','--settings',(Join-Path $fixture 'game/settings.yaml'),'--mod',$fixture,'--delay','0','--camera-profile','Chase Far')
    if($noWatchdog){$expected+='--no-watchdog'}
    if(($actual -join '|') -ne ($expected -join '|')){throw ('Wrong arguments: '+($actual -join '|'))}
    if($global:sr3PlayStarted -ne 1 -or $global:sr3PlayDisposed -ne 1){throw 'Wrong owned process lifecycle'}
    if($env:SR3LAB_SETTINGS -ne $oldSettings){throw 'Settings environment leaked'}
 }
 $env:SR3_PLAY_TEST_EXIT='2';$global:sr3PlayDisposed=0;$caught=$false
 try { & (Join-Path $fixture 'standalone/play.ps1') -GameFolder (Join-Path $fixture 'game') -WithMods }
 catch {if($_.Exception.Message -notmatch 'sr3mods failed \(exit 2\)'){throw};$caught=$true}
 if(-not $caught -or $global:sr3PlayDisposed -ne 1){throw 'Front failure not propagated/handle leaked'}
 [IO.File]::WriteAllText((Join-Path $fixture 'game/sr3mods.dll'),'synthetic')
 $global:sr3PlayStarted=0;$caught=$false
 try { & (Join-Path $fixture 'standalone/play.ps1') -GameFolder (Join-Path $fixture 'game') -WithMods }
 catch {if($_.Exception.Message -notmatch 'Adjacent sr3mods.dll'){throw};$caught=$true}
 if(-not $caught -or $global:sr3PlayStarted){throw 'Duplicate patcher not refused before launch'}
 Write-Output 'PASS: exact PID/settings/profile, watchdog override, synchronous front lifecycle, exit propagation, environment restoration, duplicate-patcher refusal.'
} finally {
 $env:SR3LAB_SETTINGS=$oldSettings;$env:SR3_PLAY_TEST_LOG=$oldLog;$env:SR3_PLAY_TEST_EXIT=$oldExit
 $resolved=(Resolve-Path -LiteralPath $fixture).Path
 $tempRoot=(Resolve-Path -LiteralPath $env:TEMP).Path.TrimEnd('\')+'\'
 if(-not $resolved.StartsWith($tempRoot,[StringComparison]::OrdinalIgnoreCase) -or (Split-Path -Leaf $resolved) -notlike 'sr3-play-test-*'){throw 'Unsafe test cleanup path'}
 Remove-Item -LiteralPath $resolved -Recurse -Force
 Remove-Variable sr3PlayStarted,sr3PlayDisposed -Scope Global -ErrorAction SilentlyContinue
}

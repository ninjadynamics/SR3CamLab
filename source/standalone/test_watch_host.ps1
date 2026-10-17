<# Integration checks of the proposed host against an owned stand-in (hidden
   window in the freeze case, no visible windows or GPU).
   Does not start or inspect Rally. Keeps its logs/dumps as test evidence.
#>
param([Parameter(Mandatory=$true)][string]$TargetExe,
      [Parameter(Mandatory=$true)][string]$WorkDirectory, [string]$HostExe = '')
$ErrorActionPreference = 'Stop'
$targetPath = (Resolve-Path -LiteralPath $TargetExe).Path
$work = [IO.Path]::GetFullPath($WorkDirectory)
if (Test-Path -LiteralPath $work) { throw 'Choose a fresh evidence directory.' }
New-Item -ItemType Directory -Path $work | Out-Null
$hostScript = Join-Path $PSScriptRoot 'watchdog.ps1'
$shellPath = if ($HostExe) { (Resolve-Path -LiteralPath $HostExe).Path } else { Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe' }
$owned = [Collections.Generic.List[Diagnostics.Process]]::new()
function Check([bool]$condition,[string]$description) {
    if (-not $condition) { throw "FAIL: $description" }
    Write-Output "PASS: $description"
}
function Wait-Until([scriptblock]$condition,[string]$description,[int]$seconds=15) {
    $deadline = [DateTime]::UtcNow.AddSeconds($seconds)
    while (-not (& $condition)) {
        if ([DateTime]::UtcNow -gt $deadline) { throw "Timeout: $description" }
        Start-Sleep -Milliseconds 50
    }
}
function New-Target([string]$name,[string]$mode='normal') {
    $directory = Join-Path $work $name
    New-Item -ItemType Directory -Path $directory | Out-Null
    $process = Start-Process -FilePath $targetPath -ArgumentList $mode -WorkingDirectory $directory -WindowStyle Hidden -PassThru
    $null = $process.Handle
    $owned.Add($process)
    return @{ Process=$process; Directory=$directory }
}
function New-Host($case,[string]$name,[long]$timeOffset=0) {
    $fileTime = $case.Process.StartTime.ToUniversalTime().ToFileTimeUtc() + $timeOffset
    $directory = Join-Path $case.Directory $name
    New-Item -ItemType Directory -Path $directory | Out-Null
    $arguments = if ($HostExe) { @('--script',('"' + $hostScript + '"')) } else { @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',('"' + $hostScript + '"')) }
    $arguments += @(
        '-ProcessId',$case.Process.Id,'-ExpectedExePath',('"' + $targetPath + '"'),
        '-ExpectedStartFileTime',$fileTime,'-CrashDirectory',('"' + (Join-Path $directory 'crash') + '"'))
    $process = Start-Process -FilePath $shellPath -ArgumentList $arguments -WorkingDirectory $directory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $directory 'stdout.log') -RedirectStandardError (Join-Path $directory 'stderr.log')
    $null = $process.Handle
    $owned.Add($process)
    return @{ Process=$process; Directory=$directory }
}
function Wait-Attached($case,$hostCase) {
    Wait-Until { (Test-Path -LiteralPath (Join-Path $case.Directory 'debug-seen.txt')) -and
        ((Get-Content -LiteralPath (Join-Path $hostCase.Directory 'stdout.log') -Raw) -match 'Watchdog host attached\.') } 'host attachment'
}
function Finish-Target($case) { [IO.File]::WriteAllText((Join-Path $case.Directory 'finish.txt'),'finish') }
try {
    $case = New-Target 'detach'
    $wrong = New-Host $case 'wrong-identity' 1
    Check ($wrong.Process.WaitForExit(15000)) 'identity refusal exits promptly'
    Check ($wrong.Process.ExitCode -ne 0 -and -not $case.Process.HasExited -and -not (Test-Path -LiteralPath (Join-Path $case.Directory 'debug-seen.txt'))) 'wrong creation time refuses attachment'
    $first = New-Host $case 'first'
    Wait-Attached $case $first
    Check (-not $case.Process.HasExited) 'external host attaches to the owned stand-in'
    $second = New-Host $case 'duplicate'
    Check ($second.Process.WaitForExit(15000)) 'duplicate host exits promptly'
    Check ($second.Process.ExitCode -ne 0 -and -not $first.Process.HasExited -and -not $case.Process.HasExited) 'duplicate ownership refuses without disturbing target or first host'
    $first.Process.Kill(); $first.Process.WaitForExit()
    Wait-Until { Test-Path -LiteralPath (Join-Path $case.Directory 'debug-gone.txt') } 'debugger detached after host termination'
    Check (-not $case.Process.HasExited) 'terminating the helper leaves the target alive'
    Finish-Target $case
    Check ($case.Process.WaitForExit(10000) -and $case.Process.ExitCode -eq 0) 'detached target exits normally'

    $case = New-Target 'normal'
    $hostCase = New-Host $case 'host'
    Wait-Attached $case $hostCase
    Finish-Target $case
    Check ($case.Process.WaitForExit(10000) -and $case.Process.ExitCode -eq 0) 'watched target exits normally'
    Check ($hostCase.Process.WaitForExit(15000) -and $hostCase.Process.ExitCode -eq 0) 'host finishes after target exit'

    $case = New-Target 'crash' 'crash'
    $hostCase = New-Host $case 'host'
    Wait-Attached $case $hostCase
    Finish-Target $case
    Check ($case.Process.WaitForExit(15000) -and $case.Process.ExitCode -ne 0) 'stand-in raises its deliberate unhandled exception'
    Check ($hostCase.Process.WaitForExit(15000) -and $hostCase.Process.ExitCode -eq 0) 'host drains the crash recorder and exits'
    $crashDir = Join-Path $hostCase.Directory 'crash'
    $record = Get-ChildItem -LiteralPath $crashDir -Filter 'watchdog_*.log' | Select-Object -First 1
    Check ($record -and ((Get-Content -LiteralPath $record.FullName -Raw) -match 'E0424242')) 'unchanged watchdog records the actual exception'
    $dumps = @(Get-ChildItem -LiteralPath $crashDir -Filter 'crash_*.dmp')
    Check ($dumps.Count -gt 0 -and $dumps[0].Length -gt 10000) 'unchanged watchdog writes a crash minidump'

    $case = New-Target 'freeze' 'freeze'
    $hostCase = New-Host $case 'host'
    Wait-Attached $case $hostCase
    $crashDir = Join-Path $hostCase.Directory 'crash'
    $record = Get-ChildItem -LiteralPath $crashDir -Filter 'watchdog_*.log' | Select-Object -First 1
    Wait-Until { (Get-Content -LiteralPath $record.FullName -Raw) -match 'watching window' } 'watchdog observes the stand-in window'
    Start-Sleep -Milliseconds 200
    [IO.File]::WriteAllText((Join-Path $case.Directory 'freeze.txt'),'freeze')
    Wait-Until { (Get-Content -LiteralPath $record.FullName -Raw) -match '==== end of the freeze record' } 'freeze samples and dump complete' 30
    $freezeLog = Get-Content -LiteralPath $record.FullName -Raw
    Check (([regex]::Matches($freezeLog,'-- sample [123] of 3')).Count -eq 3) 'unchanged watchdog takes all three freeze samples'
    $dumps = @(Get-ChildItem -LiteralPath $crashDir -Filter 'freeze_*.dmp')
    Check ($dumps.Count -gt 0 -and $dumps[0].Length -gt 10000) 'unchanged watchdog writes a freeze minidump'
    [IO.File]::WriteAllText((Join-Path $case.Directory 'resume.txt'),'resume')
    Wait-Until { (Get-Content -LiteralPath $record.FullName -Raw) -match 'answers again' } 'freeze recovery is observed'
    Finish-Target $case
    Check ($case.Process.WaitForExit(10000) -and $case.Process.ExitCode -eq 0) 'recovered stand-in exits normally'
    Check ($hostCase.Process.WaitForExit(15000) -and $hostCase.Process.ExitCode -eq 0) 'host finishes after the recovered target'
    Write-Output "Watchdog host lifecycle PASS; evidence: $work"
} finally {
    foreach ($process in $owned) {
        if (-not $process.HasExited) { $process.Kill(); $process.WaitForExit() }
        $process.Dispose()
    }
}

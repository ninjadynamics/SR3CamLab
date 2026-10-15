<# External host for the unchanged recorder. Attach to an exact process identity,
   or create a suspended target and resume only after debugger attachment. #>
[CmdletBinding(DefaultParameterSetName='Attach')]
param(
    [Parameter(Mandatory=$true,ParameterSetName='Attach')][ValidateRange(1,2147483647)][int]$ProcessId,
    [Parameter(Mandatory=$true,ParameterSetName='Attach')][string]$ExpectedExePath,
    [Parameter(Mandatory=$true,ParameterSetName='Attach')][long]$ExpectedStartFileTime,
    [Parameter(Mandatory=$true,ParameterSetName='Launch')][string]$LaunchExe,
    [Parameter(ParameterSetName='Launch')][string]$SettingsPath,
    [Parameter(ParameterSetName='Launch')][string]$ReadyFile,
    [Parameter(Mandatory=$true)][string]$CrashDirectory
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
if (-not [Environment]::Is64BitProcess) { throw 'Use 64-bit Windows PowerShell for the watchdog host.' }
Add-Type -Path (Join-Path $PSScriptRoot 'watch_process.cs')
$launched = $null
function Get-ExpectedProcess {
    $target = Get-Process -Id $ProcessId -ErrorAction Stop
    # Retain a process handle throughout the session, including while compiling.
    # Windows cannot recycle this process object/PID while that handle is held.
    $null = $target.Handle
    if (-not [Sr3WatchProcess]::Matches($target.Handle, $expected, $ExpectedStartFileTime)) {
        $target.Dispose()
        throw 'Watchdog target identity changed; nothing attached.'
    }
    return $target
}
function Show-WatchdogMessages {
    for ($message = [Sr3Watchdog]::NextMessage(); $null -ne $message; $message = [Sr3Watchdog]::NextMessage()) {
        Write-Output "Watchdog: $message"
    }
}

$target = $null; $mutex = $null
$ownsMutex = $false; $started = $false
try {
    if ($PSCmdlet.ParameterSetName -eq 'Launch') {
        $LaunchExe = (Resolve-Path -LiteralPath $LaunchExe).Path
        if ($SettingsPath) { $env:SR3LAB_SETTINGS = (Resolve-Path -LiteralPath $SettingsPath).Path }
        $launched = [Sr3WatchProcess]::new($LaunchExe)
        $ProcessId = $launched.Id
        $ExpectedExePath = $LaunchExe
        $ExpectedStartFileTime = $launched.CreationTime
    }
    $expected = (Resolve-Path -LiteralPath $ExpectedExePath).Path
    $target = Get-ExpectedProcess
    $mutex = [Threading.Mutex]::new($false, "Local\SR3LabWatchdog-$ProcessId-$ExpectedStartFileTime")
    try { $ownsMutex = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $ownsMutex = $true }
    if (-not $ownsMutex) { throw 'A watchdog host already owns this process.' }
    $modRoot = Split-Path -Parent $PSScriptRoot
    $source = Join-Path $modRoot 'watchdog.cs'
    # Keep the same address list and timeout as the PS route. Parse constants;
    # never dot-source sr3mods.ps1, which would attach mods as a side effect.
    $tokens = $null; $errors = $null
    $ast = [System.Management.Automation.Language.Parser]::ParseFile((Join-Path $modRoot 'sr3mods.ps1'), [ref]$tokens, [ref]$errors)
    if ($errors.Count) { throw 'Cannot read watchdog settings from sr3mods.ps1: parser errors.' }
    $config = @{}
    foreach ($name in @('FreezeSeconds','GameWindowVA','WatchdogValues')) {
        $assignments = @($ast.FindAll({ param($node)
            $node -is [System.Management.Automation.Language.AssignmentStatementAst] -and
            $node.Left -is [System.Management.Automation.Language.VariableExpressionAst] -and
            $node.Left.VariablePath.UserPath -eq $name
        }, $false))
        if ($assignments.Count -ne 1 -or $assignments[0].Right -isnot [System.Management.Automation.Language.CommandExpressionAst]) {
            throw "Expected one literal watchdog setting: $name"
        }
        $config[$name] = $assignments[0].Right.Expression.SafeGetValue()
    }
    Add-Type -Path $source -ErrorAction Stop
    # Compilation can outlive a process. Recheck identity immediately before
    # attaching, so a reused PID cannot silently select another executable.
    $target.Dispose(); $target = Get-ExpectedProcess
    [Sr3Watchdog]::Values = [string]$config.WatchdogValues
    $started = [Sr3Watchdog]::Start($ProcessId, [IO.Path]::GetFullPath($CrashDirectory), [int]$config.FreezeSeconds, [long]$config.GameWindowVA)
    if (-not $started) { throw 'The recorder refused to start a new session.' }
    Write-Output "Watchdog source SHA256: $((Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash)"
    $reported = $false
    $attachDeadline = [DateTime]::UtcNow.AddSeconds(15)
    while (-not [Sr3Watchdog]::Finished) {
        Show-WatchdogMessages
        if (-not $reported -and [Sr3Watchdog]::Attached) {
            Write-Output 'Watchdog host attached.'; $reported = $true
            if ($launched) {
                if ($ReadyFile) {
                    # Publish identity before resume; the consumer can safely open
                    # this process even if it exits immediately on its first code.
                    $record = @{pid=$ProcessId; exe=$expected; created=$ExpectedStartFileTime} | ConvertTo-Json -Compress
                    [IO.File]::WriteAllText($ReadyFile + '.tmp', $record)
                    [IO.File]::Move($ReadyFile + '.tmp', $ReadyFile)
                }
                $launched.Resume(); Write-Output "Watchdog launched target PID $ProcessId."
            }
        }
        if ($launched -and -not $reported -and [DateTime]::UtcNow -gt $attachDeadline) {
            throw 'Watchdog attachment failed; the suspended target will be closed without running.'
        }
        [void][Sr3Watchdog]::WaitFinished(250)
    }
    Show-WatchdogMessages
    if (-not $reported) { throw 'The watchdog session ended without confirming debugger attachment; inspect its log.' }
} finally {
    if ($started) { [Sr3Watchdog]::Stop(5000); Show-WatchdogMessages }
    if ($ownsMutex) { $mutex.ReleaseMutex() }
    if ($mutex) { $mutex.Dispose() }
    if ($target) { $target.Dispose() }
    if ($launched) { $launched.Dispose() }
}

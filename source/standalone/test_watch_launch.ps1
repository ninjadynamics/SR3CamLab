<# Launch regression: a hidden x86 stand-in checks its actual Windows heap
   flags, debugger and Unicode environment, then exits or raises an exception.
   Does not start Rally or access the desktop. Requires installed .NET Framework.
#>
param([Parameter(Mandatory=$true)][string]$WorkDirectory)
$ErrorActionPreference='Stop'
$work=[IO.Path]::GetFullPath($WorkDirectory)
if(Test-Path -LiteralPath $work){throw 'Choose a fresh evidence directory.'}
New-Item -ItemType Directory -Path $work | Out-Null
$source=@'
using System;
using System.IO;
using System.Runtime.InteropServices;
class LaunchProbe {
    [StructLayout(LayoutKind.Sequential)] struct Basic { public IntPtr reserved,peb,r0,r1,pid,r2; }
    [DllImport("ntdll.dll")] static extern int NtQueryInformationProcess(IntPtr p,int c,out Basic b,int n,out int used);
    [DllImport("kernel32.dll")] static extern bool IsDebuggerPresent();
    [DllImport("kernel32.dll")] static extern uint SetErrorMode(uint mode);
    [DllImport("kernel32.dll")] static extern void RaiseException(uint c,uint flags,uint count,IntPtr args);
    static int Main() {
        SetErrorMode(3); // no OS error dialogs, including the deliberate crash
        Basic b; int used;
        if(IntPtr.Size!=4 || NtQueryInformationProcess(new IntPtr(-1),0,out b,Marshal.SizeOf(typeof(Basic)),out used)!=0) return 40;
        int heapFlags=Marshal.ReadInt32(b.peb,0x68)&0x70;
        bool debug=IsDebuggerPresent();
        string sentinel=Environment.GetEnvironmentVariable("SR3_WATCH_TEST_UNICODE");
        bool environment=sentinel=="\u00e9\u6c34 test" && Environment.GetEnvironmentVariable("_NO_DEBUG_HEAP")=="1";
        File.WriteAllText("probe.txt","heapFlags="+heapFlags+"\ndebugger="+debug+"\nenvironment="+environment+"\n");
        if(heapFlags!=0 || !environment || (!debug && Environment.GetEnvironmentVariable("SR3_WATCH_TEST_REQUIRE_DEBUGGER")=="1")) return 41;
        if(Environment.GetEnvironmentVariable("SR3_WATCH_TEST_CRASH")=="1") RaiseException(0xE0424242,1,0,IntPtr.Zero);
        return 0;
    }
}
'@
$sourcePath=Join-Path $work 'LaunchProbe.cs'
[IO.File]::WriteAllText($sourcePath,$source)
$exe=Join-Path $work 'LaunchProbe.exe'
& "$env:SystemRoot\Microsoft.NET\Framework64\v4.0.30319\csc.exe" /nologo /optimize+ /platform:x86 /target:winexe "/out:$exe" $sourcePath
if($LASTEXITCODE -ne 0){throw 'Probe build failed.'}
$names=@('_NO_DEBUG_HEAP','SR3_WATCH_TEST_UNICODE','SR3_WATCH_TEST_REQUIRE_DEBUGGER','SR3_WATCH_TEST_CRASH')
$saved=@{}
foreach($name in $names){$saved[$name]=[Environment]::GetEnvironmentVariable($name,'Process')}
function Check($ok,$message){if(-not $ok){throw "FAIL: $message"}; Write-Output "PASS: $message"}
try {
    $env:_NO_DEBUG_HEAP='0'
    $env:SR3_WATCH_TEST_UNICODE=([char]0xe9).ToString()+[char]0x6c34+' test'
    $env:SR3_WATCH_TEST_REQUIRE_DEBUGGER='0'; $env:SR3_WATCH_TEST_CRASH='0'
    Add-Type -Path (Join-Path $PSScriptRoot 'watch_process.cs')
    $refused=$false
    try {$invalid=[Sr3WatchProcess]::new((Join-Path $work 'missing.exe'));$invalid.Dispose()} catch {$refused=$true}
    Check ($refused -and $env:_NO_DEBUG_HEAP -eq '0') 'failed creation preserves the host environment'
    $child=[Sr3WatchProcess]::new($exe)
    $process=Get-Process -Id $child.Id; $null=$process.Handle
    try {
        Check ($env:_NO_DEBUG_HEAP -eq '0') 'launch preserves the host environment'
        $child.Resume()
        Check ($process.WaitForExit(15000) -and $process.ExitCode -eq 0) 'child gets the ordinary heap and inherited Unicode variables'
    } finally {if(-not $process.HasExited){$process.Kill()};$process.Dispose();$child.Dispose()}
    $env:SR3_WATCH_TEST_REQUIRE_DEBUGGER='1'
    foreach($mode in @('normal','crash')) {
        $directory=Join-Path $work $mode
        New-Item -ItemType Directory -Path $directory | Out-Null
        $target=Join-Path $directory 'LaunchProbe.exe'
        Copy-Item -LiteralPath $exe -Destination $target
        $env:SR3_WATCH_TEST_CRASH=if($mode -eq 'crash'){'1'}else{'0'}
        $arguments=@('-LaunchExe',('"'+$target+'"'),'-CrashDirectory',('"'+(Join-Path $directory 'records')+'"'))
        $hostProcess=Start-Process -FilePath (Join-Path $PSScriptRoot 'watchdog.exe') -ArgumentList $arguments -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $directory 'host.log') -RedirectStandardError (Join-Path $directory 'host.err')
        $null=$hostProcess.Handle
        try {
            Check ($hostProcess.WaitForExit(30000) -and $hostProcess.ExitCode -eq 0) "$mode host finishes"
            $result=Get-Content -LiteralPath (Join-Path $directory 'probe.txt') -Raw
            Check ($result -match 'heapFlags=0' -and $result -match 'debugger=True' -and $result -match 'environment=True') "$mode child: debugger attached, debug heap off, Unicode environment intact"
            $record=Get-ChildItem (Join-Path $directory 'records') -Filter 'watchdog_*.log' | Select-Object -First 1
            $log=Get-Content -LiteralPath $record.FullName -Raw
            if($mode -eq 'crash') {
                Check ($log -match 'CRASH:.*E0424242') 'early unhandled exception recorded'
                $dump=Get-ChildItem (Join-Path $directory 'records') -Filter 'crash_*.dmp' | Select-Object -First 1
                Check ($dump -and $dump.Length -gt 10000) 'early crash minidump written'
            } else {Check ($log -match 'exit code 0x00000000') 'normal child exit recorded'}
        } finally {if(-not $hostProcess.HasExited){$hostProcess.Kill();$hostProcess.WaitForExit()};$hostProcess.Dispose()}
    }
} finally {foreach($name in $names){[Environment]::SetEnvironmentVariable($name,$saved[$name],'Process')}}

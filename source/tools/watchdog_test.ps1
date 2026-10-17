# Runs ..\watchdog.cs (the launcher's crash and freeze watchdog) against two small 32-bit stand-in programs, never the game:
#   crash    a hidden window that answers, a handled access violation (handed back, the program goes on), debug output,
#            then an unhandled access violation in crash_here(): the record must name crash_here, the program must end
#            with its own exception code, a minidump must be written
#   freeze   a hidden window that answers for 2 s, then stuck_here() keeps the message loop from running for 8 s, then it
#            answers again and exits with 0: three samples with stuck_here on the window thread's stack, a minidump, the
#            "answers again" line
#   box      a box built like a MessageBox (off screen and fully transparent: nothing shows) while the window answers: the
#            box's title and text, three samples, a minidump, and no freeze record
#   detach   Stop() detaches: the program runs on, answers, and has no debugger any more
#   kill     the watchdog's own process is killed while attached: the program runs on (DebugSetProcessKillOnExit FALSE)
#   second   a second watchdog cannot attach while the first is: it says so and still records the freeze
# The stand-ins are built with Visual Studio's 32-bit C compiler (found with vswhere) into -Work. Counts on the last line.
param([string]$Work = (Join-Path $env:TEMP 'sr3watchdogtest'), [switch]$Keep)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force $Work | Out-Null
$cs = Join-Path $PSScriptRoot '..\watchdog.cs'
$common = @'
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static LRESULT CALLBACK proc(HWND h, UINT m, WPARAM w, LPARAM l) { return DefWindowProcA(h, m, w, l); }
static void window(void) {                                         /* never shown: nothing appears on screen */
    WNDCLASSA c = {0}; c.lpfnWndProc = proc; c.hInstance = GetModuleHandleA(0); c.lpszClassName = "sr3wd";
    RegisterClassA(&c); CreateWindowA("sr3wd", "watchdog stand-in", WS_OVERLAPPED, 0, 0, 100, 100, 0, 0, c.hInstance, 0);
}
static void pump(void) { MSG m; while (PeekMessageA(&m, 0, 0, 0, PM_REMOVE)) { TranslateMessage(&m); DispatchMessageA(&m); } }
static void say(const char *name, void *f) { char s[160]; sprintf(s, "stand-in: %s=%p module=%p\n", name, f, (void *)GetModuleHandleA(0)); OutputDebugStringA(s); }
'@
$crashC = $common + @'
__declspec(noinline) int handled(void) { __try { *(volatile int *)0x10 = 1; } __except (EXCEPTION_EXECUTE_HANDLER) { return 1; } return 0; }
__declspec(noinline) void crash_here(volatile int *p) { p[2] = 0x1234; }
int main(int argc, char **argv) {                                  /* crash after argv[1] seconds */
    DWORD ms = (argc > 1 ? atoi(argv[1]) : 4) * 1000, t0 = GetTickCount(); int n = 0, done = 0; char s[80];
    int hidden = argc > 2 && !strcmp(argv[2], "hidden");
    if (!hidden) SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);  /* no error-reporting window for this crash, ever */
    else {   /* hidden: Windows' error reporting must run (it writes the dump the watchdog reads), but without its window */
        typedef HRESULT (WINAPI *WerFlags)(DWORD); WerFlags w = (WerFlags)GetProcAddress(GetModuleHandleA("kernel32.dll"), "WerSetFlags");
        SetErrorMode(SEM_FAILCRITICALERRORS); if (w) w(0x20);      /* WER_FAULT_REPORTING_NO_UI */
    }
    if (hidden) {                                                  /* like the game's main thread: hidden from debuggers (ThreadHideFromDebugger) */
        typedef LONG (WINAPI *SetInfo)(HANDLE, ULONG, PVOID, ULONG);
        SetInfo f = (SetInfo)GetProcAddress(GetModuleHandleA("ntdll.dll"), "NtSetInformationThread"); if (f) f(GetCurrentThread(), 0x11, 0, 0);
    }
    window();
    for (;;) {
        DWORD t = GetTickCount() - t0; pump();
        if (n++ % 30 == 0) say("crash_here", (void *)crash_here);
        if (!done && t > 1500) { done = 1; sprintf(s, "stand-in: handled=%d, going on\n", handled()); OutputDebugStringA(s); }
        if (t > ms) { OutputDebugStringA("stand-in: crashing now\n"); crash_here(0); }
        Sleep(15);
    }
}
'@
$hangC = $common + @'
__declspec(noinline) void stuck_here(DWORD ms) { DWORD t0 = GetTickCount(); while (GetTickCount() - t0 < ms) Sleep(50); }
static DWORD WINAPI worker(LPVOID e) { WaitForSingleObject((HANDLE)e, INFINITE); return 0; }
static void fake_box(void) {   /* built like a MessageBox (class #32770, its text in control 0xFFFF), but off screen, fully transparent, never activated */
    HWND d = CreateWindowExA(WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_LAYERED | WS_EX_TRANSPARENT, "#32770", "SEGA Rally 3", WS_POPUP, -32000, -32000, 8, 8, 0, 0, GetModuleHandleA(0), 0);
    SetLayeredWindowAttributes(d, 0, 0, LWA_ALPHA);
    CreateWindowExA(0, "STATIC", "Out of memory for VB", WS_CHILD, 0, 0, 4, 4, d, (HMENU)(ULONG_PTR)0xFFFF, GetModuleHandleA(0), 0);
    ShowWindow(d, SW_SHOWNOACTIVATE);
}
int main(int argc, char **argv) {          /* answer argv[1] s, stuck argv[2] s, answer argv[3] s (with a box if argv[4] is "box"), exit 0 */
    DWORD a = (argc > 1 ? atoi(argv[1]) : 2) * 1000, st = (argc > 2 ? atoi(argv[2]) : 8) * 1000, b = (argc > 3 ? atoi(argv[3]) : 3) * 1000, t0;
    HANDLE e = CreateEventA(0, TRUE, FALSE, 0); int n = 0;
    CreateThread(0, 0, worker, e, 0, 0); window();
    for (t0 = GetTickCount(); GetTickCount() - t0 < a; Sleep(15)) { pump(); if (n++ % 30 == 0) say("stuck_here", (void *)stuck_here); }
    if (st) { OutputDebugStringA("stand-in: stuck now\n"); stuck_here(st); OutputDebugStringA("stand-in: going on\n"); }
    if (argc > 4 && !strcmp(argv[4], "box")) { fake_box(); OutputDebugStringA("stand-in: box up\n"); }
    for (t0 = GetTickCount(); GetTickCount() - t0 < b; Sleep(15)) pump();
    SetEvent(e); return 0;
}
'@
# ---- build ----
$crashExe = Join-Path $Work 'sr3wd_crash.exe'; $hangExe = Join-Path $Work 'sr3wd_hang.exe'
if (-not (Test-Path $crashExe) -or -not (Test-Path $hangExe) -or (Get-Item $crashExe).LastWriteTime -lt (Get-Item $PSCommandPath).LastWriteTime) {
    $vsw = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    $vs = if (Test-Path $vsw) { & $vsw -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath } else { $null }
    $vc = if ($vs) { Join-Path $vs 'VC\Auxiliary\Build\vcvars32.bat' } else { $null }
    if (-not $vc -or -not (Test-Path $vc)) { throw 'This test builds its stand-ins with Visual Studio''s C compiler (the Build Tools with "Desktop development with C++"); vcvars32.bat was not found.' }
    Set-Content (Join-Path $Work 'sr3wd_crash.c') $crashC -Encoding ASCII; Set-Content (Join-Path $Work 'sr3wd_hang.c') $hangC -Encoding ASCII
    $bat = Join-Path $Work 'build.bat'
    Set-Content $bat "@echo off`r`ncd /d `"$Work`"`r`n(call `"$vc`"`r`ncl /nologo /O1 /W3 /D_CRT_SECURE_NO_WARNINGS sr3wd_crash.c user32.lib`r`ncl /nologo /O1 /W3 /D_CRT_SECURE_NO_WARNINGS sr3wd_hang.c user32.lib) > build.log 2>&1`r`n" -Encoding ASCII
    cmd /c "`"$bat`""                                              # (its output, vcvars32's own complaints included, is in build.log)
    if (-not (Test-Path $crashExe) -or -not (Test-Path $hangExe)) { Get-Content (Join-Path $Work 'build.log'); throw 'The stand-ins did not build.' }
}
Add-Type -Path $cs
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class WdTest {
    [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(int a, bool i, int pid);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll")] static extern bool CheckRemoteDebuggerPresent(IntPtr h, out bool d);
    [DllImport("user32.dll")] static extern IntPtr FindWindowEx(IntPtr p, IntPtr after, string cls, string title);
    [DllImport("user32.dll")] static extern int GetWindowThreadProcessId(IntPtr w, out int pid);
    [DllImport("user32.dll")] static extern IntPtr SendMessageTimeout(IntPtr w, uint m, IntPtr wp, IntPtr lp, uint f, uint ms, out IntPtr r);
    public static bool Debugged(int pid) {                         // (needs PROCESS_QUERY_INFORMATION: it asks for the debug port)
        IntPtr h = OpenProcess(0x0400, false, pid); bool d = false;
        if (h == IntPtr.Zero || !CheckRemoteDebuggerPresent(h, out d)) throw new Exception("cannot ask process " + pid + " for a debugger");
        CloseHandle(h); return d;
    }
    public static bool Answers(int pid) {                          // the stand-in's hidden window answers a message within 1 s
        IntPtr w = IntPtr.Zero; int p;
        while ((w = FindWindowEx(IntPtr.Zero, w, "sr3wd", null)) != IntPtr.Zero) {
            GetWindowThreadProcessId(w, out p); IntPtr r;
            if (p == pid) return SendMessageTimeout(w, 0, IntPtr.Zero, IntPtr.Zero, 2, 1000, out r) != IntPtr.Zero;
        }
        return false;
    }
}
'@
$script:pass = 0; $script:fail = 0
function Check([string]$what, [bool]$ok, [string]$got = '') {
    if ($ok) { $script:pass++; $v = 'ok    ' } else { $script:fail++; $v = 'FAILED' }
    '  {0} {1}{2}' -f $v, $what, $(if ($got) { ": $got" } else { '' })
}
function News { $l = @(); for ($m = [Sr3Watchdog]::NextMessage(); $null -ne $m; $m = [Sr3Watchdog]::NextMessage()) { $l += $m }; return ,$l }
function Run([string]$exe, [string]$args2) { $p = Start-Process -FilePath $exe -ArgumentList $args2 -WorkingDirectory $Work -WindowStyle Hidden -PassThru; $null = $p.Handle; return $p }   # (the handle: so ExitCode is kept)
function Fn([string]$log, [string]$name) {   # the function's offset in the stand-in, from its own debug line
    $m = [regex]::Match($log, "stand-in: $name=([0-9A-Fa-f]+) module=([0-9A-Fa-f]+)"); if (-not $m.Success) { return -1 }
    return [Convert]::ToInt64($m.Groups[1].Value, 16) - [Convert]::ToInt64($m.Groups[2].Value, 16)
}
function InFn([string]$text, [string]$exe, [long]$off, [int]$size) {   # some "exe+0x..." in the text falls inside the function
    if ($off -lt 0) { return $false }
    foreach ($m in [regex]::Matches($text, [regex]::Escape($exe) + '\+0x([0-9A-F]+)')) { $o = [Convert]::ToInt64($m.Groups[1].Value, 16); if ($o -ge $off -and $o -lt $off + $size) { return $true } }
    return $false
}

"1. crash: a handled access violation, then an unhandled one"
$dir = Join-Path $Work 'crash_case'; Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
$p = Run $crashExe '4'
[void][Sr3Watchdog]::Start($p.Id, $dir, 3, 0)
[void]$p.WaitForExit(20000); [void][Sr3Watchdog]::WaitFinished(10000)
$log = Get-Content -Raw ([Sr3Watchdog]::LogPath); $news = News
$off = Fn $log 'crash_here'
Check 'attached' ($log -match '\d attached\r?\n')
Check 'the break-ins of the attach taken by the watchdog (a 64-bit one makes two), none handed to the program' ($log -match 'attach break-in taken' -and ([IntPtr]::Size -eq 4 -or $log -match '32-bit attach break-in taken') -and $log -notmatch 'first chance [^\n]*breakpoint')
Check 'the stand-in''s own window is the one watched' ($log -match 'watching window 0x[0-9A-F]+ "watchdog stand-in" \(class sr3wd, thread \d+, hidden\)') (([regex]::Match($log, 'watching window[^\r\n]*')).Value)
Check 'the handled access violation is logged as first chance and handed back: the program went on' ($log -match 'first chance \(the game may handle it\): access violation 0xC0000005 at [0-9A-F]{8} \(sr3wd_crash\.exe\+0x[0-9A-F]+\) \(writing 0x00000010\)' -and $log -match 'game says: stand-in: handled=1, going on' -and $log -match 'game says: stand-in: crashing now')
$cl = ($log -split "`n" | Where-Object { $_ -match '==== CRASH' }) -join ''
Check 'the crash record: second chance, writing address 8, inside crash_here()' ($cl -match 'access violation 0xC0000005 at .*\(writing 0x00000008\).*second chance' -and (InFn $cl 'sr3wd_crash.exe' $off 0x20)) $cl.Trim()
Check 'registers, code bytes, stack, calls on the stack, the other threads, the last debug lines' ($log -match '  thread \d+ \(from .*\): eip [0-9A-F]{8} \(sr3wd_crash\.exe\+' -and $log -match 'code at eip-16: [0-9a-f]{96}' -and $log -match '  stack: [0-9a-f]{8}' -and $log -match 'calls on the stack: [0-9A-F]{8} \(sr3wd_crash\.exe\+' -and $log -match '  other threads:' -and $log -match "last debug output lines:\r?\n.*stand-in")
$dump = Get-ChildItem $dir -Filter 'crash_*.dmp' | Select-Object -First 1
Check 'a minidump' ($null -ne $dump -and $dump.Length -gt 10000) $(if ($dump) { "$($dump.Name), $([int]($dump.Length / 1024)) KB" } else { 'none' })
Check 'the program ended with its own exception (0xC0000005), seen by the watchdog' ($p.ExitCode -eq -1073741819 -and $log -match 'the process ended, exit code 0xC0000005') ('exit code 0x{0:X8}' -f $p.ExitCode)
Check 'news for the launcher: the crash, with the log and the minidump' (@($news | Where-Object { $_ -match '^the game crashed: access violation .* Details: crash_case\\watchdog_.*\.log, minidump crash_case\\crash_.*\.dmp\.$' }).Count -eq 1) ($news -join ' | ')
Check 'after the crash, the dying program is not taken for a freeze' ($log -notmatch '==== FREEZE' -and @($news | Where-Object { $_ -match 'stopped responding' }).Count -eq 0)

"1b. crash on a thread hidden from debuggers (as the game's main thread is): the record comes from Windows' crash dump"
# Needs Windows' LocalDumps (HKLM\SOFTWARE\Microsoft\Windows\Windows Error Reporting\LocalDumps); without it this case reports so.
$dir = Join-Path $Work 'hidden_case'; Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
$p = Run $crashExe '5 hidden'; Start-Sleep -Milliseconds 800          # (the stand-in hides its thread first thing)
[void][Sr3Watchdog]::Start($p.Id, $dir, 3, 0)
[void]$p.WaitForExit(30000); [void][Sr3Watchdog]::WaitFinished(20000)
$log = Get-Content -Raw ([Sr3Watchdog]::LogPath); $news = News
Check 'the hidden thread is named when the watchdog attaches' ($log -match 'hidden from debuggers: thread \d+') (([regex]::Match($log, 'hidden from debuggers[^\r\n]*')).Value)
$cl = ($log -split "`n" | Where-Object { $_ -match '==== CRASH' }) -join ''
Check 'no exception reached the debugger, and the crash record was read from the dump: writing address 8, in the stand-in' ($log -notmatch 'second chance' -and $cl -match "CRASH \(from Windows' crash dump sr3wd_crash\.exe\.\d+\.dmp\): access violation 0xC0000005 at [0-9A-F]{8} \(sr3wd_crash\.exe\+0x[0-9A-F]+\) \(writing 0x00000008\)") $cl.Trim()
Check 'its registers and stack' ($log -match '  edi [0-9A-F]{8} .* eip [0-9A-F]{8}  esp [0-9A-F]{8}' -and $log -match '  stack: [0-9A-F]{8}')
Check 'news for the launcher: the crash, from the dump' (@($news | Where-Object { $_ -match "^the game crashed: access violation .*seen in Windows' crash dump" }).Count -eq 1) ($news -join ' | ')

"2. freeze: the message loop stuck for 8 s"
$dir = Join-Path $Work 'freeze_case'; Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
$p = Run $hangExe '2 8 3'
[void][Sr3Watchdog]::Start($p.Id, $dir, 3, 0)
[void]$p.WaitForExit(30000); [void][Sr3Watchdog]::WaitFinished(10000)
$log = Get-Content -Raw ([Sr3Watchdog]::LogPath); $news = News; $lines = $log -split "`r?`n"
$off = Fn $log 'stuck_here'
$tStuck = ($lines | Where-Object { $_ -match 'stand-in: stuck now' } | Select-Object -First 1); $tFreeze = ($lines | Where-Object { $_ -match '==== FREEZE' } | Select-Object -First 1)
$secs = if ($tStuck -and $tFreeze) { ([datetime]::ParseExact($tFreeze.Substring(0, 12), 'HH:mm:ss.fff', $null) - [datetime]::ParseExact($tStuck.Substring(0, 12), 'HH:mm:ss.fff', $null)).TotalSeconds } else { -1 }
Check 'the freeze is recorded 3 to 6 s after the loop got stuck' ($secs -ge 3 -and $secs -le 6.5) ('{0:0.0} s; {1}' -f $secs, $(if ($tFreeze) { $tFreeze.Substring(13).Trim() } else { 'no record' }))
$win = @($lines | Where-Object { $_ -match '\[window\] thread' })
$winCalls = @(for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -match '\[window\] thread') { $lines[$i + 1] } })
Check 'three samples, the window thread first in each' (@($lines | Where-Object { $_ -match '-- sample [123] of 3' }).Count -eq 3 -and $win.Count -eq 3)
Check 'the window thread''s stack shows stuck_here() in all three' (@($winCalls | Where-Object { InFn "$_" 'sr3wd_hang.exe' $off 0x40 }).Count -eq 3) ("$($winCalls | Select-Object -First 1)".Trim())
Check 'the other thread is there, with where it started, unchanged in the later samples' ($log -match '    thread \d+ \(from [0-9A-F]{8} \(sr3wd_hang\.exe\+0x[0-9A-F]+\)\): eip' -and $log -match 'thread \d+: unchanged \(eip')
$dump = Get-ChildItem $dir -Filter 'freeze_*.dmp' | Select-Object -First 1
Check 'a minidump' ($null -ne $dump -and $dump.Length -gt 10000) $(if ($dump) { "$($dump.Name), $([int]($dump.Length / 1024)) KB" } else { 'none' })
Check 'it answers again: noted, and only one freeze record' ($log -match 'answers again \(about \d+ s without an answer\)' -and @($lines | Where-Object { $_ -match '==== FREEZE' }).Count -eq 1)
Check 'the program ran to its end (exit code 0)' ($p.ExitCode -eq 0) "exit code $($p.ExitCode)"
Check 'news: stopped responding (with the minidump), then responding again' (@($news | Where-Object { $_ -match '^the game stopped responding at .* minidump freeze_case\\freeze_' }).Count -eq 1 -and @($news | Where-Object { $_ -match '^the game is responding again \(it hung for about \d+ s\)\.$' }).Count -eq 1) ($news -join ' | ')

"3. a message box (as the game's ""Out of memory for VB""): the window still answers"
$dir = Join-Path $Work 'box_case'; Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
$p = Run $hangExe '2 0 7 box'
[void][Sr3Watchdog]::Start($p.Id, $dir, 3, 0)
[void]$p.WaitForExit(20000); [void][Sr3Watchdog]::WaitFinished(10000)
$log = Get-Content -Raw ([Sr3Watchdog]::LogPath); $news = News
Check 'the box is recorded with its title and text, three samples, a minidump' ($log -match '==== MESSAGE BOX: the game shows a message box: "SEGA Rally 3": Out of memory for VB' -and @([regex]::Matches($log, '-- sample [123] of 3')).Count -eq 3 -and @(Get-ChildItem $dir -Filter 'msgbox_*.dmp').Count -eq 1)
Check 'once, and not taken for a freeze' (@([regex]::Matches($log, '==== MESSAGE BOX')).Count -eq 1 -and $log -notmatch '==== FREEZE')
Check 'news: the box and its text' (@($news | Where-Object { $_ -match '^the game shows a message box "SEGA Rally 3": Out of memory for VB \(box_case\\watchdog_.*, minidump box_case\\msgbox_.*\.dmp\)\.$' }).Count -eq 1) ($news -join ' | ')

"4. detach: Stop() while the program runs"
$dir = Join-Path $Work 'detach_case'; Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
$p = Run $hangExe '30 0 0'
[void][Sr3Watchdog]::Start($p.Id, $dir, 3, 0)
for ($i = 0; $i -lt 50 -and -not [Sr3Watchdog]::Attached; $i++) { Start-Sleep -Milliseconds 100 }
$was = [WdTest]::Debugged($p.Id); Start-Sleep -Milliseconds 1500
[Sr3Watchdog]::Stop(5000); Start-Sleep -Milliseconds 1000
$log = Get-Content -Raw ([Sr3Watchdog]::LogPath); [void](News)
Check 'attached (the program has a debugger), then detached by Stop()' ($was -and $log -match 'detached \(the game runs on\)' -and -not [Sr3Watchdog]::Attached -and [Sr3Watchdog]::Finished)
Check 'the program runs on, answers, and has no debugger any more' (-not $p.HasExited -and [WdTest]::Answers($p.Id) -and -not [WdTest]::Debugged($p.Id))
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue

"5. kill: the watchdog's own process is killed while attached; a second watchdog meanwhile"
$dir = Join-Path $Work 'kill_case'; Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue; New-Item -ItemType Directory -Force $dir | Out-Null
$p = Run $hangExe '12 6 30'
$marker = Join-Path $dir 'attached.txt'
$child = Start-Process powershell -WindowStyle Hidden -PassThru -ArgumentList '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command',
    "Add-Type -Path '$cs'; [void][Sr3Watchdog]::Start($($p.Id), '$dir\child', 3, 0); while (-not [Sr3Watchdog]::Attached) { Start-Sleep -Milliseconds 100 }; Set-Content '$marker' 'yes'; Start-Sleep 120"
for ($i = 0; $i -lt 200 -and -not (Test-Path $marker); $i++) { Start-Sleep -Milliseconds 100 }
Check 'the watchdog in another process has attached' ((Test-Path $marker) -and [WdTest]::Debugged($p.Id))
[void][Sr3Watchdog]::Start($p.Id, "$dir\second", 3, 0)
Start-Sleep -Milliseconds 1500; $news = News
Check 'a second watchdog cannot attach, and says so' (@($news | Where-Object { $_ -match '^could not attach to the game \(error \d+.*freezes still are\.$' }).Count -eq 1) ($news -join ' | ')
for ($i = 0; $i -lt 400; $i++) { $news += News; if (@($news | Where-Object { $_ -match 'responding again' }).Count) { break }; Start-Sleep -Milliseconds 100 }   # stuck from 12 to 18 s
Check 'and still records the freeze (and the end of it)' (@($news | Where-Object { $_ -match '^the game stopped responding' }).Count -eq 1 -and @($news | Where-Object { $_ -match 'responding again' }).Count -eq 1) ($news -join ' | ')
[Sr3Watchdog]::Stop(5000)
Stop-Process -Id $child.Id -Force; Start-Sleep -Milliseconds 1500
Check 'its process killed: the program runs on, answers, and has no debugger' (-not $p.HasExited -and [WdTest]::Answers($p.Id) -and -not [WdTest]::Debugged($p.Id))
Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue

if (-not $Keep) { foreach ($d in 'crash_case', 'freeze_case', 'box_case', 'detach_case', 'kill_case') { Remove-Item (Join-Path $Work $d) -Recurse -Force -ErrorAction SilentlyContinue } }
"WATCHDOG CHECKS: $script:pass passed, $script:fail failed"

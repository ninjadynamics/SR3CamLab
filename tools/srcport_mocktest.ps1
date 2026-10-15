# Runs patches.ps1's SRC-turning install / keep / remove (Install-SrcPort, Remove-SrcPort) against a fake in-memory game.
#   powershell -ExecutionPolicy Bypass -File srcport_mocktest.ps1        the last line counts the checks
$src = Get-Content (Join-Path $PSScriptRoot '..\patches.ps1') -Raw
$cut = $src.IndexOf('# ---- launch (unless')
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$body = $src.Substring(0, $cut).Replace('$PSScriptRoot', "'$repo'").Replace('[Sr3Mem]::Alloc', '[MockMem]::Alloc').Replace('[Sr3Mem]::Write', '[MockMem]::Write').Replace('[Sr3Mem]::Read', '[MockMem]::Read').Replace('[Sr3Mem]::Suspend', '[MockMem]::Nop').Replace('[Sr3Mem]::Resume', '[MockMem]::Nop')
$body += @'

Add-Type @"
using System; using System.Collections.Generic;
public static class MockMem {
    public static Dictionary<long, byte> M = new Dictionary<long, byte>();
    static long next = 0x20000000;
    public static long Alloc(IntPtr h, int n) { long a = next; next += 0x10000; for (int i = 0; i < n; i++) M[a + i] = 0; return a; }
    public static void Write(IntPtr h, long va, byte[] b, bool w) { for (int i = 0; i < b.Length; i++) M[va + i] = b[i]; }
    public static byte[] Read(IntPtr h, long va, int n) { var b = new byte[n]; for (int i = 0; i < n; i++) { byte v; if (!M.TryGetValue(va + i, out v)) return null; b[i] = v; } return b; }
    public static void Nop(IntPtr h) { }
}
"@
$script:pass = 0; $script:fail = 0
function Check([string]$what, [bool]$ok) { if ($ok) { $script:pass++; "  ok     $what" } else { $script:fail++; "  FAILED $what" } }
function Log($m) { "    log: $m" }
$h = [IntPtr]::Zero
[MockMem]::Write(0, $SrcPortSite, ([BitConverter]::GetBytes([uint32]$SrcPortStock)), $false)
$code = HexToBytes $SrcPortCode
Install-SrcPort $h
$cave = $script:SrcPortCave
Check ("1. install: the vehicle step's entry 0x{0:X} -> 0x{1:X} (cave + entry)" -f $SrcPortSite, (Read-GamePtr $h $SrcPortSite)) ($cave -and (Read-GamePtr $h $SrcPortSite) -eq $cave + $SrcPortEntry)
$got = [MockMem]::Read(0, $cave, $code.Length); $sites = @{}
for ($i = 0; $i -lt $SrcPortRelocs.Length; $i += 4) { $sites[[Convert]::ToInt32($SrcPortRelocs.Substring($i, 4), 16)] = 1 }
$bad = 0
foreach ($o in $sites.Keys) { if ([BitConverter]::ToUInt32($got, $o) -ne ([BitConverter]::ToUInt32($code, $o) + [uint32]$cave)) { $bad++ } }
$other = 0; for ($i = 0; $i -lt $code.Length; $i++) { $in = $false; foreach ($d in 0, 1, 2, 3) { if ($sites.ContainsKey($i - $d)) { $in = $true } }; if (-not $in -and $got[$i] -ne $code[$i]) { $other++ } }
Check ("   {0} relocations each got the cave's address added ({1} wrong); every other byte as built ({2} differ)" -f $sites.Count, $bad, $other) ($bad -eq 0 -and $other -eq 0)
Check ('   the data block: magic SRCP, version {0}, mode {1} (2 = on), the log pointer inside the area' -f (Read-GameInt $h ($cave + $SrcPortData + 4)), (Read-GameInt $h ($cave + $SrcPortData + 8))) ((Read-GameInt $h ($cave + $SrcPortData)) -eq 0x50435253 -and (Read-GameInt $h ($cave + $SrcPortData + 8)) -eq 2 -and (Read-GamePtr $h ($cave + $SrcPortData + 0x1E0)) -gt $cave -and (Read-GamePtr $h ($cave + $SrcPortData + 0x1E0)) -lt $cave + $SrcPortAlloc)
$script:SrcPortCave = $null
Install-SrcPort $h
Check '2. PLAY.bat again on the same game: the routine in place is kept (no second copy)' ($script:SrcPortCave -eq $cave -and (Read-GamePtr $h $SrcPortSite) -eq $cave + $SrcPortEntry)
[MockMem]::Write(0, $cave + $SrcPortData + 4, ([BitConverter]::GetBytes([int]0)), $false)
Install-SrcPort $h
Check ('3. an older version in the game: a new copy (0x{0:X}) takes the hook' -f $script:SrcPortCave) ($script:SrcPortCave -ne $cave -and (Read-GamePtr $h $SrcPortSite) -eq $script:SrcPortCave + $SrcPortEntry)
Remove-SrcPort $h
Check '4. remove: SEGA''s vehicle step back in the vtable' ((Read-GamePtr $h $SrcPortSite) -eq $SrcPortStock -and -not $script:SrcPortCave)
Remove-SrcPort $h
Check '5. remove again: nothing to do' ((Read-GamePtr $h $SrcPortSite) -eq $SrcPortStock)
[MockMem]::Write(0, $SrcPortSite, ([BitConverter]::GetBytes([uint32]0x30000000)), $false)
Install-SrcPort $h
Check '6. the entry points to code that is not ours: left alone' ((Read-GamePtr $h $SrcPortSite) -eq 0x30000000 -and -not $script:SrcPortCave)
"SRCPORT MOCK CHECKS: $($script:pass) passed, $($script:fail) failed"
'@
$tmp = Join-Path $env:TEMP 'sr3_srcport_mock.ps1'
Set-Content -LiteralPath $tmp -Value $body -Encoding UTF8
try { & $tmp -NoLaunch } finally { Remove-Item -LiteralPath $tmp }

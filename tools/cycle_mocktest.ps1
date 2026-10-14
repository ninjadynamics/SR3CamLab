# Runs patch.ps1's camera-cycle install/update/remove against a fake in-memory game.
param([string]$Profile = 'Daytona')
$src = Get-Content (Join-Path $PSScriptRoot '..\patch.ps1') -Raw
$cut = $src.IndexOf('# ---- launch (unless')
$body = $src.Substring(0, $cut).Replace('[Sr3Mem]::Alloc', '[MockMem]::Alloc').Replace('[Sr3Mem]::Write', '[MockMem]::Write').Replace('[Sr3Mem]::Read', '[MockMem]::Read').Replace('. (Join-Path $PSScriptRoot ''setup.ps1'')', ". '" + (Join-Path $PSScriptRoot '..\setup.ps1') + "'")
$body += @'

Add-Type @"
using System; using System.Collections.Generic;
public static class MockMem {
    public static Dictionary<long, byte> M = new Dictionary<long, byte>();
    static long next = 0x20000000;
    public static long Alloc(IntPtr h, int n) { long a = next; next += 0x10000; for (int i = 0; i < n; i++) M[a + i] = 0; return a; }
    public static void Write(IntPtr h, long va, byte[] b, bool w) { for (int i = 0; i < b.Length; i++) M[va + i] = b[i]; }
    public static byte[] Read(IntPtr h, long va, int n) { var b = new byte[n]; for (int i = 0; i < n; i++) { byte v; if (!M.TryGetValue(va + i, out v)) return null; b[i] = v; } return b; }
}
"@
function Hex($b) { ($b | ForEach-Object { $_.ToString('x2') }) -join '' }
[MockMem]::Write(0, $HookDrawVA, $HookDrawOrig, $false)
[MockMem]::Write(0, 0xA65794, ([BitConverter]::GetBytes([int]1)), $false)   # PVS off, as a CamLab camera leaves it
[MockMem]::Write(0, $HookLostVA, $HookLostOrig, $false)
[MockMem]::Write(0, $HookBlendVA, $HookBlendOrig, $false)
foreach ($v in $CamUpdateHooks) { [MockMem]::Write(0, $v[0], ([BitConverter]::GetBytes([int]$v[1])), $false) }
$h = [IntPtr]::Zero
function BlendTo { $b = [MockMem]::Read(0, $HookBlendVA, 5); if ($b[0] -ne 0xE8) { return -1 }; return $HookBlendVA + 5 + [BitConverter]::ToInt32($b, 1) }   # where the blend's hook site calls
Install-Cycle $h
$base = Find-Cycle $h
'1. install: block at {0:X8}, draw hook {1}, lost hook {2}' -f $base, (Hex ([MockMem]::Read(0, $HookDrawVA, 5))), (Hex ([MockMem]::Read(0, $HookLostVA, 5)))
$lost = $HookLostVA + 5 + [BitConverter]::ToInt32([MockMem]::Read(0, $HookLostVA, 5), 1)
'   lost hook lands on block+{0:X} (expected {1:X}); code matches: {2}' -f ($lost - $base), $CycleLost, (Same ([MockMem]::Read(0, $base + $CycleDraw, (HexToBytes $CycleCode).Length)) (HexToBytes $CycleCode))
'   blend hook {0} lands on block+{1:X} (expected {2:X}); second code area matches: {3}; ends inside the block: {4}' -f (Hex ([MockMem]::Read(0, $HookBlendVA, 5))), ((BlendTo) - $base), $CycleBlend, (Same ([MockMem]::Read(0, $base + $CycleCode2At, (HexToBytes $CycleCode2).Length)) (HexToBytes $CycleCode2)), (($CycleCode2At + (HexToBytes $CycleCode2).Length) -le $CycleSize)
$q = [MockMem]::Read(0, $base + $CycleQol, 12)
'   smoothing and blend at block+{0:X}: mouse {1} s, keys {2} s, blend {3} s (profiles.yaml: mouseSmoothing {4}, cameraBlend {5}; keys = 2 x mouse)' -f $CycleQol, [BitConverter]::ToSingle($q, 0), [BitConverter]::ToSingle($q, 4), [BitConverter]::ToSingle($q, 8), $file.Top['mousesmoothing'], $file.Top['camerablend']
'   their state starts empty (block+{0:X} .. 2400 all zero): {1}' -f ($CycleQol + 12), (@([MockMem]::Read(0, $base + $CycleQol + 12, 0x2400 - $CycleQol - 12) | Where-Object { $_ -ne 0 }).Count -eq 0)
$d = [MockMem]::Read(0, $base, 0x1000)
'   slots {0}, start {1}, popup {2} px, magic {3}' -f [BitConverter]::ToInt32($d, 0x20), [BitConverter]::ToInt32($d, 0x24), [BitConverter]::ToInt32($d, 0x18), [Text.Encoding]::ASCII.GetString($d, 0, 4)
for ($i = 0; $i -lt [BitConverter]::ToInt32($d, 0x20); $i++) {
    $n = [Text.Encoding]::ASCII.GetString($d, 0x100 + 32 * $i, 32).TrimEnd([char]0)
    '   slot {0}: {1,-20} colour {2:X8}  kmin {3} kmax {4} mult {5}' -f $i, $n, [BitConverter]::ToUInt32($d, 0xE00 + 4 * $i), [BitConverter]::ToSingle($d, 0x500 + 0x5C * $i + 0x10), [BitConverter]::ToSingle($d, 0x500 + 0x5C * $i + 0x14), [BitConverter]::ToSingle($d, 0x500 + 0x5C * $i + 0x2C)
}
$g = [MockMem]::Read(0, $base + 0x2000, 0x260)
for ($i = 0; $i -lt 12; $i++) {
    '   game cam +{0:X8}: {1,-24} colour {2:X8}' -f [BitConverter]::ToInt32($g, 0x1B0 + 4 * $i), [Text.Encoding]::ASCII.GetString($g, 32 * $i, 32).TrimEnd([char]0), [BitConverter]::ToUInt32($g, 0x210 + 4 * $i)
}
'   hidden list: ' + ((0..11 | ForEach-Object { '{0:X}' -f [BitConverter]::ToInt32($g, 0x1E0 + 4 * $_) }) -join ' ')
'   camera string: ' + [Text.Encoding]::ASCII.GetString($d, 0xE0, 16).TrimEnd([char]0)
'   strings: ' + (([Text.Encoding]::ASCII.GetString($d, 0x60, 0x40) + [Text.Encoding]::ASCII.GetString($d, 0xEA0, 0x70)) -replace "`0+", ' | ')
'   mouse k: {0} {1} {2} {3}' -f [BitConverter]::ToSingle($d, 0xF10), [BitConverter]::ToSingle($d, 0xF14), [BitConverter]::ToSingle($d, 0xF18), [BitConverter]::ToSingle($d, 0xF1C)
'   camera update hooks: ' + (($CamUpdateHooks | ForEach-Object { '{0:X}->block+{1:X}' -f $_[0], ([BitConverter]::ToUInt32([MockMem]::Read(0, $_[0], 4), 0) - $base) }) -join ', ') + "  (rot {0:X}, free {1:X})" -f $CycleRot, $CycleFree
$mgr = 0x30000018; [MockMem]::Write(0, $base + 0x58, ([BitConverter]::GetBytes([int]$mgr)), $false); [MockMem]::Write(0, $base + 0xBC, ([BitConverter]::GetBytes([int]2)), $false)
[MockMem]::Write(0, $mgr + 0x510, ([BitConverter]::GetBytes([int]0x6EB808)), $false); [MockMem]::Write(0, $mgr + 0x1A38, ([BitConverter]::GetBytes([int]0x6EBDF0)), $false)
$lst = New-Object byte[] 0x40; [Array]::Copy([BitConverter]::GetBytes([int]14), 0, $lst, 0, 4); [Array]::Copy([BitConverter]::GetBytes([int]($mgr + 0x510)), 0, $lst, 8, 4); [MockMem]::Write(0, $mgr + 0x22C, $lst, $false)
$orig = New-Object byte[] 12; [Array]::Copy([BitConverter]::GetBytes([int]($mgr + 0x1700)), 0, $orig, 0, 4); [Array]::Copy([BitConverter]::GetBytes([int]($mgr + 0x189C)), 0, $orig, 4, 4); [MockMem]::Write(0, $base + 0x2180, $orig, $false)
function SeatOnCopy($b) { [MockMem]::Write(0, $b + 0x2258, ([BitConverter]::GetBytes([int]0x0BADF00D)), $false); [MockMem]::Write(0, $mgr + 0x1A38 + 0x194, ([BitConverter]::GetBytes([int]($b + 0x2240))), $false) }
function Seat { '{0:X8}' -f [BitConverter]::ToUInt32([MockMem]::Read(0, $mgr + 0x1A38 + 0x194, 4), 0) }
SeatOnCopy $base
Install-Cycle $h
'2. update: block still at {0:X8}: {1}' -f (Find-Cycle $h), ((Find-Cycle $h) -eq $base)
'   blend hook still on block+{0:X}' -f ((BlendTo) - $base)
[MockMem]::Write(0, $base + $CycleQol + 0x10, [byte[]]@(1, 2, 3, 4), $false)   # something outstanding in the old block's smoothing state
$oldCode = [MockMem]::Read(0, $base + $CycleDraw, 0x1000); $oldCode2 = [MockMem]::Read(0, $base + $CycleCode2At, $CycleSize - $CycleCode2At)
$CycleCode = $CycleCode.Substring(0, $CycleCode.Length - 2) + 'cc'          # a newer build: must move to a new block
Install-Cycle $h
$nb = Find-Cycle $h
'   cockpit eye after moving blocks (want 0BADF00D): ' + (Seat)
'2b. newer build: moved to {0:X8} ({1}); camera hooks now {2}' -f $nb, ($nb -ne $base), (($CamUpdateHooks | ForEach-Object { $t = [BitConverter]::ToUInt32([MockMem]::Read(0, $_[0], 4), 0); if (($t -band 0xFFFF0000) -eq $nb) { 'new block' } else { 'STALE {0:X8}' -f $t } }) -join ', ')
'   blend hook now on the new block+{0:X} (expected {1:X}); the code of the old block was not written over: {2}; the smoothing / blend state of the new one starts empty: {3}' -f ((BlendTo) - $nb), $CycleBlend, ((Same ([MockMem]::Read(0, $base + $CycleDraw, 0x1000)) $oldCode) -and (Same ([MockMem]::Read(0, $base + $CycleCode2At, $CycleSize - $CycleCode2At)) $oldCode2)), (@([MockMem]::Read(0, $nb + $CycleQol + 12, 0x2400 - $CycleQol - 12) | Where-Object { $_ -ne 0 }).Count -eq 0)
$CycleCode2 = $CycleCode2.Substring(0, $CycleCode2.Length - 2) + 'cc'        # a build that differs in the second code area only: a new block too
Install-Cycle $h
$nb2 = Find-Cycle $h
'2c. newer second code area only: moved to {0:X8} ({1}); blend hook on that block+{2:X}' -f $nb2, ($nb2 -ne $nb -and $nb2 -ne $base), ((BlendTo) - $nb2)
$nb = $nb2
SeatOnCopy $nb
Remove-Cycle $h
'   cockpit eye after remove (want 0BADF00D): ' + (Seat)
'   PVS flag after remove (want 0): ' + [BitConverter]::ToInt32([MockMem]::Read(0, 0xA65794, 4), 0)
'   game list after remove: ' + ((0..3 | ForEach-Object { '{0:X}' -f [BitConverter]::ToInt32([MockMem]::Read(0, $mgr + 0x22C + 4 * $_, 4), 0) }) -join ' ')
'   camera update hooks after remove: ' + (($CamUpdateHooks | ForEach-Object { '{0:X}' -f [BitConverter]::ToUInt32([MockMem]::Read(0, $_[0], 4), 0) }) -join ', ')
'3. remove: draw hook {0}, lost hook {1}, restored: {2}' -f (Hex ([MockMem]::Read(0, $HookDrawVA, 5))), (Hex ([MockMem]::Read(0, $HookLostVA, 5))), ((Same ([MockMem]::Read(0, $HookDrawVA, 5)) $HookDrawOrig) -and (Same ([MockMem]::Read(0, $HookLostVA, 5)) $HookLostOrig))
'   blend hook after remove: {0}, the call of the game again: {1}' -f (Hex ([MockMem]::Read(0, $HookBlendVA, 5))), (Same ([MockMem]::Read(0, $HookBlendVA, 5)) $HookBlendOrig)
# a game whose bytes at the blend's hook site are not the expected ones: everything else goes in, the site is left alone
$odd = [byte[]]@(0xE8, 0x11, 0x22, 0x33, 0x00); [MockMem]::Write(0, $HookBlendVA, $odd, $false)
'4. other bytes at the blend hook site ({0}): the next line must say the blend is left out' -f (Hex $odd)
Install-Cycle $h
$b4 = Find-Cycle $h
'   cycle installed at {0:X8}: {1}; site untouched: {2}; reported as hooked: {3}' -f $b4, ($b4 -ne 0), (Same ([MockMem]::Read(0, $HookBlendVA, 5)) $odd), $script:BlendHooked
Remove-Cycle $h
'   after remove: site still untouched: {0}; draw hook restored: {1}' -f (Same ([MockMem]::Read(0, $HookBlendVA, 5)) $odd), (Same ([MockMem]::Read(0, $HookDrawVA, 5)) $HookDrawOrig)
# cameraBlend 0: no hook at all at the blend's site, and one that is there goes away when the setting changes to 0 in a running game
[MockMem]::Write(0, $HookBlendVA, $HookBlendOrig, $false); $blendSec = 0
Install-Cycle $h
$b5 = Find-Cycle $h
'5. cameraBlend 0: cycle installed: {0}; blend site keeps the call of the game: {1}; blend time in the block: {2}' -f ($b5 -ne 0), (Same ([MockMem]::Read(0, $HookBlendVA, 5)) $HookBlendOrig), [BitConverter]::ToSingle([MockMem]::Read(0, $b5 + $CycleQol + 8, 4), 0)
$blendSec = 0.75; Install-Cycle $h
'   set to 0.75 s in the running game: hooked to block+{0:X} (same block: {1}), blend time {2}' -f ((BlendTo) - $b5), ((Find-Cycle $h) -eq $b5), [BitConverter]::ToSingle([MockMem]::Read(0, $b5 + $CycleQol + 8, 4), 0)
$blendSec = 0; $lookSmooth = 0; Install-Cycle $h
'   back to 0, mouse smoothing 0 too: the call of the game again: {0}; mouse / keys / blend in the block: {1} {2} {3}' -f (Same ([MockMem]::Read(0, $HookBlendVA, 5)) $HookBlendOrig), [BitConverter]::ToSingle([MockMem]::Read(0, $b5 + $CycleQol, 4), 0), [BitConverter]::ToSingle([MockMem]::Read(0, $b5 + $CycleQol + 4, 4), 0), [BitConverter]::ToSingle([MockMem]::Read(0, $b5 + $CycleQol + 8, 4), 0)
Remove-Cycle $h
'@
$tmp = Join-Path $env:TEMP 'sr3_cycle_mock.ps1'
Set-Content -LiteralPath $tmp -Value $body -Encoding UTF8
try { & $tmp $Profile -ProfilesFile (Join-Path $PSScriptRoot '..\profiles.yaml') } finally { Remove-Item -LiteralPath $tmp }

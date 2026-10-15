# patches.ps1's plan for one set of settings: everything it would write into a freshly started game, written instead
# into a fake game that holds the original bytes (the mock tests' way: its own code, with [Sr3Mem] swapped for [MockMem]).
# lockstep.py compares this with patches.dll's plan (patches_plan); they must be the same, byte for byte.
#   plan_ps1.ps1 -Out <plan.json> [-CameraProfile <name>] [-ProfilesFile <yaml>] [-Overlay <px>] [-MouseSmoothing <s>] [-CameraBlend <s>] [-Canary]
param([Parameter(Mandatory = $true)][string]$Out, [string]$CameraProfile = '', [string]$ProfilesFile = '', [int]$Overlay = -1,
      [double]$MouseSmoothing = -1, [double]$CameraBlend = -1, [switch]$Canary)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$src = Get-Content (Join-Path $repo 'patches.ps1') -Raw
$cut = $src.IndexOf('# ---- launch (unless')
$body = $src.Substring(0, $cut).Replace('[Sr3Mem]::Alloc', '[MockMem]::Alloc').Replace('[Sr3Mem]::Write', '[MockMem]::Write').Replace('[Sr3Mem]::Read', '[MockMem]::Read').Replace(
    '. (Join-Path $PSScriptRoot ''setup.ps1'')', ". '" + (Join-Path $repo 'setup.ps1') + "'").Replace("Join-Path `$PSScriptRoot 'profiles.yaml'", "Join-Path '$repo' 'profiles.yaml'")
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
foreach ($p in $Patches) { [MockMem]::Write(0, $p.VA, $p.OrigB, $false) }                 # a freshly started game
[MockMem]::Write(0, $HookDrawVA, $HookDrawOrig, $false); [MockMem]::Write(0, $HookLostVA, $HookLostOrig, $false); [MockMem]::Write(0, $HookBlendVA, $HookBlendOrig, $false)
foreach ($v in $CamUpdateHooks) { [MockMem]::Write(0, $v[0], ([BitConverter]::GetBytes([int]$v[1])), $false) }
$h = [IntPtr]::Zero
foreach ($p in $Patches) { [MockMem]::Write($h, $p.VA, $p.NewB, ($p.VA -eq $CaveVA)) }   # patches.ps1's main flow, fresh install
Install-Cycle $h
$base = Find-Cycle $h
$plan = [ordered]@{ profile = $ProfileName; slots = @($slots | ForEach-Object { $_.Name }); sites = [ordered]@{}; hooks = [ordered]@{}; vtables = [ordered]@{}; block = '' }
foreach ($p in $Patches) { $plan.sites['0x{0:X}' -f $p.VA] = Hex ([MockMem]::Read(0, $p.VA, $p.NewB.Length)) }
foreach ($va in $HookDrawVA, $HookLostVA, $HookBlendVA) {
    $b = [MockMem]::Read(0, $va, 5)
    $plan.hooks['0x{0:X}' -f $va] = if ($base -and $b[0] -eq 0xE8 -and -not (Same $b $HookBlendOrig) -and -not (Same $b $HookLostOrig)) { 'call block+0x{0:x}' -f ($va + 5 + [BitConverter]::ToInt32($b, 1) - $base) } else { Hex $b }
}
foreach ($v in $CamUpdateHooks) {
    $d = [BitConverter]::ToUInt32([MockMem]::Read(0, $v[0], 4), 0)
    $plan.vtables['0x{0:X}' -f $v[0]] = if ($base -and $d -ge $base -and $d -lt $base + $CycleSize) { 'block+0x{0:x}' -f ($d - $base) } else { '0x{0:x}' -f $d }
}
if ($base) { $plan.block = Hex ([MockMem]::Read(0, $base, $CycleSize)) }
[IO.File]::WriteAllText($PlanOut, ($plan | ConvertTo-Json -Depth 4), (New-Object Text.UTF8Encoding $false))
'@
$work = Join-Path $env:TEMP ('sr3_plan_' + [Guid]::NewGuid().ToString('N')); New-Item -ItemType Directory -Force $work | Out-Null   # (an empty folder: the script unblocks its own folder's files)
$tmp = Join-Path $work 'plan_body.ps1'
Set-Content -LiteralPath $tmp -Value $body -Encoding UTF8
$a = @{ PlanOut = $null }
try {
    $PlanOut = [IO.Path]::GetFullPath($Out)
    $args_ = @{}
    if ($CameraProfile) { $args_.CameraProfile = $CameraProfile }
    if ($ProfilesFile) { $args_.ProfilesFile = $ProfilesFile }
    if ($Overlay -ge 0) { $args_.Overlay = $Overlay }
    if ($MouseSmoothing -ge 0) { $args_.MouseSmoothing = $MouseSmoothing }
    if ($CameraBlend -ge 0) { $args_.CameraBlend = $CameraBlend }
    if ($Canary) { $args_.Canary = $true }
    & $tmp @args_
} finally { Remove-Item -LiteralPath $work -Recurse -Force -ErrorAction SilentlyContinue }

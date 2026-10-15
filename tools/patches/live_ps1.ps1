# patches.ps1's live part (Set-MenuTimers, Set-CarLists, Set-Handling, Watch-Tracks) on a scripted fake game, writing every
# write, suspend / resume, allocation, log line and screen grab to a trace. live_lockstep.py runs livetest.exe (pc_live.c) on
# the same game and compares the two traces line for line. The fake game is livetest.c's (see there; keep the two alike).
#   live_ps1.ps1 -Scenario <scenario.json> -GameExe <...\Rally.exe> -ModDir <dir> -Out <trace>
# The script is cut before its launch part, [Sr3Mem] becomes [MockGame], and the outside world (Get-Now,
# Test-KeyDown, Get-FrontWindow, the screen grab, Log, Start-Sleep) is replaced by functions defined after it. It runs as
# <ModDir>\live_body.ps1, so $PSScriptRoot (handling.json, ..\Screenshots) is the mod folder, as in a real install.
param([Parameter(Mandatory = $true)][string]$Scenario, [Parameter(Mandatory = $true)][string]$GameExe, [Parameter(Mandatory = $true)][string]$ModDir, [Parameter(Mandatory = $true)][string]$Out)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$src = Get-Content (Join-Path $repo 'patches.ps1') -Raw
$cut = $src.IndexOf('# ---- launch (unless')
$body = $src.Substring(0, $cut).Replace('[Sr3Mem]::', '[MockGame]::').Replace('Start-Sleep -Milliseconds', 'Skip-Sleep').Replace(
    '. (Join-Path $PSScriptRoot ''setup.ps1'')', ". '" + (Join-Path $repo 'setup.ps1') + "'").Replace("Join-Path `$PSScriptRoot 'profiles.yaml'", "Join-Path '$repo' 'profiles.yaml'")
Add-Type @"
using System; using System.Collections.Generic; using System.Text;
public class MockProc { public int Id = 1; public bool HasExited { get { return MockGame.Step >= MockGame.Count; } } public void WaitForExit() { } }
public static class MockGame {
    public static Dictionary<long, byte> M = new Dictionary<long, byte>();
    public static List<string> T = new List<string>();
    public static bool Trace = false; public static long Base = 0, NextA = 0x20000000, Now = 0, Front = 0; public static int NextH = 14, Step = 0, Count = 0, Pad = 0, Phase = 0;
    public static HashSet<int> Keys = new HashSet<int>();
    static List<long> FT = new List<long>(), FFront = new List<long>(); static List<int> FPad = new List<int>(); static List<int[]> FKeys = new List<int[]>();
    static List<long[]> FVa = new List<long[]>(); static List<string[]> FHex = new List<string[]>(); static List<bool[]> FRel = new List<bool[]>();
    public static void AddFrame(long t, int pad, long front, int[] keys, long[] va, string[] hex, bool[] rel) { FT.Add(t); FPad.Add(pad); FFront.Add(front); FKeys.Add(keys); FVa.Add(va); FHex.Add(hex); FRel.Add(rel); Count++; }
    public static byte[] Hex(string h) { var b = new byte[h.Length / 2]; for (int i = 0; i < b.Length; i++) b[i] = Convert.ToByte(h.Substring(2 * i, 2), 16); return b; }
    public static void Put(long va, byte[] b) { for (int i = 0; i < b.Length; i++) M[va + i] = b[i]; }
    static bool Has(long a) { return M.ContainsKey(a) && M.ContainsKey(a + 1) && M.ContainsKey(a + 2) && M.ContainsKey(a + 3); }
    public static int I(long a) { if (!Has(a)) return 0; return M[a] | (M[a + 1] << 8) | (M[a + 2] << 16) | (M[a + 3] << 24); }
    public static void PutI(long a, int v) { for (int i = 0; i < 4; i++) M[a + i] = (byte)(v >> (8 * i)); }
    public static string S(long a) { var sb = new StringBuilder(); byte b; while (sb.Length < 299 && M.TryGetValue(a, out b) && b != 0) { sb.Append((char)b); a++; } return sb.ToString(); }
    public static void PutS(long a, string s) { for (int i = 0; i < s.Length; i++) M[a + i] = (byte)s[i]; M[a + s.Length] = 0; }
    public static void Line(string s) { if (Trace) T.Add(s); }
    public static long Alloc(IntPtr h, int n) { long a = NextA; NextA += 0x10000; for (int i = 0; i < n && i < 0x10000; i++) M[a + i] = 0; Line(String.Format("A {0:X} {1:X}", n, a)); return a; }
    public static IntPtr Open(int pid) { return IntPtr.Zero; }
    public static void Close(IntPtr h) { }
    public static void Suspend(IntPtr h) { Line("S"); }
    public static void Resume(IntPtr h) { Line("R"); }
    public static void Write(IntPtr h, long va, byte[] b, bool keep) {
        if (Trace) { var sb = new StringBuilder(); foreach (byte x in b) sb.Append(x.ToString("x2")); T.Add(String.Format("W {0:X} {1} {2}", va, keep ? 1 : 0, sb)); }
        Put(va, b);
        if (Base != 0 && va == Base + 0x2264 && b.Length > 0 && b[0] == 1) {                    // the game loads its videos
            for (long e = 0x728630; e < 0x728750; e += 16) if (I(e + 12) == -1) PutI(e + 12, NextH++);
            PutI(Base + 0x2264, 0);
        }
        if (Base != 0 && va == Base + 0x2270 && I(va) != 0) {                                  // the game reopens a video object
            int hd = I(va) - 1; string p = S(I(Base + 0x2274));
            PutS(0xAD2F90 + 0x16C * (long)hd + 0xC, p); PutI(0xAD2F90 + 0x16C * (long)hd + 4, 1); PutI(Base + 0x2270, 0);
        }
    }
    static void NextFrame() {
        int k = Step++;
        if (Base != 0 && I(Base + 0x10) > 0) PutI(Base + 0x10, I(Base + 0x10) - 1);           // the block counts the popup's frames down
        for (int i = 0; i < FVa[k].Length; i++) Put(FVa[k][i] + (FRel[k][i] ? Base : 0), Hex(FHex[k][i]));
        Now = FT[k] * 10000; Pad = FPad[k]; Front = FFront[k]; Keys.Clear(); foreach (int v in FKeys[k]) Keys.Add(v);
        Line("F " + Step);
    }
    public static byte[] Read(IntPtr h, long va, int n) {
        if (va == 0x9D6E3C && n == 1) { if (Step >= Count) return null; NextFrame(); }
        var b = new byte[n]; for (int i = 0; i < n; i++) { byte v; if (!M.TryGetValue(va + i, out v)) return null; b[i] = v; } return b;
    }
}
"@
$body += @'

# ---- the outside world, faked (these come after patches.ps1's own and replace them)
function Log($m) { [MockGame]::Line("L $m") }
function Skip-Sleep($ms) { }
function Initialize-Host { }
$script:MockT0 = New-Object DateTime 2026, 10, 15, 12, 0, 0
function Get-Now { return $script:MockT0.AddTicks([MockGame]::Now) }
function Test-KeyDown([int]$vk) { return [MockGame]::Keys.Contains($vk) }
function Get-FrontWindow { return [MockGame]::Front }
function New-ScreenGrab { [MockGame]::Line('G grab'); return 'grab' }
function Save-ScreenGrab($bmp, [string]$path, $info) { [MockGame]::Line('G save ' + (Split-Path -Leaf $path) + ' ' + $(if ($info) { $info } else { '-' })) }
function Close-ScreenGrab($bmp) { if ($bmp) { [MockGame]::Line('G close') } }
function Request-Watchdog($game) { [MockGame]::Line('G watch'); return @('Watchdog on', 'watchdog_test.log') }   # (livetest.c's t_watch answers the same)

$sc = [IO.File]::ReadAllText($LiveScenario) | ConvertFrom-Json
$h = [IntPtr]::Zero
if ([MockGame]::Phase -eq 1) {                                  # the second run: PLAY.bat again on the running game, its install traced
    [MockGame]::Trace = $true
    try { $older = Test-CameraSites $h; Install-CameraPatch $h $older } catch { [MockGame]::Line('L ' + $_.Exception.Message) }
    [IO.File]::WriteAllText($LiveOut, (([MockGame]::T -join "`n") + "`n"), (New-Object Text.UTF8Encoding $false))
    return
}
if ($null -ne $sc.next_handle) { [MockGame]::NextH = [int]$sc.next_handle }
foreach ($f in @($sc.frames)) {
    $va = New-Object Collections.Generic.List[long]; $hx = New-Object Collections.Generic.List[string]; $rel = New-Object Collections.Generic.List[bool]
    foreach ($w in @($f.set)) { if ($w) { $va.Add([long]$w[0]); $hx.Add([string]$w[1]); $rel.Add($false) } }
    foreach ($w in @($f.setb)) { if ($w) { $va.Add([long]$w[0]); $hx.Add([string]$w[1]); $rel.Add($true) } }
    $keys = [int[]]@(@($f.keys) | Where-Object { $null -ne $_ } | ForEach-Object { [int]$_ })
    [MockGame]::AddFrame([long]$f.t, [int]$f.pad, [long]$f.front, $keys, $va.ToArray(), $hx.ToArray(), $rel.ToArray())
}
foreach ($p in $Patches) { [MockGame]::Put($p.VA, $p.OrigB) }                               # a freshly started game
[MockGame]::Put($HookDrawVA, $HookDrawOrig); [MockGame]::Put($HookLostVA, $HookLostOrig); [MockGame]::Put($HookBlendVA, $HookBlendOrig)
foreach ($v in $CamUpdateHooks) { [MockGame]::Put($v[0], ([BitConverter]::GetBytes([int]$v[1]))) }
foreach ($w in @($sc.mem)) { if ($w) { [MockGame]::Put([long]$w[0], [MockGame]::Hex([string]$w[1])) } }
$older = Test-CameraSites $h; Install-CameraPatch $h $older                                  # patches.ps1's main flow, fresh install
[MockGame]::Base = Find-Cycle $h
foreach ($w in @($sc.after)) { if ($w) { [MockGame]::Put([MockGame]::Base + [long]$w[0], [MockGame]::Hex([string]$w[1])) } }
foreach ($w in @($sc.between)) { if ($w) { [MockGame]::Put([long]$w[0], [MockGame]::Hex([string]$w[1])) } }
if ($sc.reinstall) { [MockGame]::Phase = 1; return }                                        # (live_ps1.ps1 runs the script again with the second settings)
$script:GameExePath = $LiveGameExe
[MockGame]::Trace = $true
$game = New-Object MockProc
Set-MenuTimers $game
Set-CarLists $game
Set-Handling $game
Watch-Tracks $game $LiveGameExe
[IO.File]::WriteAllText($LiveOut, (([MockGame]::T -join "`n") + "`n"), (New-Object Text.UTF8Encoding $false))
'@
$tmp = Join-Path $ModDir 'live_body.ps1'
Set-Content -LiteralPath $tmp -Value $body -Encoding UTF8
$LiveScenario = [IO.Path]::GetFullPath($Scenario); $LiveGameExe = $GameExe; $LiveOut = [IO.Path]::GetFullPath($Out)
try {
    & $tmp
    $ri = ([IO.File]::ReadAllText($LiveScenario) | ConvertFrom-Json).reinstall
    if ($ri) {                                                    # the same script again on the same fake game, with the second run's settings
        $p2 = @{}
        if ($ri.profile) { $p2.CameraProfile = [string]$ri.profile }
        if ($ri.profiles_file) { $p2.ProfilesFile = [string]$ri.profiles_file }
        if ($null -ne $ri.overlay) { $p2.Overlay = [int]$ri.overlay }
        if ($null -ne $ri.mouse) { $p2.MouseSmoothing = [double]$ri.mouse }
        if ($null -ne $ri.blend) { $p2.CameraBlend = [double]$ri.blend }
        if ($ri.canary) { $p2.Canary = $true }
        & $tmp @p2
    }
} finally { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }

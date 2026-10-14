# Runs patch.ps1's switcher (Watch-Tracks) against a scripted fake game to check a track's own tune (Set-CourseTune):
# the stream record of the Classic slot's music must be turned to the tune only while a track that has one is the
# current choice, and be the game's own again with every other track. Same method as switch_mocktest.ps1: the game's
# memory is a dictionary, nothing real is touched.
$src = Get-Content (Join-Path $PSScriptRoot '..\patch.ps1') -Raw
$cut = $src.IndexOf('# ---- launch (unless')
$body = $src.Substring(0, $cut).Replace('[Sr3Mem]::Alloc', '[MockTune]::Alloc').Replace('[Sr3Mem]::Write', '[MockTune]::Write').Replace('[Sr3Mem]::Read', '[MockTune]::Read').Replace('[Sr3Mem]::Open', '[MockTune]::Open').Replace('[Sr3Mem]::Close', '[MockTune]::Close').Replace('. (Join-Path $PSScriptRoot ''setup.ps1'')', ". '" + (Join-Path $PSScriptRoot '..\setup.ps1') + "'").Replace('Start-Sleep -Milliseconds', 'Skip-Sleep')
Add-Type @"
using System; using System.Collections.Generic; using System.Text;
public class MockTuneProc { public int Id = 1; public bool HasExited { get { return MockTune.Step >= MockTune.Script.Count; } } public void WaitForExit() { } }
public static class MockTune {
    public static Dictionary<long, byte> M = new Dictionary<long, byte>();
    public static List<string> Script = new List<string>(), Out = new List<string>();
    public static int Step = 0; public static long Base = 0x20000000, RecB = 0, Info = 0;
    static long next = 0x20000000;
    public static long Alloc(IntPtr h, int n) { long a = next; next += 0x10000; for (int i = 0; i < n; i++) M[a + i] = 0; return a; }
    public static IntPtr Open(int pid) { return IntPtr.Zero; }
    public static void Close(IntPtr h) { }
    public static long U(long a) { return (uint)(M[a] | (M[a + 1] << 8) | (M[a + 2] << 16) | (M[a + 3] << 24)); }
    public static void PutI(long a, long v) { for (int i = 0; i < 4; i++) M[a + i] = (byte)(v >> (8 * i)); }
    public static string S(long a) { var sb = new StringBuilder(); byte b; while (M.TryGetValue(a, out b) && b != 0) { sb.Append((char)b); a++; } return sb.ToString(); }
    public static void PutS(long a, string s) { for (int i = 0; i < s.Length; i++) M[a + i] = (byte)s[i]; M[a + s.Length] = 0; }
    public static void Write(IntPtr h, long va, byte[] b, bool w) { for (int i = 0; i < b.Length; i++) M[va + i] = b[i]; }
    // every look at the menu flag is one tick of the script: "menu count current-track viewchange header-loaded"
    public static byte[] Read(IntPtr h, long va, int n) {
        if (va == 0x9D6E3C) {
            if (Step > 0) Report();
            if (Step >= Script.Count) return null;
            string[] p = Script[Step++].Split(' ');
            M[0x9D6E3C] = (byte)int.Parse(p[0]); PutI(0x9C442C, int.Parse(p[1])); PutS(0x30000100, p[2]); M[0x9DBB0C] = (byte)(p[3] == "1" ? 0xff : 0);
            if (p[4] == "1") { PutI(0x9C4EC0, 0x32000000); PutI(0x9C4EC4, 0x32000110); PutI(0x9C4EC8, 0x32000110 + 200 * 25); }
        }
        var b = new byte[n]; for (int i = 0; i < n; i++) { byte v; if (!M.TryGetValue(va + i, out v)) return null; b[i] = v; } return b;
    }
    static string last = "";
    static void Report() {
        string s = "folder 'track" + (char)M[0x6C607B] + "'  music name " + S(U(0x6451C5)) + "  stream 20: samples at " + (U(RecB + 0xC4) + 0xC0) + ", " + U(Info + 0xC8) + " bytes, loop start " + U(Info + 0xCC) + ", loops " + U(Info + 0xD0);
        Out.Add(String.Format("{0,3} [{1,-22}] {2}", Step, Script[Step - 1], s == last ? "(same)" : s)); last = s;
    }
}
"@
$body += @'

# ---- the fake game ----
function Skip-Sleep($ms) { }
$fake = Join-Path $env:TEMP 'sr3tunetest'; Remove-Item $fake -Recurse -Force -ErrorAction SilentlyContinue
foreach ($d in 'Main_release\tracks\_SR3Extras', 'Main_release\track1\Desert4', 'Main_release\track2\Desert4', 'Main_release\track3\Desert4', 'Audio') { New-Item -ItemType Directory -Force (Join-Path $fake $d) | Out-Null }
[IO.File]::WriteAllBytes((Join-Path $fake 'Audio\EnglishStreamData.stm'), (New-Object byte[] 4096))
# three imported courses in the Classic slot: one with a tune (192-byte block at 2000, 400 bytes of samples, loop from byte 40),
# one without, and one whose tune is not in the stream file (it must be ignored)
@{ art = $false; slots = @{ Desert4 = @{ title = "Desert '95"; speech = ''; tracks = @(
        @{ title = 'Mountain'; dir = '1'; tune = @{ stream = 20; offset = 2000; bytes = 400; loopstart = 40 } },
        @{ title = 'Forest'; dir = '2' },
        @{ title = 'Lake Side'; dir = '3'; tune = @{ stream = 20; offset = 900000; bytes = 400; loopstart = 0 } }) } } } |
    ConvertTo-Json -Depth 6 | Set-Content (Join-Path $fake 'Main_release\tracks\_SR3Extras\switch.json')
function B([long]$v) { ,([byte[]]([BitConverter]::GetBytes($v))[0..3]) }
$h = [IntPtr]::Zero
[MockTune]::Write($h, $HookDrawVA, $HookDrawOrig, $false); [MockTune]::Write($h, $HookLostVA, $HookLostOrig, $false); [MockTune]::Write($h, $HookBlendVA, $HookBlendOrig, $false)
foreach ($v in $CamUpdateHooks) { [MockTune]::Write($h, $v[0], (B $v[1]), $false) }
foreach ($a in $TrackDirSites) { [MockTune]::Write($h, $a, [byte[]]@(0x73), $false) }
[MockTune]::Write($h, 0x6D5EF0, (Str '%s%s' 8), $false); [MockTune]::Write($h, 0x6D5E7C, (Str '%s%s' 8), $false); [MockTune]::Write($h, 0x6D5EA0, (Str '%s%s%s' 8), $false)
[MockTune]::Write($h, 0x644EA5, (B 0x6D5EF0), $false); [MockTune]::Write($h, 0x6451C5, (B 0x6D5E7C), $false); [MockTune]::Write($h, 0x63382B, (B 0x6D5EA0), $false)
[MockTune]::Write($h, $TrackBkgdSite, [byte[]]@(0x44), $false); foreach ($a in $TrackBannerSites) { [MockTune]::Write($h, $a, [byte[]]@(0x52), $false) }
[MockTune]::Write($h, 0x30000100, (New-Object byte[] 64), $false); [MockTune]::Write($h, 0x9DBDB0, (B 0x30000000), $false); [MockTune]::Write($h, 0x30000018, (B 0x30000100), $false)
[MockTune]::Write($h, 0xB2A850, (B 0), $false); [MockTune]::Write($h, 0xA65794, (B 0), $false)
[MockTune]::Write($h, 0x9D6E3C, [byte[]]@(0), $false); [MockTune]::Write($h, 0x9C442C, (B 0), $false); [MockTune]::Write($h, 0x9DBB0C, (B 0), $false)
# the stream header as the game holds it: 25 streams; stream 20 is the Classic slot's music (stereo 32000 Hz, 10649600 bytes,
# its path block at 85792000 in the stream file, no loop). The three pointers are 0 until the script says the header is loaded.
foreach ($a in 0x9C4EC0, 0x9C4EC4, 0x9C4EC8) { [MockTune]::Write($h, $a, (B 0), $false) }
$ta = 0x32000110; $tb = $ta + 200 * 25; $infoOff = 0x110 + 400 * 25
for ($i = 0; $i -lt 25; $i++) {
    [MockTune]::Write($h, $ta + 200 * $i + 0xC0, (B $i), $false); [MockTune]::Write($h, $ta + 200 * $i + 0xC4, (B ($infoOff + 224 * $i)), $false)
    [MockTune]::Write($h, $tb + 200 * $i + 0xC0, (B $i), $false); [MockTune]::Write($h, $tb + 200 * $i + 0xC4, (B (1000000 * $i + 65792000)), $false)
    $info = 0x32000000 + $infoOff + 224 * $i
    foreach ($w in @(@(0xC0, 2), @(0xC4, 32000), @(0xC8, 10649600), @(0xCC, 0), @(0xD0, 0))) { [MockTune]::Write($h, $info + $w[0], (B $w[1]), $false) }
}
[MockTune]::RecB = $tb + 200 * 20; [MockTune]::Info = 0x32000000 + $infoOff + 224 * 20
Install-Cycle $h
[MockTune]::Base = Find-Cycle $h
[MockTune]::Write($h, [MockTune]::Base + 0x226C, (B 4294967295), $false)
# menu flag, entries of the menu on screen, current track (the last one confirmed), View Change held, stream header loaded
[MockTune]::Script.AddRange([string[]]@(
    '0 0 Tropical4 0 0',                                             # attract; the game has not loaded its stream header yet
    '1 3 Tropical4 0 0', '1 3 Tropical4 1 0', '1 3 Tropical4 0 0',   # first menu, one press: Classic will be "Mountain"
    '1 6 Desert4 0 0',                                               # Classic confirmed: Mountain's folder; its tune must wait for the header
    '1 2 Desert4 0 1',                                               # the header is there: stream 20 now points at Mountain's tune
    '0 0 Desert4 0 1',                                               # the race: unchanged
    '0 0 Tropical4 0 1',                                             # the game shows another stage: stream 20 is its own again
    '0 0 Desert4 0 1',                                               # back on the Classic slot, still Mountain: the tune again
    '1 3 Desert4 0 1',                                               # a new game: the slot's own track, the slot's own music
    '1 3 Desert4 1 1', '1 3 Desert4 0 1',                            # -> Mountain: the tune
    '1 3 Desert4 1 1', '1 3 Desert4 0 1',                            # -> Forest (no tune): the slot's own music
    '1 3 Desert4 1 1', '1 3 Desert4 0 1',                            # -> Lake Side (its tune is not in the file): the slot's own music
    '1 3 Desert4 1 1', '1 3 Desert4 0 1',                            # -> back to the slot's own track
    '0 0 Desert4 0 1'))
$script:Logged = New-Object System.Collections.ArrayList
function Log($m) { [void]$script:Logged.Add($m) }
Watch-Tracks (New-Object MockTuneProc) (Join-Path $fake 'Rally.exe')
$script:Logged | ForEach-Object { "log: $_" }
[MockTune]::Out
# what the last lines must say: the game's own values (samples at 85792192, 10649600 bytes, loop start 0, loops 0)
$own = ([MockTune]::U([MockTune]::RecB + 0xC4) -eq 85792000) -and ([MockTune]::U([MockTune]::Info + 0xC8) -eq 10649600) -and ([MockTune]::U([MockTune]::Info + 0xCC) -eq 0) -and ([MockTune]::U([MockTune]::Info + 0xD0) -eq 0)
$others = $true; for ($i = 0; $i -lt 25; $i++) { if ($i -ne 20 -and ([MockTune]::U($tb + 200 * $i + 0xC4) -ne 1000000 * $i + 65792000 -or [MockTune]::U(0x32000000 + $infoOff + 224 * $i + 0xC8) -ne 10649600)) { $others = $false } }
"at the end stream 20 is the game's own again: $own;  every other stream record is untouched: $others"
Remove-Item $fake -Recurse -Force -ErrorAction SilentlyContinue
'@
$tmp = Join-Path $env:TEMP 'sr3_tune_mock.ps1'
Set-Content -LiteralPath $tmp -Value $body -Encoding UTF8
try { & $tmp 'Daytona' -ProfilesFile (Join-Path $PSScriptRoot '..\profiles.yaml') } finally { Remove-Item -LiteralPath $tmp }

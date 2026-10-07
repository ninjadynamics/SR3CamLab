# Runs patch.ps1's alternative-track switcher (Watch-Tracks) against a scripted fake game:
# the menus come and go, View Change is pressed, and the test prints what the game would read.
$src = Get-Content (Join-Path $PSScriptRoot '..\patch.ps1') -Raw
$cut = $src.IndexOf('# ---- launch (unless')
$body = $src.Substring(0, $cut).Replace('[Sr3Mem]::Alloc', '[MockGame]::Alloc').Replace('[Sr3Mem]::Write', '[MockGame]::Write').Replace('[Sr3Mem]::Read', '[MockGame]::Read').Replace('[Sr3Mem]::Open', '[MockGame]::Open').Replace('[Sr3Mem]::Close', '[MockGame]::Close').Replace('. (Join-Path $PSScriptRoot ''setup.ps1'')', ". '" + (Join-Path $PSScriptRoot '..\setup.ps1') + "'").Replace('Start-Sleep -Milliseconds', 'Skip-Sleep')
Add-Type @"
using System; using System.Collections.Generic; using System.Text;
public class MockProc { public int Id = 1; public bool HasExited { get { return MockGame.Step >= MockGame.Script.Count; } } public void WaitForExit() { } }
public static class MockGame {
    public static Dictionary<long, byte> M = new Dictionary<long, byte>();
    public static List<string> Script = new List<string>(), Out = new List<string>();
    public static int Step = 0, NextHandle = 20; public static long Base = 0x20000000;
    static long next = 0x20000000;
    public static long Alloc(IntPtr h, int n) { long a = next; next += 0x10000; for (int i = 0; i < n; i++) M[a + i] = 0; return a; }
    public static IntPtr Open(int pid) { return IntPtr.Zero; }
    public static void Close(IntPtr h) { }
    public static void Sleep(int ms) { }
    public static int I(long a) { return M[a] | (M[a + 1] << 8) | (M[a + 2] << 16) | (M[a + 3] << 24); }
    public static void PutI(long a, int v) { for (int i = 0; i < 4; i++) M[a + i] = (byte)(v >> (8 * i)); }
    public static string S(long a) { var sb = new StringBuilder(); byte b; while (M.TryGetValue(a, out b) && b != 0) { sb.Append((char)b); a++; } return sb.ToString(); }
    public static void PutS(long a, string s) { for (int i = 0; i < s.Length; i++) M[a + i] = (byte)s[i]; M[a + s.Length] = 0; }
    public static void Write(IntPtr h, long va, byte[] b, bool w) {
        for (int i = 0; i < b.Length; i++) M[va + i] = b[i];
        if (va == Base + 0x2264 && b[0] == 1) {                       // the block's request: the game loads every video without a handle
            for (long e = 0x728630; e < 0x728750; e += 16) if (I(e + 12) == -1) { PutI(e + 12, NextHandle++); Out.Add("   game loads video '" + S(I(e + 4)) + "' as #" + (NextHandle - 1)); }
            PutI(Base + 0x2264, 0);
        }
        if (va == Base + 0x2270 && I(va) != 0) {                      // the block's request: a video object plays another file
            int handle = I(va) - 1; string path = S(I(Base + 0x2274));
            PutS(0xAD2F90 + 0x16C * handle + 0xC, path); Out.Add("   game reopens video object #" + handle + " on '" + path + "'");
            PutI(Base + 0x2270, 0);
        }
    }
    public static Dictionary<string, int> Ids = new Dictionary<string, int>();
    static string Card(int handle) { string p = S(0xAD2F90 + 0x16C * handle + 0xC); return p.Substring(p.LastIndexOf('_') + 1); }
    // every look at the menu flag is one tick of the script: "menu count current-track viewchange highlighted-card"
    public static byte[] Read(IntPtr h, long va, int n) {
        if (va == 0x9D6E3C) {
            if (Step > 0) Report();
            if (Step >= Script.Count) return null;
            string[] p = Script[Step++].Split(' ');
            M[0x9D6E3C] = (byte)int.Parse(p[0]); PutI(0x9C442C, int.Parse(p[1])); PutS(0x30000100, p[2]); M[0x9DBB0C] = (byte)(p[3] == "1" ? 0xff : 0);
            PutI(Base + 0x226C, p.Length > 4 && Ids.ContainsKey(p[4]) ? Ids[p[4]] : -1);
        }
        var b = new byte[n]; for (int i = 0; i < n; i++) { byte v; if (!M.TryGetValue(va + i, out v)) return null; b[i] = v; } return b;
    }
    static string last = "";
    static void Report() {
        string popup = I(Base + 0x10) > 0 ? "'" + S(I(Base + 0x50)) + "' / '" + (I(Base + 0x2268) != 0 ? S(I(Base + 0x2268)) : "(built-in hint)") + "'" : "none";
        string s = "tracks dir 'track" + (char)M[0x6C607B] + "' pictures BKG" + (char)M[0x6BCF0F] + "/BANNE" + (char)M[0x6E5A36] + " announcer " + S(I(0x610E10)) + "," + S(I(0x610E3B)) + "," + S(I(0x610E67)) + " sounds " + S(I(0x644EA5)) + "|" + S(I(0x6451C5)) + "|" + S(I(0x63382B)) + " all-visible " + I(0xA65794) + "  cards " + Card(I(0x72871C)) + " " + Card(I(0x72872C)) + " " + Card(I(0x72873C)) + "  popup " + popup;
        Out.Add(String.Format("{0,3} [{1,-26}] {2}", Step, Script[Step - 1], s == last ? "(same)" : s)); last = s;
        if (I(Base + 0x10) > 0) PutI(Base + 0x10, I(Base + 0x10) - 1);   // the block counts the popup's frames down
    }
}
"@
$body += @'

# ---- the fake game ----
function Skip-Sleep($ms) { }
$fake = Join-Path $env:TEMP 'sr3switchtest'; Remove-Item $fake -Recurse -Force -ErrorAction SilentlyContinue
foreach ($d in 'Main_release\tracks\_SR3Extras', 'Main_release\track1\Canyon4', 'Main_release\track2\Canyon4', 'Main_release\track1\Alpine4', 'frontend\PC\Videos') { New-Item -ItemType Directory -Force (Join-Path $fake $d) | Out-Null }
foreach ($v in 'CA1', 'CA2', 'AL1') { Set-Content (Join-Path $fake "frontend\PC\Videos\LANG_ENGLISH_$v.wmv") 'x' }
@{ art = $true; slots = @{ Canyon4 = @{ title = 'Canyon'; speech = 'SP_Canyon'; tracks = @(@{ title = 'Arctic'; dir = '1'; video = 'CA1'; speech = 'SP_SEGARALLYREVO' }, @{ title = 'Safari'; dir = '2'; video = 'CA2'; speech = 'SP_SEGARALLYREVOLUTION'; ambience = 'ID_TRACK_DESERT_2'; music = 'ID_TRACK_DESERT_1'; events = 'ID_TRACK_DESERT_2' }) }
              Alpine4 = @{ title = 'Alpine'; speech = 'SP_Alpine'; tracks = @(@{ title = 'Lakeside'; dir = '1'; video = 'AL1'; speech = 'SP_Lakeside' }, @{ title = 'Gone'; dir = '3'; video = 'AL3' }) } } } |
    ConvertTo-Json -Depth 6 | Set-Content (Join-Path $fake 'Main_release\tracks\_SR3Extras\switch.json')
function B([int]$v) { ,[BitConverter]::GetBytes($v) }
$h = [IntPtr]::Zero
[MockGame]::Write($h, $HookDrawVA, $HookDrawOrig, $false); [MockGame]::Write($h, $HookLostVA, $HookLostOrig, $false)
foreach ($v in $CamUpdateHooks) { [MockGame]::Write($h, $v[0], (B $v[1]), $false) }
foreach ($a in $TrackDirSites) { [MockGame]::Write($h, $a, [byte[]]@(0x73), $false) }
[MockGame]::Write($h, 0x6CF084, (Str 'SP_Tropical' 12), $false); [MockGame]::Write($h, 0x6CF098, (Str 'SP_Alpine' 12), $false); [MockGame]::Write($h, 0x6CF0AC, (Str 'SP_Canyon' 12), $false)
[MockGame]::Write($h, 0x6D5EF0, (Str '%s%s' 8), $false); [MockGame]::Write($h, 0x6D5E7C, (Str '%s%s' 8), $false); [MockGame]::Write($h, 0x6D5EA0, (Str '%s%s%s' 8), $false)
[MockGame]::Write($h, 0x644EA5, (B 0x6D5EF0), $false); [MockGame]::Write($h, 0x6451C5, (B 0x6D5E7C), $false); [MockGame]::Write($h, 0x63382B, (B 0x6D5EA0), $false)
[MockGame]::Write($h, 0x610E10, (B 0x6CF084), $false); [MockGame]::Write($h, 0x610E3B, (B 0x6CF098), $false); [MockGame]::Write($h, 0x610E67, (B 0x6CF0AC), $false)
[MockGame]::Write($h, $TrackBkgdSite, [byte[]]@(0x44), $false); foreach ($a in $TrackBannerSites) { [MockGame]::Write($h, $a, [byte[]]@(0x52), $false) }
# video table: three cards with their names and handles (the game has loaded them), the rest loaded too
for ($e = 0x728630; $e -lt 0x728750; $e += 16) { [MockGame]::Write($h, $e, (B 0x30000400), $false); [MockGame]::Write($h, $e + 4, (B 0x30000400), $false); [MockGame]::Write($h, $e + 8, (B 0), $false); [MockGame]::Write($h, $e + 12, (B (($e - 0x728630) / 16)), $false) }
[MockGame]::PutS(0x30000400, 'other.wmv'); [MockGame]::PutS(0x30000410, 'TRO.wmv'); [MockGame]::PutS(0x30000420, 'ALP.wmv'); [MockGame]::PutS(0x30000430, 'CAN.wmv')
[MockGame]::Write($h, 0x728714, (B 0x30000410), $false); [MockGame]::Write($h, 0x728724, (B 0x30000420), $false); [MockGame]::Write($h, 0x728734, (B 0x30000430), $false)
[MockGame]::Write($h, 0x30000100, (New-Object byte[] 64), $false); [MockGame]::Write($h, 0x9DBDB0, (B 0x30000000), $false); [MockGame]::Write($h, 0x30000018, (B 0x30000100), $false)
foreach ($c in @(@(14, 'TRO'), @(15, 'ALP'), @(16, 'CAN'))) { [MockGame]::Write($h, 0xAD2F90 + 0x16C * $c[0] + 0xC, (New-Object byte[] 256), $false); [MockGame]::PutS(0xAD2F90 + 0x16C * $c[0] + 0xC, ".\frontend\PC\Videos\LANG_ENGLISH_$($c[1]).wmv") }
# the game's track list: [[0xB2A850] + 8] + 8 = first node {next, id, ..., +0x18 -> name}
[MockGame]::Write($h, 0xB2A850, (B 0x31000000), $false); [MockGame]::Write($h, 0x31000008, (B 0x31000100), $false)
$n = 0x31000108; $id = 0x5001
foreach ($t in 'Tropical4', 'Canyon4', 'Alpine4') {
    [MockGame]::Write($h, $n, (New-Object byte[] 0x40), $false); [MockGame]::Write($h, $n + 4, (B $id), $false); [MockGame]::Write($h, $n + 0x18, (B ($n + 0x20)), $false); [MockGame]::PutS($n + 0x20, $t)
    [MockGame]::Ids[$t] = $id; $id += 7
    if ($t -ne 'Alpine4') { [MockGame]::Write($h, $n, (B ($n + 0x100)), $false) }
    $n += 0x100
}
[MockGame]::Write($h, 0xA65794, (B 0), $false)
[MockGame]::Write($h, 0x9D6E3C, [byte[]]@(0), $false); [MockGame]::Write($h, 0x9C442C, (B 0), $false); [MockGame]::Write($h, 0x9DBB0C, (B 0), $false)
Install-Cycle $h
[MockGame]::Base = Find-Cycle $h
[MockGame]::Write($h, [MockGame]::Base + 0x226C, (B -1), $false)
# menu flag, entries of the menu on screen, current track (the last one confirmed), View Change held, highlighted card
[MockGame]::Script.AddRange([string[]]@(
    '0 0 Tropical4 0 -',        # attract
    '1 3 Tropical4 0 -', '1 3 Tropical4 1 -', '1 3 Tropical4 0 -',   # mode menu (3 entries): a press does nothing
    '1 6 Tropical4 0 -', '1 6 Tropical4 1 -', '1 6 Tropical4 0 -',   # car select: a press does nothing
    '1 2 Tropical4 0 -',        # transmission
    '1 3 Tropical4 0 Tropical4',                                     # stage select, Tropical highlighted: no alternatives, no text
    '1 3 Tropical4 0 Canyon4',  # Canyon highlighted: its own track, text shows
    '1 3 Tropical4 1 Canyon4', '1 3 Tropical4 1 Canyon4', '1 3 Tropical4 0 Canyon4',   # one (held) press -> Arctic
    '1 3 Tropical4 1 Canyon4', '1 3 Tropical4 0 Canyon4',            # -> Safari
    '1 3 Tropical4 0 Alpine4',  # Alpine highlighted: its own
    '1 3 Tropical4 1 Alpine4', '1 3 Tropical4 0 Alpine4',            # -> Lakeside
    '1 3 Tropical4 1 Alpine4', '1 3 Tropical4 0 Alpine4',            # -> back to its own (the entry with a missing folder is not offered)
    '1 3 Tropical4 0 Canyon4',  # back on Canyon: still Safari
    '1 3 Canyon4 0 Canyon4',    # confirmed
    '0 3 Canyon4 0 -', '0 0 Canyon4 0 -',                            # the race loads Canyon from track2, with Safari's sounds
    '0 0 Tropical4 0 -',        # later the game shows Tropical (attract): its own folder
    '1 3 Canyon4 0 -',          # a new game: choices forgotten, cards back on their own videos
    '1 6 Canyon4 0 -', '1 2 Canyon4 0 -', '1 3 Canyon4 0 Tropical4', '1 3 Canyon4 0 Canyon4', '0 0 Canyon4 0 -'))
$script:Logged = New-Object System.Collections.ArrayList
function Log($m) { [void]$script:Logged.Add($m) }
Watch-Tracks (New-Object MockProc) (Join-Path $fake 'Rally.exe')
$script:Logged | ForEach-Object { "log: $_" }
[MockGame]::Out
Remove-Item $fake -Recurse -Force -ErrorAction SilentlyContinue
'@
$tmp = Join-Path $env:TEMP 'sr3_switch_mock.ps1'
Set-Content -LiteralPath $tmp -Value $body -Encoding UTF8
try { & $tmp 'Daytona' -ProfilesFile (Join-Path $PSScriptRoot '..\profiles.yaml') } finally { Remove-Item -LiteralPath $tmp }

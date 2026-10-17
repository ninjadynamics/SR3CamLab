<#
  SEGA Rally 3 - SR3CamLab chase camera, in-memory edition
  -----------------------------------------------------------
  Rally.exe on disk is never modified. This script launches the game through
  TeknoParrot as usual, waits until it has finished booting (and TeknoParrot's
  version check has passed), then patches the camera in the game's memory.

    ON  = start the game with PLAY.bat (runs this script)
    TEST = sr3mods.ps1 -Canary: camera looks at the car from the side (proves the patch is live)
    OFF = start the game normally from TeknoParrot. Closing the game undoes everything.

  The camera feel comes from profiles.yaml (next to this script):
      default: Snappy
      profiles:
        Snappy:
          strength: 0.7
          ...
    PLAY.bat                       -> the default profile
    PLAY.bat Drone                 -> the "Drone" profile
    PLAY.bat "SR3 Chase"           -> start on SEGA Rally 3's own chase camera (built in;
                                      "SR3 Chase Far" = its far chase camera)
    -Overlay <px>                  -> size of the camera name popup (0 = off; default: the
                                      file's "overlay:", else 48; pixels at 1080p)
    -MouseSmoothing <seconds>      -> how softly the cameras you steer follow the mouse and keys
                                      (0 = raw; default: the file's "mouseSmoothing:", else 0.08)
    -CameraBlend <seconds>         -> time the view takes to travel to the next camera on View Change
                                      (0 = cut; default: the file's "cameraBlend:", else 0.5)
    -Cores <n>                     -> CPU threads the game may use (default 4; 0 = all). Keeps the
                                      memory its cached videos take low enough to avoid crashes.
    -TpProfile <name>              -> start the game with another TeknoParrot profile this time (setup.yaml's otherwise;
                                      SR3Windowed: 1280x720 in a window, which also starts with the monitor off)
    -NoWatchdog                    -> don't watch the game for crashes and freezes (normally each one
                                      is written to the crash folder as it happens: Start-Watchdog)
    -Setup                         -> open the setup window (where TeknoParrot and the game are;
                                      kept in setup.yaml, found automatically the first time)
  In a race, the game's View Change button cycles through every camera: the game's own
  ("Game:", white: Chase, Bumper, Bonnet), each profile ("CamLab:", lime), then the debug
  cameras the game hides ("Debug:", orange: far chase, cockpit, the cockpit from the driver's
  seat, wheel, car rotate, free cams).
  The name shows for 2 seconds, 14% of the way down the screen (with a mouse/WASD hint on
  the cameras you can steer). The view travels from the old camera to the new one (cameraBlend).
  Car rotate cam: mouse left/right orbits, forward/back tilts, W/S zoom in and out.
  The key below Esc (~) resets the car rotate and free cams. Free cams: mouse looks, WASD moves, Space/Ctrl up/down.
  START in a race: a short press saves a screenshot (..\Screenshots) when you let go, with the
  camera, the car and the track in it (a PNG text chunk "SR3Lab"). VIEW CHANGE held for 1.2
  seconds leaves the race for the game's main menu (Step-Start; it runs in the alternative
  tracks' loop, so with SR3 Extras tracks installed).
    -List                          -> show all profiles
    -ProfilesFile <path>           -> read the profiles from another file (CamLab's Launch
                                      uses this to run unsaved slider values)
  While the game is running, re-running with another profile switches it live.

  Profile values (keys are case-insensitive):
    Strength        0..1   how much the camera follows the direction of travel
                           instead of the car's nose (0 = original SR3 aim)
    FadeInStartKmh  km/h   speed where the effect starts fading in
    FadeInFullKmh   km/h   speed where it is at full strength
    StiffnessMin/Max       camera spring (higher = snappier, lower = floatier)
    Damping                higher = less overshoot, lower = more swing
    MaxAngle        deg    furthest the camera may swing round from straight behind
                           the car (stops it showing the car fully sideways)
    CapStiffness    0..1   how the limit feels: low = resistance builds up early and
                           gently (soft spring), high = firm, 1 = hard wall.
                           The camera moves freely up to MaxAngle x CapStiffness.
    Distance        m      optional framing: how far behind the car the camera sits
    Height          m      optional framing: how high above the car it floats
    Fov             deg    optional framing: lens width. Leave all three out to keep
                           SR3's own framing (the far chase view scales distance/height)
#>
param([string]$CameraProfile = '', [switch]$List, [switch]$NoLaunch, [switch]$Canary, [switch]$Off, [int]$DelaySeconds = 20, [string]$ProfilesFile = '', [int]$Overlay = -1, [int]$Cores = 4, [switch]$Setup,
      [double]$MouseSmoothing = -1, [double]$CameraBlend = -1, [switch]$NoWatchdog, [string]$TpProfile = '')

# Files from a downloaded zip carry Windows' "from the internet" mark, which makes Windows ask
# before running PLAY.bat or camlab.exe. Clear it from SR3CamLab's own files (a no-op after the first run).
Get-ChildItem -LiteralPath $PSScriptRoot -Recurse -File -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue

# where TeknoParrot and the game are (setup.yaml, the setup window)
. (Join-Path $PSScriptRoot 'setup.ps1')

$ErrorActionPreference = 'Stop'

# ---- load the profile ----
# A small, strict reader for the profile file's YAML subset: top-level "default:" and
# "profiles:", one mapping per profile, "key: value" pairs below it, '#' comments.
function Read-ProfilesYaml([string]$path) {
    $profiles = New-Object System.Collections.ArrayList
    $default = ''; $inProfiles = $false; $profIndent = -1; $cur = $null; $top = @{}
    foreach ($raw in [IO.File]::ReadAllLines($path)) {
        $line = ($raw -split '#', 2)[0].TrimEnd()
        if (-not $line.Trim()) { continue }
        $indent = $line.Length - $line.TrimStart(' ').Length
        $body = $line.Trim()
        $i = $body.IndexOf(':')
        if ($i -lt 0) { continue }
        $key = $body.Substring(0, $i).Trim().Trim('"', "'")
        $val = $body.Substring($i + 1).Trim().Trim('"', "'")
        if ($indent -eq 0) {
            $inProfiles = $key -eq 'profiles'
            if ($key -eq 'default') { $default = $val }
            elseif (-not $inProfiles) { $top[$key.ToLower()] = $val }
            $cur = $null
            continue
        }
        if (-not $inProfiles) { continue }
        if ($profIndent -lt 0) { $profIndent = $indent }
        if ($indent -eq $profIndent) { $cur = @{ '_name' = $key }; [void]$profiles.Add($cur) }
        elseif ($cur -and $indent -gt $profIndent) { $cur[$key.ToLower()] = $val }
    }
    return @{ Default = $default; Profiles = $profiles; Top = $top }
}

$YamlPath = if ($ProfilesFile) { $ProfilesFile } else { Join-Path $PSScriptRoot 'profiles.yaml' }
if (-not (Test-Path -LiteralPath $YamlPath)) { throw "Profile file not found: $YamlPath" }
$file = Read-ProfilesYaml $YamlPath
$rows = @($file.Profiles)
if ($rows.Count -eq 0) { throw "$(Split-Path -Leaf $YamlPath) has no profiles." }
$defaultName = if ($file.Default) { $file.Default } else { $rows[0]['_name'] }
if ($List) {
    Write-Host "Profiles in $(Split-Path -Leaf $YamlPath) (* = default):"
    Write-Host ("{0} SR3 Chase      (built in: SEGA Rally 3's own chase camera)" -f $(if ($defaultName -ieq 'SR3 Chase' -or $defaultName -ieq 'Baseline') { '*' } else { ' ' }))
    Write-Host ("{0} SR3 Chase Far  (built in: SEGA Rally 3's own far chase camera)" -f $(if ($defaultName -ieq 'SR3 Chase Far') { '*' } else { ' ' }))
    $rows | ForEach-Object {
        [pscustomobject]@{ Profile = $(if ($_['_name'] -eq $defaultName) { "* " } else { "  " }) + $_['_name']
            Strength = $_['strength']; FadeIn = "$($_['fadeinstartkmh'])-$($_['fadeinfullkmh'])"; Stiffness = "$($_['stiffnessmin'])-$($_['stiffnessmax'])"
            Damping = $_['damping']; MaxAngle = $_['maxangle']; Cap = $_['capstiffness']
            Framing = $(if ($_['distance']) { "$($_['distance']) m / $($_['height']) m / $($_['fov']) deg" } else { 'SR3 default' }) }
    } | Format-Table -AutoSize | Out-String | Write-Host
    return
}
$wanted = if ($CameraProfile) { $CameraProfile } else { $defaultName }
# "Baseline" is built in: SEGA Rally 3's own chase camera. The patch reproduces it exactly:
# no travel follow, the game's raw spring values 15 / 90 with its x7.5 multiplier (112.5 / 675),
# damping 15, no angle limit and the game's own framing.
$BaselineRow = @{ '_name' = 'SR3 Chase'; 'strength' = '0'; 'fadeinstartkmh' = '14'; 'fadeinfullkmh' = '43'; 'stiffnessmin' = '15'; 'stiffnessmax' = '90';
                  'damping' = '15'; 'maxangle' = '180'; 'capstiffness' = '0.25' }
# "SR3 Chase Far" is the game's far chase camera with the same stock settings.
$StartFar = $wanted -ieq 'SR3 Chase Far'
$Baseline = $StartFar -or $wanted -ieq 'SR3 Chase' -or $wanted -ieq 'Baseline'
if ($Baseline) { $row = $BaselineRow }
else { $row = $rows | Where-Object { $_['_name'] -eq $wanted } | Select-Object -First 1 }
if (-not $row) { throw ("Profile '$wanted' not found. Available: " + (($rows | ForEach-Object { $_['_name'] }) -join ', ')) }
$inv = [Globalization.CultureInfo]::InvariantCulture
function Has($name) { return [bool]"$($row[$name.ToLower()])".Trim() }
function Num($name) {
    $v = 0.0
    if (-not [double]::TryParse(("$($row[$name.ToLower()])").Trim(), [Globalization.NumberStyles]::Float, $inv, [ref]$v)) { throw "Profile '$($row['_name'])': '$name' is missing or not a number (use a dot as decimal separator)." }
    return $v
}
$ProfileName    = $row['_name']
$Strength       = Num 'Strength'
$FadeInStartKmh = Num 'FadeInStartKmh'
$FadeInFullKmh  = Num 'FadeInFullKmh'
$StiffnessMin   = Num 'StiffnessMin'
$StiffnessMax   = Num 'StiffnessMax'
$Damping        = Num 'Damping'
$MaxAngleDeg    = if (Has 'MaxAngle') { Num 'MaxAngle' } else { 180 }     # optional: no limit
$CapStiffness   = if (Has 'CapStiffness') { Num 'CapStiffness' } else { 0.4 }
# framing is optional: all three set = override SR3's camera distance/height/field of view
$Framing = (Has 'Distance') -and (Has 'Height') -and (Has 'Fov')
if ($Framing) { $Distance = Num 'Distance'; $Height = Num 'Height'; $Fov = Num 'Fov' }

$CaveVA    = 0x673C80
$TunableLo = 0x08; $TunableHi = 0x24
$DiagLo = 0x34; $DiagHi = 0x50      # canary flag, call counters, runtime scratch (change at runtime)
$LimitOff = 0x54                         # soft angle limit: knee, range, 1/range (radians)
$FramingOff = 0x68                       # framing: flag, distance, height, fov
$DebugLo = 0x80; $DebugHi = 0x8C         # SR3's own framing, recorded every frame (changes at runtime)
$SettingsHi = 0x90                       # end of the settings/data block
$MultOff = 0x50                          # the spring multiplier (1.0; the game's own is 7.5)
$LoadedFlagVA = 0x9EB81C       # game's settings pointer: non-zero once system data is loaded

$Patches = @(
    @{ VA = 0x673C80; Orig = '00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'; New = '53523343010000003333333f000080400000003e00000040000090410000f041000010c1000000000000803f17b7d1380000003f000000000000000000000000000000000000000000000000000000000000803fc3f5484017b7d13800401c46ffffff7f00000080000000000000e04033331340000070420000a03f3333933f00000000000000000000000000000000ff05b83c6700ff742408ff742408e8dde0d8ff83c4088b442404f30f1000f30f1105c43c6700f30f104008f30f1105c83c6700f30f10442430f30f104c24380f28d0f30f59d00f28d9f30f59d9f30f58d3f30f51d20f2f15b03c67000f86b80000000f28daf30f5c1d8c3c6700f30f591d903c6700f30f5f1da43c6700f30f5d1da83c6700f30f5ec2f30f5ecaf30f1020f30f1068080f28f4f30f59f00f28fdf30f59f9f30f58f7f30f5935943c6700f30f5f35a43c6700f30f5d35a83c6700f30f59def30f591d883c6700f30f5cc4f30f59c3f30f58c4f30f5ccdf30f59cbf30f58cd0f28d0f30f59d00f28d9f30f59d9f30f58d3f30f51d20f2f15ac3c67007617f30f5ec2f30f5ecaf30f1100f30f114808ff05bc3c6700833db43c670000741d8b442404f30f1000f30f1048080f57d2f30f5cd1f30f1110f30f1140088b442404f30f1000f30f5905c83c6700f30f104808f30f590dc43c6700f30f5cc1f30f1105c03c6700f30f1000f30f5905c43c6700f30f104808f30f590dc83c6700f30f58c1f30f1105cc3c6700d905c03c6700d905cc3c6700d9f3d91dc03c6700c3ccccccccccccccccccccccccccd9059c3c6700c3ccccccccccccccccccd905983c6700c3ccccccccccccccccccf30f10442408f30f1105003d6700f30f1044240cf30f1105043d6700f30f1081b0030000f30f1105083d6700833de83c6700007461f30f100da83c6700f30f1015a83c67008139b8b86e007510f30f100df83c6700f30f1015fc3c6700f30f1005ec3c6700f30f59c1f30f584130f30f11442408f30f1005f03c6700f30f59c2f30f1144240cf30f1005f43c6700f30f1181b0030000f30f10442404f30f5805c03c67000f2ec07b030f57c0f30f1015e03c67000f28c80f54caf30f101de43c67000f54d80f2f0dd43c6700763df30f5c0dd43c6700f30f590ddc3c67000f28e1f30f59e1f30f5825a83c6700f30f51e4f30f5eccf30f590dd83c6700f30f580dd43c67000f56cb0f28c1f30f11442404e90ae6f7ff'; Desc = 'code cave: tuning constants + hook + stiffness getters'; OrigB = $null; NewB = $null },
    @{ VA = 0x5F72DD; Orig = 'e81eabe0ff'; New = 'e82eca0700'; Desc = 'chase cam: target-direction hook'; OrigB = $null; NewB = $null },
    @{ VA = 0x5F7E29; Orig = 'e8d2a7ffff'; New = 'e8b2c00700'; Desc = 'chase cam: eye placement uses bent heading'; OrigB = $null; NewB = $null },
    @{ VA = 0x5F724D; Orig = 'e4ff6e00'; New = 'd03c6700'; Desc = 'chase cam: stiffness multiplier x7.5 -> cave (1.0)'; OrigB = $null; NewB = $null },
    @{ VA = 0x5F76B0; Orig = '50056f00'; New = 'a03c6700'; Desc = 'chase cam: damping constant -> cave'; OrigB = $null; NewB = $null },
    @{ VA = 0x6EB8A8; Orig = 'c0c45e00'; New = 'c03e6700'; Desc = 'vtable 0x6eb808: max stiffness getter'; OrigB = $null; NewB = $null },
    @{ VA = 0x6EB8AC; Orig = 'b0c45e00'; New = 'd03e6700'; Desc = 'vtable 0x6eb808: min stiffness getter'; OrigB = $null; NewB = $null },
    @{ VA = 0x6EB958; Orig = 'c0c45e00'; New = 'c03e6700'; Desc = 'vtable 0x6eb8b8: max stiffness getter'; OrigB = $null; NewB = $null },
    @{ VA = 0x6EB95C; Orig = 'b0c45e00'; New = 'd03e6700'; Desc = 'vtable 0x6eb8b8: min stiffness getter'; OrigB = $null; NewB = $null }
)

Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class Sr3Mem {
    [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr OpenProcess(int a, bool i, int pid);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, IntPtr n, out IntPtr r);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool WriteProcessMemory(IntPtr h, IntPtr a, byte[] b, IntPtr n, out IntPtr w);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool VirtualProtectEx(IntPtr h, IntPtr a, IntPtr n, uint p, out uint old);
    [DllImport("kernel32.dll", SetLastError=true)] static extern bool FlushInstructionCache(IntPtr h, IntPtr a, IntPtr n);
    [DllImport("ntdll.dll")] static extern int NtSuspendProcess(IntPtr h);
    [DllImport("ntdll.dll")] static extern int NtResumeProcess(IntPtr h);
    public static IntPtr Open(int pid) { IntPtr h = OpenProcess(0x0800 | 0x0400 | 0x0008 | 0x0010 | 0x0020, false, pid); if (h == IntPtr.Zero) throw new Exception("OpenProcess failed: " + Marshal.GetLastWin32Error()); return h; }
    [DllImport("kernel32.dll", SetLastError=true)] static extern IntPtr VirtualAllocEx(IntPtr h, IntPtr a, IntPtr n, uint t, uint p);
    public static long Alloc(IntPtr h, int n) { IntPtr a = VirtualAllocEx(h, IntPtr.Zero, (IntPtr)n, 0x3000, 0x40); if (a == IntPtr.Zero) throw new Exception("VirtualAllocEx failed: " + Marshal.GetLastWin32Error()); return (long)a; }
    public static void Close(IntPtr h) { CloseHandle(h); }
    public static byte[] Read(IntPtr h, long va, int n) { var b = new byte[n]; IntPtr r; if (!ReadProcessMemory(h, (IntPtr)va, b, (IntPtr)n, out r) || (int)r != n) return null; return b; }
    public static void Suspend(IntPtr h) { NtSuspendProcess(h); }
    public static void Resume(IntPtr h) { NtResumeProcess(h); }
    public static void Write(IntPtr h, long va, byte[] b, bool keepWritable) {
        uint old; IntPtr w;
        if (!VirtualProtectEx(h, (IntPtr)va, (IntPtr)b.Length, 0x40, out old)) throw new Exception("VirtualProtectEx failed: " + Marshal.GetLastWin32Error());
        bool ok = WriteProcessMemory(h, (IntPtr)va, b, (IntPtr)b.Length, out w);
        uint dummy; if (!keepWritable) VirtualProtectEx(h, (IntPtr)va, (IntPtr)b.Length, old, out dummy);
        FlushInstructionCache(h, (IntPtr)va, (IntPtr)b.Length);
        if (!ok || (int)w != b.Length) throw new Exception("WriteProcessMemory failed: " + Marshal.GetLastWin32Error());
    }
}
'@

function HexToBytes([string]$h) { $b = New-Object byte[] ($h.Length / 2); for ($i = 0; $i -lt $b.Length; $i++) { $b[$i] = [Convert]::ToByte($h.Substring($i * 2, 2), 16) }; return ,$b }
function Same([byte[]]$a, [byte[]]$b) { if ($null -eq $a -or $a.Length -ne $b.Length) { return $false }; for ($i = 0; $i -lt $a.Length; $i++) { if ($a[$i] -ne $b[$i]) { return $false } }; return $true }
# what this window says is also kept in play.log next to PLAY.bat (the last run only)
$script:PlayLog = Join-Path $PSScriptRoot 'play.log'
try { [IO.File]::WriteAllText($script:PlayLog, '') } catch { $script:PlayLog = $null }
function Log($m) {
    $line = "[{0:HH:mm:ss}] {1}" -f (Get-Date), $m
    Write-Host $line
    if ($script:PlayLog) { try { [IO.File]::AppendAllText($script:PlayLog, $line + "`r`n") } catch { } }
}

# ---- validate tuning and build the patch bytes ----
if ($Strength -lt 0 -or $Strength -gt 1) { throw 'Strength must be between 0 and 1.' }
if ($FadeInStartKmh -lt 0 -or $FadeInFullKmh -le $FadeInStartKmh) { throw 'FadeInFullKmh must be greater than FadeInStartKmh (both >= 0).' }
if ($StiffnessMin -le 0 -or $StiffnessMax -lt $StiffnessMin -or $StiffnessMax -gt 500) { throw 'Need 0 < StiffnessMin <= StiffnessMax <= 500.' }
if ($Damping -le 0 -or $Damping -gt 100) { throw 'Damping must be between 0 and 100.' }
if ($MaxAngleDeg -lt 1 -or $MaxAngleDeg -gt 180) { throw 'MaxAngle must be between 1 and 180 degrees.' }
if ($CapStiffness -lt 0 -or $CapStiffness -gt 1) { throw 'CapStiffness must be between 0 and 1.' }
if ($MaxAngleDeg -ge 180) { $Knee = [Math]::PI; $Range = 1e-4 }   # no limit
else { $m = $MaxAngleDeg * [Math]::PI / 180; $Knee = $CapStiffness * $m; $Range = [Math]::Max($m - $Knee, 1e-4) }
if ($Framing) {
    if ($Distance -lt 1 -or $Distance -gt 30) { throw 'Distance must be between 1 and 30 m.' }
    if ($Height -lt 0 -or $Height -gt 15) { throw 'Height must be between 0 and 15 m.' }
    if ($Fov -lt 20 -or $Fov -gt 120) { throw 'Fov must be between 20 and 120 degrees.' }
}
# The cave's settings for one profile (validated); $stock = the game's x7.5 spring multiplier.
function Get-CaveImage($r, [bool]$stock) {
    $script:row = $r
    $S = Num 'Strength'; $F0 = Num 'FadeInStartKmh'; $F1 = Num 'FadeInFullKmh'
    $K0 = Num 'StiffnessMin'; $K1 = Num 'StiffnessMax'; $Dm = Num 'Damping'
    $MA = if (Has 'MaxAngle') { Num 'MaxAngle' } else { 180 }
    $CS = if (Has 'CapStiffness') { Num 'CapStiffness' } else { 0.4 }
    $Fr = (Has 'Distance') -and (Has 'Height') -and (Has 'Fov')
    $n = $r['_name']
    if ($S -lt 0 -or $S -gt 1) { throw "${n}: Strength must be between 0 and 1." }
    if ($F0 -lt 0 -or $F1 -le $F0) { throw "${n}: FadeInFullKmh must be greater than FadeInStartKmh (both >= 0)." }
    if ($K0 -le 0 -or $K1 -lt $K0 -or $K1 -gt 500) { throw "${n}: need 0 < StiffnessMin <= StiffnessMax <= 500." }
    if ($Dm -le 0 -or $Dm -gt 100) { throw "${n}: Damping must be between 0 and 100." }
    if ($MA -lt 1 -or $MA -gt 180) { throw "${n}: MaxAngle must be between 1 and 180 degrees." }
    if ($CS -lt 0 -or $CS -gt 1) { throw "${n}: CapStiffness must be between 0 and 1." }
    if ($MA -ge 180) { $kn = [Math]::PI; $rg = 1e-4 }
    else { $m = $MA * [Math]::PI / 180; $kn = $CS * $m; $rg = [Math]::Max($m - $kn, 1e-4) }
    $b = HexToBytes $Patches[0].New
    $v = @($S, ($F0 / 3.6), (1.0 / (($F1 - $F0) / 3.6)), 2.0, $K0, $K1, -$Dm)
    for ($i = 0; $i -lt $v.Count; $i++) { [Array]::Copy([BitConverter]::GetBytes([single]$v[$i]), 0, $b, $TunableLo + $i * 4, 4) }
    $lim = @($kn, $rg, (1.0 / $rg))
    for ($i = 0; $i -lt 3; $i++) { [Array]::Copy([BitConverter]::GetBytes([single]$lim[$i]), 0, $b, $LimitOff + $i * 4, 4) }
    [Array]::Copy([BitConverter]::GetBytes([int]$Fr), 0, $b, $FramingOff, 4)
    if ($Fr) {
        $fv = @((Num 'Distance'), (Num 'Height'), (Num 'Fov'))
        if ($fv[0] -lt 1 -or $fv[0] -gt 30 -or $fv[1] -lt 0 -or $fv[1] -gt 15 -or $fv[2] -lt 20 -or $fv[2] -gt 120) { throw "${n}: framing out of range (distance 1-30 m, height 0-15 m, fov 20-120)." }
        for ($i = 0; $i -lt 3; $i++) { [Array]::Copy([BitConverter]::GetBytes([single]$fv[$i]), 0, $b, $FramingOff + 4 + $i * 4, 4) }
    }
    if ($stock) { [Array]::Copy([BitConverter]::GetBytes([single]7.5), 0, $b, $MultOff, 4) }
    return ,$b
}
foreach ($p in $Patches) {
    $p.OrigB = HexToBytes $p.Orig; $p.NewB = HexToBytes $p.New
    if ($p.VA -eq $CaveVA) {
        $p.NewB = Get-CaveImage $row $Baseline
        $script:row = $row
        if ($Canary) { $p.NewB[$DiagLo] = 1 }
    }
}

# ---- the camera cycle: the game's cameras, the hidden ones, then every profile ----
# A block of code and data allocated in the game (see build_cycle.py): every frame it keeps the
# race camera list extended with our chase slots, loads the selected slot's settings into the
# cave and draws the camera name with a D3DX font for 2 seconds after a change.
$CycleCode = '9c60e8000000005d81ed0710000083bd64220000007411c7856422000000000000b800166200ffd083c8ff833d480f9c0000741a6a17b9fc536e00b8d0705400ffd083c40489c7b890646000ffd089856c22000083c8ff833d480f9c0000741a6a16b9145e6e00b8d0705400ffd083c40489c7b890646000ffd089857822000083c8ff833d480f9c0000740cbf4ae0ac6eb810656000ffd089857c2200008b857022000085c00f84d10000004883f8140f83bd0000005069f86c01000081c7902fad00837f0400746c8b872001000085c074068b0850ff5124bb2c0100008b041f85c0740dc7041f000000008b0850ff510883eb0481fb1c01000073e18b874401000085c07410c78744010000000000008b0850ff5108c7873001000000000000c70700000000c7470400000000c74708000000008b8d7422000055b880dc4d00ffd05d85c074288b87200100008b0850ff511c85c07c06c707000000008b04246a016a0050b870e34d00ffd083c40c83c404c78570220000000000008b35ecb49e0085f60f844003000083c61881be1005000008b86e000f852d0300008dbe1005000039be340200000f851b0300008b862c0200003b452875093975580f849e01000083f8010f82fe020000c7855c2200000000000083f8150f87eb02000031c931d239c173288b9c8e3402000039fb741a83fa0c731539755875083b95bc0000007308899c95802100004241ebd439755874098995bc00000089455c89956022000031c983f90c735d8b9c8de021000083fbff745185db782b01f3833b0074215131c939d1730c399c8d80210000741041ebf083fa0c7308899c9580210000425941ebc081e3ffffff7f01f3833b0074f083fa0c73eb899c95802100004289955c220000ebdb8b4d208d1c1183fb150f873402000083bd5c22000000740749018d5c22000089552c89755889be34020000bb0100000031c93b8d6022000073128b848d8021000089849e340200004341ebe6b9010000003b4d20730b89bc9e340200004341ebf08b8d6022000039d173128b848d8021000089849e340200004341ebea899e2c020000895d288b85a80f000085c074054839d8722e8b452483f8fe751c8d8ec408000031c039d8730c398c8634020000741140ebf031c0eb0a85c07406038560220000898630020000c7451cffffffffc785b0000000010000008b86300200003b451c0f845a0100008b4d1c83f9ff74358d51013b5528720231d239d074278b948634020000399690010000750d8b948e34020000899690010000898e30020000e91d0100003b862c0200000f831101000089451c8d4801898da80f00008b8c863402000029f131d281f9ec0e0000741081f9780c0000740881f9681d00007501428995a00f0000e8bf01000031c985c074093b8560220000760141890d9457a60085c074173b8560220000762d89c12b8d602200003b4d20732089c8e80b0200008b8c85000e0000898d600e0000c1e0058d840500010000eb668b9c8634020000813bb8b86e0075095031c0e8db0100005829f33b855c220000750681cb000000808d85e0000000c785600e0000ffffffff31c983f90c7327399c8db0210000751b8b848d102200008985600e000089c8c1e0058d840500200000eb0341ebd48945508b8db0000000c785b00000000000000085c9750b8b4514894510e802150000e816030000837d10000f8ed2000000ff4d108b451885c00f8ec4000000f72578db7e00b938040000f7f183f8087d05b808000000508d5d08e8720100005985c00f849400000089c351a178db7e00b90e000000f7e1b964000000f7f18985b40000008b45508985a40f00008b04248b8d600e0000e8bb0100005883bda00f000000745e506bc00b31d2b90a000000f7f10185b400000058d1e883f8087d05b808000000508d9d980f0000e8000100005985c0742d89c38b956822000085d275068d95b00f00008995a40f000089c8b9e0e0e0ffe85c010000eb07c7451000000000619da10cd17e00c3608dbe381a0000813ff0bd6e0075708d95402200008b9d5c22000085db744c39d875488b8f9401000039d1745285c9744e898d582200008b01350000008089028b41048942048b41088942088b410c350000008089420c8b41108942108b4114894214899794010000eb14399794010000750c8b8d58220000898f9401000061c3565751526bd05c8db41500050000bf883c6700b90b000000f3a5bfd03c6700b90c000000f3a5833de83c67000075118b555885d2740ac782c0080000000070425a595f5ec33b430475038b03c3508b0b85c9740c518b11ff5208c70300000000588943048b555485d275228d4d6051ff15f441670085c074418d4d705150ff150442670085c0743289455489c2538d8d80000000516a006a046a006a016a006a0168bc0200006a00ff7304ff350cd17e00ffd285c07c038b03c3c70300000000c743040000000031c0c35131d2b916000000f7f185c075014089c76bc00731d2b90a000000f7f185c07501408985b800000089f9f7d931d2e86200000089f931d2e85900000031c989faf7dae84e00000031c989fae8450000008b8db800000089cae8380000008b8db800000089caf7dae8290000008b8db800000089caf7d9e81a0000008b8db8000000f7d989cae80b00000031c931d258e806000000c3b8000000d056898da00000008bb5b400000001d689b5a40000008b3574db7e0001ce89b5a80000008b3578db7e0001d689b5ac000000506a218db5a0000000566affffb5a40f00006a00538b33ff56385ec38b35ecb49e0085f6742a83c6188bbe900100008d86ec0e000039c774168d86780c000039c7740c8d86681d000039c77402eb01c38b35ecb49e0085f60f846f04000083c61881be1005000008b86e000f855c0400008bbe900100008d86ec0e0000bb0100000039c774288d86780c0000bb0200000039c774198d86681d000039c7740fc785300f000001000000e91f04000083bd8c0e0000000f85f60000008d8da00e000051ff15f441670085c00f84fd03000089c2528d8db00e00005152ff15044267005a8985800e0000528d8dc00e00005152ff15044267005a8985840e0000528d8dd00e00005152ff15044267005a8985880e0000528d8d400f00005152ff15044267005a8985900e00008d8d600f00005251ff15f44167005a85c0745b8d8d700f0000525150ff15044267005a8985940e00008d8df00e00005152ff150442670089858c0e000083bd800e000000742883bd840e000000741f83bd880e000000741683bd900e000000740d83bd940e000000740485c07519c7858c0e000000000000c785300f000002000000e91c030000ff958c0e00008d8d380f0000c701000000005150ff95900e0000ff95940e00003b85380f0000740fc785300f000003000000e9e5020000c785300f000004000000c785340f000000000000a174db7e00d1e88985280f0000a178db7e00d1e889852c0f00008d8d700e000051ff95800e000031c08985200f00008985240f000083bd680e00000075248b85700e00002b85280f00008985200f00008b85740e00002b852c0f00008985240f0000c785680e000000000000ffb52c0f0000ffb5280f0000ff95840e0000c785640e00000100000068c0000000ff95880e00005068dc000000ff95880e00005909c825008000008b8dd80f00008985d80f000085c0741085c9750c89f98b07ff5004e8170f0000f30f2a85200f0000f30f2a8d240f0000e87c0e0000f30f5985100f0000f30f598d100f000083fb010f8510010000f30f108dac220000f30f598dd00f0000f30f10160f57db0f2fd3761ef30f10daf30f599d140f0000f30f5ec3f30f5995180f0000f30f5ecaeb060f57c00f57c9f30f1186a8010000f30f118eb80100006a536a57e8df0100008d85a4220000e8520e0000f30f1186ac0100000f57c0f30f1186bc010000f30f10160f57db0f2fd30f8688000000f30f5995180f00008b860c05000085c07476f30f1086ac010000f30f59c2f30f584720f30f5800f30f5f85e00f0000f30f5d85e40f0000f30f5c00f30f5c4720f30f5ec2f30f1186ac010000f30f1086b8010000f30f59c2f30f584748f30f584004f30f5f85e80f0000f30f5d85ec0f0000f30f5c4004f30f5c4748f30f5ec2f30f1186b8010000c3f30f1097300200000f57db0f2fd3760af30f5ec2f30f5ecaeb12f30f59851c0f0000f30f598d1c0f0000eb30f30f10d9f30f59daf30f589f68020000f30f5d9d900f0000f30f5f9d940f0000f30f5c9f68020000f30f5edaf30f10cbf30f1186a8010000f30f118eac0100000f57c0f30f1186c40100006a576a53e8a80000008d8598220000e81b0d0000f30f1186b00100006a446a41e88c0000008d859c220000e8ff0c0000f30f1186b40100006a206a11e8700000008d85a0220000e8e30c0000f30f1186b8010000c3c785680e00000100000083bd640e0000007448c785640e000000000000e8eb0c00008b755885f6743231c08986a80100008986ac0100008986b00100008986b40100008986b80100008986bc0100008986c00100008986c4010000c35331dbff74240cff95880e0000660985340f000066a90080740143ff742408ff95880e000066a9008074014bf30f2ac35bc208009c60e8000000005d81ed2e1d0000e8e0faffff619d68001e5f00c39c60e8000000005d81ed491d0000e8c5faffff619d68e03f5f00c39c60e8000000005d81ed641d00008b4d0885c97414518b11ff5208c7450800000000c7450c000000008b8d980f000085c9741a518b11ff5208c785980f000000000000c7859c0f000000000000619d6820125900c3'
$CycleSize = 0x4000; $CycleDraw = 0x1000; $CycleLost = 0x1d5d; $CycleRot = 0x1d27; $CycleFree = 0x1d42
# the block's second code area (constants, then code): the smoothing of the steerable cameras and the blend between cameras
$CycleCode2 = '0000803f000040400000803ecdcccc3dbd3786350000803d0000000000000000ffffffffffffffffffffffff000000005175657279506572666f726d616e6365436f756e746572005175657279506572666f726d616e63654672657175656e63790000000000000000000000000000000000803f000000000000803f00000000000000000000803f00000000000000000000803f00000000000080bf00000000f30f1095002800000f57db0f2f1873427a40f30f10260f2fe376370f2fa508280000772ed906d830d9e0d9eadec9d9c0d9fcdce9d9c9d9f0d9e8dec1d9fdddd9d9e8dee1d99db4220000f30f1095b4220000c3f30f58000f28d8f30f59c2f30f5cd80f28e3f30f59e40f2fa5102800007307f30f58c30f57dbf30f1118c38d8584220000e877fffffff30f1195b02200008d8580220000e864ffffff8d8590220000e8acfffffff30f1185a82200000f28c18d8594220000e896fffffff30f1185ac2200000f28c8f30f1085a8220000c3f30f1095b02200000f28e8f30f5c00f30f59c2f30f58000f28ddf30f5cd8f30f59db0f2f9d1028000073030f28c5f30f1100c35031c089859022000089859422000089859822000089859c2200008985a02200008985a422000058c3508b86300200008b8486340200003b85f022000074128985e8220000c785ec2200007800000058c3c785e422000001000000c785e82200000000000058c30f28da0fc6db55f30f58da0f12d2f30f58d3c30f5cc80f59ce0f58c1c35331dbf30f1000f30f59049af30f104804f30f594c9a04f30f58c1f30f104808f30f594c9a08f30f58c1f30f11041983c30483fb0c72cc5bc35331dbf30f1000f30f59041af30f104804f30f594c1a10f30f58c1f30f104808f30f594c1a20f30f58c1f30f11041983c30483fb0c72cc5bc3c785d82200000000000083bdb82200000075528d85600f000050ff15f441670085c00f84bd00000089c78d8d482800005157ff150442670085c00f84a50000008d8dc022000051ffd08d8d302800005157ff150442670085c00f84860000008985b82200008d85c822000050ff95b82200008b85c82200008b95cc2200008b8dd02200008b9dd42200008985d02200008995d422000089cf09df744929c819da753785c078338985c8220000db85c8220000dfadc0220000def9d99dd8220000f30f1085d8220000f30f5d850c280000f30f1185d8220000c38b850c2800008985d8220000c3a1ecb49e0085c00f84fe04000083c01839f00f85f3040000a110ce7e003b0514ce7e00750a83f827741283f81c740d833d00b89d00000f84cf0400000f57c90f2f8d882200000f83a50400000f8a9f040000e8c3feffff83bdb8220000000f848d0400008bbe8401000085ff0f847f04000089f98b07ff505c89c38b96c801000085d20f846804000081c25c1300000f10bd202800003bbdf0220000741d89bdf02200003bbde8220000745ac785e022000000000000e9c300000083bde422000000754283bde8220000007412ff8dec2200007f0ac785e82200000000000083bde0220000000f8492000000f30f1085dc220000f30f5885d8220000f30f1185dc220000eb78c785e422000000000000c785e82200000000000083bdf422000000745b31c90f10140a0f54d70f59d2e857fdfffff30f5c9500280000f30f59d20f2f951428000077357a3383c11083f93072d256578db5002300008dbd40230000b910000000f3a55f5ec785dc22000000000000c785e0220000010000000f10020f1185803f00000f1042100f1185903f00000f1042200f1185a03f00000f108250edffff0f54c70f1185b03f00008d95803f00000f10020f54c70f104a100f54cf0f58c10f104a200f54cf0f58c10f104a300f54cf0f58c10f57c90f59c10f28d0e8a4fcffff0f2ed10f8a010300000f1042200f54c70f5985702800000f28d00f59d2e882fcffff0f2f95102800000f86db020000f30f51d20fc6d2000f5ec20f1185e02700000f108d802800000f118dd02700000f28c80fc6c9c60f598d902800000f10120f54d70f59d1e839fcffff0f57db0f2fd373060f5cd90f28cb0f118dc02700000f1042300f1185f02700008d95c02700000f1043300f54c70f1185802300000f104b6c0f54cf0f5cc80f28d10f59d2e8f0fbffff0f2f95102800000f8649020000f30f51d2f30f1195b02300000fc6d2000f5eca0f118d902300000f1083200100000f54c70f1185a02300008b83780100008985b423000083bde0220000000f8497010000f30f10b5dc220000f30f5eb5882200000f2fb5002800000f83700100000f28c6f30f58c0f30f108d04280000f30f5cc8f30f59cef30f59f10fc6f6008d85402300008d8dd0230000e8a8fbffff0f1085d02300000f54c70f104a300f54cf0f58c10f108d80230000e845fbffff0f1185802300008d8550230000e876fbffff0f1085d02300000f54c70f108d90230000e81dfbffff0f28d00f59d2e8fffaffff0f2f95102800007612f30f51d20fc6d2000f5ec20f1185902300008d8560230000e82ffbffff0f1085d02300000f54c70f108da0230000e8d6faffff0f1185a02300000f1085702300000f108db0230000e8bcfaffff0f1385b0230000f30f1085b02300000fc6c0000f108d902300000f59c80f1085802300000f58c80f118dc02300000f1095a02300000f58d10f58d0e869fafffff30f5895b42300000f57dbf30f59d30f2ed30f8ab70000000f1343300f12c0f30f1143380f134b6c0f12c9f30f114b740f1085a02300000f1383200100000f12c0f30f1183280100008b85b4230000898378010000eb0ac785e0220000000000000f1085802300000f104a300f54cf0f5cc10f1185d02300008d85d02300008d8d00230000e8fcf9ffff8d85902300008d8d10230000e8ebf9ffff8d85a02300008d8d20230000e8daf9ffff8b85b02300008985302300008b85b4230000898534230000c785f422000001000000c331c08985f42200008985e02200008985e42200008985e8220000c3ff742404b890165f00ffd09c60e8000000005d81ed9e300000e8d6faffff619dc20400'
$CycleCode2At = 0x2800; $CycleBlend = 0x308c
$CycleQol = 0x2280                                                # mouse smoothing, key smoothing, blend time (3 floats, seconds; 0 = off)
$CycleMaxSlots = 21; $CycleSlotBytes = 0x5C
$HookDrawVA = 0x591C4D; $HookDrawOrig = HexToBytes 'a10cd17e00'   # mov eax,[device] before EndScene/Present
$HookLostVA = 0x591B01; $HookLostOrig = HexToBytes 'e81af7ffff'   # call 0x591220 (frees resources before Reset)
# call 0x5F1690 (esi = camera manager, one float): once per drawn frame it works out, from the cameras' last two updates,
# the state the view is built from. The block's wrapper calls it, then blends that state (see build_cycle.py). Read in the
# disassembly and run against the game's own code on an emulated CPU (tools\cycle_real.py, 2026-10-14), not yet in the
# running game; when the bytes there are not these, the blend is left out and View Change cuts as before.
$HookBlendVA = 0x5C948C; $HookBlendOrig = HexToBytes 'e8ff810200'
# the update method (vtable slot 3) of the cameras the mouse and keys steer: our wrappers write
# their inputs just before they run (the game clears them earlier in the frame)
$CamUpdateHooks = @(@(0x6EBB3C, 0x5F1E00, 'rot'), @(0x6ECBA4, 0x5F3FE0, 'free'), @(0x6ECC94, 0x5F3FE0, 'free'))
# The game's own cameras (offset in the camera manager, official name from the game). A race
# normally offers Chase, Bumper and Bonnet; the rest are hidden in the game and added after them.
# 0x80000000 + offset adds that camera again, patched: the cockpit cam from the driver's seat.
$White = 0xFFFFFFFF; $Orange = 0xFFFF9A2E; $Lime = 0xFF9CFF3A                   # Game / Debug / CamLab (ARGB; PowerShell reads these as negative Int32, which is the right bits)
$GameCams = @(@(0x1700, 'Game: Bumper cam', $White), @(0x189C, 'Game: Bonnet cam', $White), @(0x8C4, 'Debug: Chase cam far', $Orange),
              @(0x1A38, 'Debug: Cockpit cam', $Orange), @(0x80001A38, 'Debug: Cockpit cam (patched)', $Orange),
              @(0x1BD0, 'Debug: Wheel cam', $Orange), @(0xEEC, 'Debug: Car rotate cam', $Orange),
              @(0xC78, 'Debug: Free cam', $Orange), @(0x1D68, 'Debug: Car free cam', $Orange))
$HiddenCams = @(0x8C4, 0x1A38, 0x80001A38, 0x1BD0, 0xEEC, 0xC78, 0x1D68)
$CycleGameCams = 12                                                     # block+0x2000: names, then list, offsets, extras, colours
$CockpitSeat = 0x2240                                                   # block+0x2240: driver-seat eye/look copy, +0x18 the game's pointer

$showHidden = -not ("$($file.Top['hiddencameras'])".Trim() -match '^(false|no|off|0)$')   # hiddenCameras: true (default) / false
$startRow = $row
$slots = New-Object System.Collections.ArrayList
[void]$slots.Add(@{ Name = 'Game: Chase cam'; Profile = 'SR3 Chase'; Color = $White; Image = (Get-CaveImage $BaselineRow $true) })
foreach ($r in $rows) {
    if ($r['_name'] -ieq 'Baseline' -or $r['_name'] -ieq 'SR3 Chase' -or $r['_name'] -ieq 'SR3 Chase Far') { continue }
    if ($slots.Count -ge $CycleMaxSlots - 2 - $(if ($showHidden) { $HiddenCams.Count } else { 0 })) {   # the list also holds Bumper, Bonnet and the debug cameras
        Log "Too many profiles for the camera cycle; '$($r['_name'])' is left out."; continue }
    try { [void]$slots.Add(@{ Name = "CamLab: $($r['_name'])"; Profile = $r['_name']; Color = $Lime; Image = (Get-CaveImage $r $false) }) }
    catch { Log "Profile '$($r['_name'])' is left out of the camera cycle: $($_.Exception.Message)" }
}
$script:row = $startRow
$startSlot = 0
for ($i = 0; $i -lt $slots.Count; $i++) { if ($slots[$i].Profile -eq $startRow['_name']) { $startSlot = $i } }
if ($StartFar) { $startSlot = -2 }                       # the block finds the far chase cam in the list
$overlayPx = 48
if ($file.Top['overlay']) { $tmp = 0; if ([int]::TryParse($file.Top['overlay'], [ref]$tmp)) { $overlayPx = $tmp } }
if ($Overlay -ge 0) { $overlayPx = $Overlay }
$overlayPx = [Math]::Max(0, [Math]::Min(200, $overlayPx))
# Two more settings of the file's top level, in seconds (a switch of the same name wins; missing or not a number = the
# default; "off" = 0). CamLab's Launch file does not carry them: then the ones of profiles.yaml next to this script count.
#   mouseSmoothing: time constant of the steerable cameras' mouse look (car rotate, free cams): after this long the
#                   camera has made up 63% of a mouse movement. 0 = raw, as before. Their keys get twice this.
#   cameraBlend:    how long the view takes from the old camera to the new one on View Change. 0 = cut, as before.
$ownTop = $null
function Get-Seconds([string]$key, [double]$fromSwitch, [double]$default, [double]$max) {
    $v = $default; $t = "$($file.Top[$key.ToLower()])".Trim()
    if (-not $t -and $ProfilesFile) {
        if ($null -eq $script:ownTop) { $own = Join-Path $PSScriptRoot 'profiles.yaml'; $script:ownTop = if (Test-Path -LiteralPath $own) { (Read-ProfilesYaml $own).Top } else { @{} } }
        $t = "$($script:ownTop[$key.ToLower()])".Trim()
    }
    $n = 0.0
    if ($t -match '^(off|false|no)$') { $v = 0.0 }
    elseif ($t -and [double]::TryParse($t, [Globalization.NumberStyles]::Float, $inv, [ref]$n) -and -not [double]::IsNaN($n)) { $v = $n }
    if ($fromSwitch -ge 0) { $v = $fromSwitch }
    return [Math]::Max(0.0, [Math]::Min($max, $v))
}
$lookSmooth = Get-Seconds 'mouseSmoothing' $MouseSmoothing 0.08 1.0
$blendSec = Get-Seconds 'cameraBlend' $CameraBlend 0.5 3.0

function Put([byte[]]$buf, [int]$off, [byte[]]$src) { [Array]::Copy($src, 0, $buf, $off, $src.Length) }
function Str([string]$t, [int]$n) { $b = New-Object byte[] $n; $a = [Text.Encoding]::ASCII.GetBytes($t); [Array]::Copy($a, 0, $b, 0, [Math]::Min($a.Length, $n - 1)); return ,$b }
function CallTo([long]$from, [long]$to) { $b = New-Object byte[] 5; $b[0] = 0xE8; [Array]::Copy([BitConverter]::GetBytes([int]($to - ($from + 5))), 0, $b, 1, 4); return ,$b }
function Find-Cycle($h) {
    $b = [Sr3Mem]::Read($h, $HookDrawVA, 5)
    if (-not $b -or $b[0] -ne 0xE8) { return 0 }
    $base = $HookDrawVA + 5 + [BitConverter]::ToInt32($b, 1) - $CycleDraw
    $m = [Sr3Mem]::Read($h, $base, 4)
    if ($m -and [Text.Encoding]::ASCII.GetString($m) -eq 'SR3V') { return $base }
    return 0
}
# installs or updates the block; call with the game suspended
function Install-Cycle($h) {
    $code = HexToBytes $CycleCode; $code2 = HexToBytes $CycleCode2
    $base = Find-Cycle $h
    if (-not $base) {
        if (-not (Same ([Sr3Mem]::Read($h, $HookDrawVA, 5)) $HookDrawOrig) -or -not (Same ([Sr3Mem]::Read($h, $HookLostVA, 5)) $HookLostOrig)) {
            Log 'Camera cycle not installed: unexpected bytes at its hook sites.'; return
        }
        $base = [Sr3Mem]::Alloc($h, $CycleSize)
        [Sr3Mem]::Write($h, $base + $CycleDraw, $code, $true)
        [Sr3Mem]::Write($h, $base + $CycleCode2At, $code2, $true)
    }
    elseif (-not (Same ([Sr3Mem]::Read($h, $base + $CycleDraw, $code.Length)) $code) -or -not (Same ([Sr3Mem]::Read($h, $base + $CycleCode2At, $code2.Length)) $code2)) {
        # a newer build: never rewrite code the game may be running; move to a fresh block,
        # keeping the state (font, camera list) and leaving the old one as it is
        $old = $base
        Restore-CockpitSeat $h $old
        $base = [Sr3Mem]::Alloc($h, $CycleSize)
        [Sr3Mem]::Write($h, $base, ([Sr3Mem]::Read($h, $old, $CycleDraw)), $true)
        [Sr3Mem]::Write($h, $base + 0xF98, (New-Object byte[] 0x10), $true)   # hint font, hint flag, text: start empty
        [Sr3Mem]::Write($h, $base + 0x2180, ([Sr3Mem]::Read($h, $old + 0x2180, 4 * $CycleGameCams)), $true)   # the game's list entries
        [Sr3Mem]::Write($h, $base + $CycleDraw, $code, $true)
        [Sr3Mem]::Write($h, $base + $CycleCode2At, $code2, $true)              # its state (0x2280 ..) starts empty: nothing outstanding, no blend
    }
    $qol = New-Object byte[] 12                                        # 0x2280: seconds; the keys of a steerable camera get twice the mouse's time:
    Put $qol 0 ([BitConverter]::GetBytes([single]$lookSmooth))          # they are all or nothing, the mouse is not (a guess to be judged in the game)
    Put $qol 4 ([BitConverter]::GetBytes([single](2 * $lookSmooth))); Put $qol 8 ([BitConverter]::GetBytes([single]$blendSec))
    [Sr3Mem]::Write($h, $base + $CycleQol, $qol, $true)
    $settings = New-Object byte[] 0x18                                 # 0x14..0x2C
    Put $settings 0x00 ([BitConverter]::GetBytes([int]120))             # frames shown (2 s at 60 fps)
    Put $settings 0x04 ([BitConverter]::GetBytes([int]$overlayPx))
    Put $settings 0x08 ([BitConverter]::GetBytes([int]-1))              # last index: re-apply
    Put $settings 0x0C ([BitConverter]::GetBytes([int]$slots.Count))
    Put $settings 0x10 ([BitConverter]::GetBytes([int]$startSlot))
    Put $settings 0x14 ([BitConverter]::GetBytes([int]0))               # extended count: re-extend
    [Sr3Mem]::Write($h, $base + 0x14, $settings, $true)
    [Sr3Mem]::Write($h, $base + 0xB0, ([BitConverter]::GetBytes([int]1)), $true)   # quiet: no popup for this
    $strings = New-Object byte[] 0x40
    Put $strings 0x00 (Str 'd3dx9_41.dll' 16); Put $strings 0x10 (Str 'D3DXCreateFontA' 16); Put $strings 0x20 (Str 'Arial' 32)
    [Sr3Mem]::Write($h, $base + 0x60, $strings, $true)
    [Sr3Mem]::Write($h, $base, ([Text.Encoding]::ASCII.GetBytes('SR3V')), $true)
    [Sr3Mem]::Write($h, $base + 0xE0, (Str 'Camera' 16), $true)        # 0xE0: name of an unknown camera
    $gc = New-Object byte[] 0x240                                      # 0x2000: names, 0x21B0: offsets, 0x21E0: extras, 0x2210: colours
    for ($i = 0; $i -lt $CycleGameCams; $i++) {
        $known = $i -lt $GameCams.Count
        if ($known) { Put $gc ($i * 32) (Str $GameCams[$i][1] 32); Put $gc (0x210 + 4 * $i) ([BitConverter]::GetBytes([int]$GameCams[$i][2])) }
        Put $gc (0x1B0 + 4 * $i) ([BitConverter]::GetBytes([int]$(if ($known) { $GameCams[$i][0] } else { -1 })))
        Put $gc (0x1E0 + 4 * $i) ([BitConverter]::GetBytes([int]$(if ($showHidden -and $i -lt $HiddenCams.Count) { $HiddenCams[$i] } else { -1 })))
    }
    [Sr3Mem]::Write($h, $base + 0x2000, $gc[0..0x17F], $true)
    [Sr3Mem]::Write($h, $base + 0x21B0, $gc[0x1B0..0x23F], $true)
    $scol = New-Object byte[] ($CycleMaxSlots * 4)                     # 0xE00: colour per slot
    for ($i = 0; $i -lt $slots.Count; $i++) { Put $scol ($i * 4) ([BitConverter]::GetBytes([int]$slots[$i].Color)) }
    [Sr3Mem]::Write($h, $base + 0xE00, $scol, $true)
    $u = New-Object byte[] 0x70                                        # 0xEA0: user32 functions for the free-cam controls
    Put $u 0x00 (Str 'user32.dll' 16); Put $u 0x10 (Str 'GetCursorPos' 16); Put $u 0x20 (Str 'SetCursorPos' 16)
    Put $u 0x30 (Str 'GetAsyncKeyState' 32); Put $u 0x50 (Str 'GetForegroundWindow' 32)
    [Sr3Mem]::Write($h, $base + 0xEA0, $u, $true)
    $u2 = New-Object byte[] 0x50                                       # 0xF40: to check the game is in front
    Put $u2 0x00 (Str 'GetWindowThreadProcessId' 32); Put $u2 0x20 (Str 'kernel32.dll' 16); Put $u2 0x30 (Str 'GetCurrentProcessId' 32)
    [Sr3Mem]::Write($h, $base + 0xF40, $u2, $true)
    [Sr3Mem]::Write($h, $base + 0xFD0, ([BitConverter]::GetBytes([single]-0.01)), $true)   # car rotate tilt per mouse pixel
    $pitch = New-Object byte[] 8                                       # 0xF90: free cams look at most this far up / down (rad, just under 90 deg)
    Put $pitch 0 ([BitConverter]::GetBytes([single]1.5706)); Put $pitch 4 ([BitConverter]::GetBytes([single]-1.5706))
    [Sr3Mem]::Write($h, $base + 0xF90, $pitch, $true)
    $rot = New-Object byte[] 16                                        # 0xFE0: car rotate cam limits: distance, height (m)
    Put $rot 0 ([BitConverter]::GetBytes([single]3)); Put $rot 4 ([BitConverter]::GetBytes([single]30))
    Put $rot 8 ([BitConverter]::GetBytes([single]0.5)); Put $rot 12 ([BitConverter]::GetBytes([single]20))
    [Sr3Mem]::Write($h, $base + 0xFE0, $rot, $true)
    [Sr3Mem]::Write($h, $base + 0xFB0, (Str 'Use mouse/WASD to navigate' 32), $true)   # 0xFB0: the hint under a steerable camera's name
    $k = New-Object byte[] 0x10                                        # 0xF10: mouse radians per pixel, the game's rates
    Put $k 0x0 ([BitConverter]::GetBytes([single]0.0025)); Put $k 0x4 ([BitConverter]::GetBytes([single]([Math]::PI / 2)))
    Put $k 0x8 ([BitConverter]::GetBytes([single]10)); Put $k 0xC ([BitConverter]::GetBytes([single]1))
    [Sr3Mem]::Write($h, $base + 0xF10, $k, $true)
    $names = New-Object byte[] ($CycleMaxSlots * 32); $params = New-Object byte[] ($CycleMaxSlots * $CycleSlotBytes)
    for ($i = 0; $i -lt $slots.Count; $i++) {
        Put $names ($i * 32) (Str $slots[$i].Name 32)
        [Array]::Copy($slots[$i].Image, 0x08, $params, $i * $CycleSlotBytes, 0x2C)
        [Array]::Copy($slots[$i].Image, 0x50, $params, $i * $CycleSlotBytes + 0x2C, 0x30)
    }
    [Sr3Mem]::Write($h, $base + 0x100, $names, $true)
    [Sr3Mem]::Write($h, $base + 0x500, $params, $true)
    foreach ($v in $CamUpdateHooks) {                                  # the original method, or a wrapper of ours
        $cur = [BitConverter]::ToUInt32([Sr3Mem]::Read($h, $v[0], 4), 0)
        $sig = [Sr3Mem]::Read($h, ($cur -band 0xFFFF0000), 4)               # our blocks start on a 64 KB boundary with "SR3V"
        $ours = $sig -and [Text.Encoding]::ASCII.GetString($sig) -eq 'SR3V'
        if ($cur -eq $v[1] -or $ours) {
            $to = $base + $(if ($v[2] -eq 'rot') { $CycleRot } else { $CycleFree })
            [Sr3Mem]::Write($h, $v[0], ([BitConverter]::GetBytes([int]$to)), $false)
        }
    }
    [Sr3Mem]::Write($h, $HookLostVA, (CallTo $HookLostVA ($base + $CycleLost)), $false)
    [Sr3Mem]::Write($h, $HookDrawVA, (CallTo $HookDrawVA ($base + $CycleDraw)), $false)
    # the blend's hook, only while there is a blend to do: with cameraBlend 0 the game's own call stays (or comes back)
    $site = Test-BlendSite $h; $script:BlendHooked = $site -and $blendSec -gt 0
    if ($script:BlendHooked) { [Sr3Mem]::Write($h, $HookBlendVA, (CallTo $HookBlendVA ($base + $CycleBlend)), $false) }
    elseif ($site) { [Sr3Mem]::Write($h, $HookBlendVA, $HookBlendOrig, $false) }
    else { Log ('Camera blend not installed (View Change cuts as before): unexpected bytes at 0x{0:X}.' -f $HookBlendVA) }
}
# The blend's hook site holds the game's own call, or a call into a block of ours (they start on a 64 KB boundary with "SR3V")
function Test-BlendSite($h) {
    $cur = [Sr3Mem]::Read($h, $HookBlendVA, 5)
    if (Same $cur $HookBlendOrig) { return $true }
    if (-not $cur -or $cur[0] -ne 0xE8) { return $false }
    $to = [uint32](([long]$HookBlendVA + 5 + [BitConverter]::ToInt32($cur, 1)) -band 4294967295)
    $sig = [Sr3Mem]::Read($h, ($to -band 0xFFFF0000), 4)
    return [bool]($sig -and [Text.Encoding]::ASCII.GetString($sig) -eq 'SR3V')
}
# unhooks the block and puts the game's camera list back; call with the game suspended
# Points the cockpit cam's eye back at the game's data if it uses this block's driver-seat copy.
function Restore-CockpitSeat($h, $base) {
    $mgr = [BitConverter]::ToUInt32([Sr3Mem]::Read($h, $base + 0x58, 4), 0)
    if (-not $mgr) { return }
    $cam = $mgr + 0x1A38; $vt = [Sr3Mem]::Read($h, $cam, 4); $p = [Sr3Mem]::Read($h, $cam + 0x194, 4)
    if ($vt -and $p -and [BitConverter]::ToUInt32($vt, 0) -eq 0x6EBDF0 -and [BitConverter]::ToUInt32($p, 0) -eq $base + $CockpitSeat) {
        [Sr3Mem]::Write($h, $cam + 0x194, ([Sr3Mem]::Read($h, $base + $CockpitSeat + 0x18, 4)), $false)
    }
}
function Remove-Cycle($h) {
    $base = Find-Cycle $h
    if (-not $base) { return }
    Restore-CockpitSeat $h $base
    [Sr3Mem]::Write($h, 0xA65794, ([BitConverter]::GetBytes([int]0)), $false)   # the game's visibility (PVS) back on
    if (Test-BlendSite $h) { [Sr3Mem]::Write($h, $HookBlendVA, $HookBlendOrig, $false) }   # only over a call of ours (or the game's own, which changes nothing)
    [Sr3Mem]::Write($h, $HookDrawVA, $HookDrawOrig, $false)
    [Sr3Mem]::Write($h, $HookLostVA, $HookLostOrig, $false)
    foreach ($v in $CamUpdateHooks) { [Sr3Mem]::Write($h, $v[0], ([BitConverter]::GetBytes([int]$v[1])), $false) }
    $st = [Sr3Mem]::Read($h, $base + 0x2180 - 4, 4 + 4 * $CycleGameCams)  # the list entries the block found
    $mgr = [BitConverter]::ToUInt32([Sr3Mem]::Read($h, $base + 0x58, 4), 0); $n = [BitConverter]::ToInt32([Sr3Mem]::Read($h, $base + 0xBC, 4), 0)   # the game's own entries
    if ($mgr -and $n -ge 0 -and $n -le $CycleGameCams) {
        $hdr = [Sr3Mem]::Read($h, $mgr + 0x510, 4); $first = [Sr3Mem]::Read($h, $mgr + 0x234, 4)
        if ($hdr -and [BitConverter]::ToUInt32($hdr, 0) -eq 0x6EB808 -and $first -and [BitConverter]::ToUInt32($first, 0) -eq $mgr + 0x510) {
            $list = New-Object byte[] (12 + 4 * $n)
            Put $list 0 ([BitConverter]::GetBytes([int](1 + $n))); Put $list 8 ([BitConverter]::GetBytes([int]($mgr + 0x510)))
            for ($i = 0; $i -lt $n; $i++) { [Array]::Copy($st, 4 + 4 * $i, $list, 12 + 4 * $i, 4) }
            [Sr3Mem]::Write($h, $mgr + 0x22C, $list, $false)
        }
    }
}

# ---- after the game ----
# Leaving the game sometimes leaves a modifier key (usually Alt) "held" in Windows, because
# the key-up never arrived. When this script started the game, it waits for it to close and
# then sends key-ups for Alt, Ctrl, Shift and Win, which clears any that are stuck.
Add-Type -Namespace SR3 -Name Keys -MemberDefinition '[DllImport("user32.dll")] public static extern void keybd_event(byte vk, byte scan, uint flags, UIntPtr extra);'
# ---- alternative tracks (SR3 Extras) ----
# SR3 Extras can give a stage card more tracks than the game's own: their files sit next to the
# game's (Main_release\track1\<slot>, track2\<slot>...; stage card videos LANG_<language>_<code>.wmv)
# and tracks\_SR3Extras\switch.json lists them. While the game runs, this watches the stage-select
# screen: View Change steps the highlighted card through its tracks. Nothing is patched for good;
# the game is pointed at the chosen files by rewriting a few names in its memory:
#   the "tracks" in its track path patterns (6 places) -> "track1"...: follows the current track
#   the card's video: the game has no room for more videos than its own (20 objects, 18 used), so
#   the card's own video object is closed and opened again on the other file (tools\build_cycle.py)
#   the announcer's clip for the card, said when the card is highlighted: the routine's pointer to
#   the clip's name ("SP_Canyon") is turned to another name, kept in the camera block
#   the sounds of the race (ambience, music, the file of ambience and reverb zones along the route): the game makes their names
#   from the track's sound id with "%s%s" patterns; the routines' pointers to those patterns are
#   turned to whole names kept in the camera block ("SFX_AMBIENT_ID_TRACK_DESERT_2")
#   scenery visibility: all of it counts as visible while an added track is raced ([0xA65794])
#   when switch.json says "art": the name patterns of the banner and background pictures, to the
#   second set of names SR3 Extras added to the menu pictures file ("BKG1_NAME_%s", "MENU_BANNE1_%s")
# Game facts: [0x9D6E3C] = 1 while the menus are up; [0x9C442C] = number of entries of the menu on
# screen (cars 6, transmission 2, stages 3); [[0x9DBDB0] + 0x18] = name of the current track (the
# last one confirmed, not the highlighted card); the highlighted card: the camera block asks the
# stage selector every frame and leaves the track's id at block + 0x226C (-1 = no selector);
# tracks: a list of nodes from [[0xB2A850] + 8] + 8, {next, id, ..., +0x18 -> name};
# [0x9DBB0C] != 0 while View Change is held; video table: see tools\build_cycle.py.
$TrackDirSites = 0x6C607B, 0x6C60A3, 0x6D57C3, 0x6E034F, 0x6E03A3, 0x6E055B     # the 's' of "tracks"
# The folder is chosen inside the game's own path code (tools\build_trackdir.py, test tools\trackdir_emu.py): the three
# routines that make a track's paths start with a jump to a routine of ours, which looks the track being read up in a
# table (track -> folder character) and writes that character into the strings above just before the path is made. The
# launcher only keeps the table current. Before, the launcher wrote the strings when its poll saw the track change, which
# was sometimes after the game had begun reading: a load of half one folder and half another crashed the game
# (2026-10-14, 0x5AF329). Without the routine (unexpected bytes) the poll writes the strings as before.
$TrackDirCode = '9c60e8000000005d83ed07a1b0bd9d0085c074738b701885f6746cb2738dbd000200008b0f83f9107605b91000000083c70485c974275657bb170000008a063a07751284c0740746474b7409ebef5f5e8a5718eb085f5e83c72049ebd588157b606c008815a3606c008815c3576d0088154f036e008815a3036e0088155b056e008895f0010000619dc3e871ffffffa1b0bd9d0068955c5c00c3e861ffffff81ec180100006876575c00c3e850ffffff81ec0001000068b6b36100c3'
$TrackDirHooks = @(@(0x5C5C90, 'a1b0bd9d00', 0x8A), @(0x5C5770, '81ec18010000', 0x9A), @(0x61B3B0, '81ec00010000', 0xAB))   # site, the game's bytes, entry
$TrackDirTable = 0x200
function Install-TrackDir($h) {
    try {
        $first = [Sr3Mem]::Read($h, $TrackDirHooks[0][0], 5)
        if ($first -and $first[0] -eq 0xE9) {                     # PLAY.bat run again on a running game: ours already
            $cave = $TrackDirHooks[0][0] + 5 + [BitConverter]::ToInt32($first, 1) - $TrackDirHooks[0][2]
            if (Same ([Sr3Mem]::Read($h, $cave, 8)) ((HexToBytes $TrackDirCode)[0..7])) { return $cave }
            Log 'Track folders: the path code holds a jump that is not ours; folders are switched by polling.'; return $null
        }
        foreach ($k in $TrackDirHooks) { if (-not (Same ([Sr3Mem]::Read($h, $k[0], $k[1].Length / 2)) (HexToBytes $k[1]))) { Log ("Track folders: unexpected bytes at 0x{0:X}; folders are switched by polling." -f $k[0]); return $null } }
        $cave = [Sr3Mem]::Alloc($h, 0x1000); [Sr3Mem]::Write($h, $cave, (HexToBytes $TrackDirCode), $true)
        [Sr3Mem]::Write($h, $cave + $TrackDirTable, (New-Object byte[] 4), $true)
        foreach ($a in $TrackDirSites) { [Sr3Mem]::Write($h, $a, [byte[]]@([byte][char]'s'), $true) }   # (and the strings stay writable for the routine)
        [Sr3Mem]::Suspend($h)
        try {
            foreach ($k in $TrackDirHooks) {
                $j = CallTo $k[0] ($cave + $k[2]); $j[0] = 0xE9
                if ($k[1].Length / 2 -gt 5) { $j = $j + [byte[]]@(0x90) }
                [Sr3Mem]::Write($h, $k[0], $j, $false)
            }
        } finally { [Sr3Mem]::Resume($h) }
        return $cave
    } catch { Log "Track folders: $($_.Exception.Message); folders are switched by polling."; return $null }
}
# the table: every slot with alternatives and the folder character of its chosen track ('s' = the game's own)
function Write-TrackDirTable($h, [long]$cave, $slots, $choice) {
    $b = New-Object byte[] (4 + 0x20 * 16); $n = 0
    foreach ($s in @($slots.Keys | Sort-Object)) {
        if ($n -ge 16) { break }
        $nm = [Text.Encoding]::ASCII.GetBytes([string]$s); if ($nm.Length -gt 23) { continue }
        [Array]::Copy($nm, 0, $b, 4 + 0x20 * $n, $nm.Length)
        $b[4 + 0x20 * $n + 0x18] = [byte][char]([string]$slots[$s][$choice[$s]].Dir)[0]; $n++
    }
    [Array]::Copy([BitConverter]::GetBytes([int]$n), 0, $b, 0, 4)
    if (-not (Same $b $script:TrackDirLast)) { [Sr3Mem]::Write($h, $cave + $TrackDirTable, $b, $true); $script:TrackDirLast = $b }
}
$TrackBkgdSite = 0x6BCF0F                                                        # the 'D' of "BKGD_NAME_%s"
$TrackBannerSites = 0x6BD79E, 0x6D96E6, 0x6E2AB2, 0x6E336E, 0x6E5A36            # the last 'R' of "MENU_BANNER_%s"
# the announcer's clip for a card: "push <name>" in the routine at 0x610DC0 (address of the pointer, the game's own name)
$TrackSpeechSite = @{ Tropical4 = @(0x610E10, 0x6CF084); Alpine4 = @(0x610E3B, 0x6CF098); Canyon4 = @(0x610E67, 0x6CF0AC) }
$TrackSpeechText = @{ Tropical4 = 0x2600; Alpine4 = 0x2640; Canyon4 = 0x2680 }           # room for the other names, in the camera block
# race sounds: address of the pointer to the pattern, the game's own pattern, room in the camera block, the whole name
$TrackSoundSites = @(@{ Site = 0x644EA5; Own = 0x6D5EF0; Text = 0x2700; Kind = 'Ambience'; Name = 'SFX_AMBIENT_{0}' },
                     @{ Site = 0x6451C5; Own = 0x6D5E7C; Text = 0x2740; Kind = 'Music'; Name = 'MU_RACE_{0}' },
                     @{ Site = 0x63382B; Own = 0x6D5EA0; Text = 0x2780; Kind = 'Events'; Name = '\Audio\{0}_Events.bin' })
$ClassicSlot = 'Desert4'                                                            # the track of the Classic mode
$TrackVideoEntry = @{ Tropical4 = 0x728710; Alpine4 = 0x728720; Canyon4 = 0x728730; Desert4 = 0x728650 }   # Desert4 (the Classic slot): the mode menu's Classic card, MENUSLIDE_CLASSIC (classic.wmv)
$SwitchTextOff = 0x2400                                                          # free room in the camera block
function Read-TrackSwitch([string]$gameExe) {
    if (-not $gameExe) { return $null }
    $dir = Split-Path -Parent $gameExe
    $file = Join-Path $dir 'Main_release\tracks\_SR3Extras\switch.json'
    if (-not (Test-Path -LiteralPath $file)) { return $null }
    try { $j = [IO.File]::ReadAllText($file) | ConvertFrom-Json } catch { Log "Alternative tracks: $file can't be read; ignoring it."; return $null }
    $slots = [ordered]@{}                                            # (in switch.json's order: pc_live.c goes through them the same way)
    foreach ($p in $j.slots.PSObject.Properties) {
        $list = New-Object System.Collections.ArrayList
        [void]$list.Add(@{ Title = "$($p.Value.title)"; Dir = 's'; Video = ''; Speech = "$($p.Value.speech)"; Ambience = ''; Music = ''; Events = ''; Tune = $null })   # 0 = the game's own track
        foreach ($a in @($p.Value.tracks)) {
            $d = "$($a.dir)"
            if ($d -notmatch '^[1-9]$') { continue }
            if (-not (Test-Path -LiteralPath (Join-Path $dir "Main_release\track$d\$($p.Name)"))) { Log "Alternative tracks: $($a.title) is listed but Main_release\track$d\$($p.Name) is missing; skipped."; continue }
            $video = "$($a.video)"
            # stage cards are LANG_<language>_<video>.wmv, the Classic card classic_<video>.wmv
            if ($video -and @(Get-ChildItem -LiteralPath (Join-Path $dir 'frontend\PC\Videos') -Filter "*_$video.wmv" -ErrorAction SilentlyContinue).Count -lt 1) { $video = '' }
            $snd = @{}; foreach ($k in 'ambience', 'music', 'events') { $snd[$k] = if ("$($a.$k)" -match '^ID_TRACK_[A-Z]{1,12}_[0-9]$') { "$($a.$k)" } else { '' } }
            # a tune of its own, appended to the game's stream file by SR3 Extras (Set-CourseTune): only when it really is there
            $tune = $null; $t = $a.tune
            if ($t -and "$($t.stream)" -match '^\d{1,4}$' -and "$($t.offset)" -match '^\d{3,10}$' -and "$($t.bytes)" -match '^\d{3,10}$' -and "$($t.loopstart)" -match '^\d{1,10}$') {
                $tune = @{ Stream = [int]"$($t.stream)"; Offset = [long]"$($t.offset)"; Bytes = [long]"$($t.bytes)"; LoopStart = [long]"$($t.loopstart)"; Loop = 1 }
                $df = Join-Path $dir 'Audio\EnglishStreamData.stm'
                if (($tune.Bytes % 4) -or ($tune.LoopStart % 4) -or $tune.LoopStart -ge $tune.Bytes -or -not (Test-Path -LiteralPath $df) -or ($tune.Offset + 0xC0 + $tune.Bytes) -gt (Get-Item -LiteralPath $df).Length -or ($tune.Offset + 0xC0 + $tune.Bytes) -gt 0x7FFFFFFF) {
                    Log "Alternative tracks: the tune of $($a.title) is not in the game's sound file; it plays its slot's own music."; $tune = $null
                }
            }
            [void]$list.Add(@{ Title = "$($a.title)"; Dir = $d; Video = $video; Speech = "$($a.speech)"; Ambience = $snd.ambience; Music = $snd.music; Events = $snd.events; Tune = $tune })
        }
        if ($list.Count -gt 1) { $slots[$p.Name] = $list }
    }
    if ($slots.Count -eq 0) { return $null }
    $script:CardVideo = @{}
    $script:TrackArt = [bool]$j.art
    return $slots
}
function Read-GameString($h, [long]$va, [int]$max) {
    $b = [Sr3Mem]::Read($h, $va, $max)
    if (-not $b) { return '' }
    $n = [Array]::IndexOf($b, [byte]0); if ($n -lt 0) { $n = $max }
    return [Text.Encoding]::ASCII.GetString($b, 0, $n)
}
function Read-GameInt($h, [long]$va) { $b = [Sr3Mem]::Read($h, $va, 4); if ($b) { return [BitConverter]::ToInt32($b, 0) }; return 0 }
# id -> name of the game's tracks
function Read-TrackNames($h) {
    $map = @{}
    $p = Read-GameInt $h 0xB2A850; if (-not $p) { return $map }
    $p = Read-GameInt $h ($p + 8); if (-not $p) { return $map }
    $n = $p + 8
    for ($i = 0; $i -lt 64 -and $n; $i++) {
        $s = Read-GameInt $h ($n + 0x18)
        if ($s) { $map[(Read-GameInt $h ($n + 4))] = Read-GameString $h $s 24 }
        $n = Read-GameInt $h $n
    }
    return $map
}
# Finds each card's video object and the file it plays; the alternatives' files are next to it.
function Initialize-TrackVideos($h, [long]$base, $slots) {
    $script:CardVideo = @{}
    foreach ($slot in @($slots.Keys)) {
        $entry = $TrackVideoEntry[$slot]
        if (-not $entry) { continue }
        $own = Read-GameInt $h ($entry + 12)
        if ($own -eq -1) {                                         # the game hasn't loaded its videos yet: have it do so now
            [Sr3Mem]::Write($h, $base + 0x2264, ([BitConverter]::GetBytes([int]1)), $true)
            for ($i = 0; $i -lt 400 -and (Read-GameInt $h ($entry + 12)) -eq -1; $i++) { Start-Sleep -Milliseconds 25 }
            $own = Read-GameInt $h ($entry + 12)
        }
        if ($own -lt 0 -or $own -ge 20) { Log "Alternative tracks: the game didn't load the card video of $slot; the card keeps its own picture."; continue }
        $path = Read-GameString $h (0xAD2F90 + 0x16C * $own + 0xC) 255
        if ($path -notmatch '\\[A-Za-z0-9_]+\.wmv$') { Log "Alternative tracks: the card video of $slot isn't where expected; the card keeps its own picture."; continue }
        $script:CardVideo[$slot] = @{ Handle = $own; Path = $path }
        $slots[$slot][0].Path = $path
        for ($k = 1; $k -lt $slots[$slot].Count; $k++) {
            $alt = $slots[$slot][$k]
            # LANG_ENGLISH_TRO.wmv -> LANG_ENGLISH_TR1.wmv (video "TR1"); classic.wmv (no underscore) -> classic_MTN.wmv (video "MTN")
            $alt.Path = if (-not $alt.Video) { $path } elseif ($path -match '_[A-Za-z0-9]+\.wmv$') { $path -replace '_[A-Za-z0-9]+\.wmv$', "_$($alt.Video).wmv" } else { $path -replace '\.wmv$', "_$($alt.Video).wmv" }        }
    }
}
# Points a card at one of its tracks: the card's video and the announcer's clip.
function Set-CardTrack($h, [long]$base, [string]$slot, $track, [bool]$own) {
    $v = $script:CardVideo[$slot]
    if ($v -and $track.Path -and $track.Path -ne $v.Path) {          # the card's video object plays the other file
        [Sr3Mem]::Write($h, $base + 0x2500, (Str $track.Path 256), $true)
        [Sr3Mem]::Write($h, $base + 0x2274, ([BitConverter]::GetBytes([int]($base + 0x2500))), $true)
        [Sr3Mem]::Write($h, $base + 0x2270, ([BitConverter]::GetBytes([int]($v.Handle + 1))), $true)
        for ($i = 0; $i -lt 300 -and (Read-GameInt $h ($base + 0x2270)) -ne 0; $i++) { Start-Sleep -Milliseconds 10 }
        $v.Path = $track.Path
    }
    $site = $TrackSpeechSite[$slot]
    if ($site) {
        $name = $site[1]                                              # the game's own name
        if (-not $own -and $track.Speech -match '^SP_[A-Za-z0-9_]{1,40}$') {
            $name = $base + $TrackSpeechText[$slot]
            [Sr3Mem]::Write($h, $name, (Str $track.Speech 48), $true)
        }
        [Sr3Mem]::Write($h, $site[0], ([BitConverter]::GetBytes([int]$name)), $true)
    }
}
# A track's own tune. SR3 Extras can append tunes to the game's stream file (Audio\EnglishStreamData.stm) after SEGA's own
# streams, where nothing of the game points. A track that has one (switch.json, "tune") gets it by turning the stream record
# of its slot's music, in the game's memory only: where the samples are, how many bytes, where the loop starts, that it loops.
# With any other track the record is the game's own again, so nothing else ever plays such a tune. Game facts (stream open
# 0x5686F0, stream read 0x5681C0): [0x9C4EC0] = the loaded stream header, [0x9C4EC4] and [0x9C4EC8] = its two tables of
# 200-byte records {path[192], index, value}; value = offset of the stream's info record in the header / offset of its
# 192-byte path block in the stream file (the samples follow). Info record: +0xC0 channels, +0xC4 rate, +0xC8 bytes,
# +0xCC loop start in bytes (at the end of a looping stream the read position becomes this), +0xD0 loops. The game reads all
# of it when a stream is opened and when it runs out, so a change made in the menus holds for the next race.
$StreamHeader = 0x9C4EC0
$script:TuneOwn = $null
function Read-GamePtr($h, [long]$va) { $b = [Sr3Mem]::Read($h, $va, 4); if ($b) { return [long][BitConverter]::ToUInt32($b, 0) }; return [long]0 }
function Write-GameInt($h, [long]$va, [long]$v) { [Sr3Mem]::Write($h, $va, ([BitConverter]::GetBytes([uint32]$v)), $true) }
# $tune = @{ Stream; Offset; Bytes; LoopStart; Loop }, or $null for the game's own. Returns $false while the header is not loaded.
function Set-CourseTune($h, $tune) {
    if (-not $tune -and -not $script:TuneOwn) { return $true }
    $hdr = Read-GamePtr $h $StreamHeader; $ta = Read-GamePtr $h ($StreamHeader + 4); $tb = Read-GamePtr $h ($StreamHeader + 8)
    if (-not $hdr -or -not $ta -or -not $tb) { return $false }
    $o = $script:TuneOwn
    if ($o -and (-not $tune -or $tune.Stream -ne $o.Stream)) {      # the game's own values back
        Write-GameInt $h ($o.Rb + 0xC4) $o.Offset; Write-GameInt $h ($o.Info + 0xC8) $o.Bytes; Write-GameInt $h ($o.Info + 0xCC) $o.LoopStart; Write-GameInt $h ($o.Info + 0xD0) $o.Loop
        $script:TuneOwn = $null
    }
    if (-not $tune) { return $true }
    $ra = $ta + 200 * $tune.Stream; $rb = $tb + 200 * $tune.Stream
    $info = $hdr + (Read-GamePtr $h ($ra + 0xC4))
    if ((Read-GamePtr $h ($ra + 0xC0)) -ne $tune.Stream -or (Read-GamePtr $h ($rb + 0xC0)) -ne $tune.Stream -or (Read-GamePtr $h ($info + 0xC0)) -ne 2 -or (Read-GamePtr $h ($info + 0xC4)) -ne 32000) {
        Log "A track's own tune: stream $($tune.Stream) is not the stereo 32000 Hz stream expected; the slot's own music plays."; return $true
    }
    if (-not $script:TuneOwn) {
        $script:TuneOwn = @{ Stream = $tune.Stream; Rb = $rb; Info = $info; Offset = (Read-GamePtr $h ($rb + 0xC4)); Bytes = (Read-GamePtr $h ($info + 0xC8)); LoopStart = (Read-GamePtr $h ($info + 0xCC)); Loop = (Read-GamePtr $h ($info + 0xD0)) }
    }
    Write-GameInt $h ($rb + 0xC4) $tune.Offset; Write-GameInt $h ($info + 0xC8) $tune.Bytes; Write-GameInt $h ($info + 0xCC) $tune.LoopStart; Write-GameInt $h ($info + 0xD0) $tune.Loop
    return $true
}
# Checkpoint times. The seconds every checkpoint marker grants live in the game's ArcadeDatabase, one block of 0xC60 bytes
# per track ([[0xB2A850] + 0xC] + 4 + 0xC60 x track; reader 0x661AA0, called at 0x5ABDF8 whenever a marker is crossed). An
# added track with its own checkpoints brings arcade_times.bin (that block) in its folder; it is written into the loaded
# table while the track is chosen and SEGA's block is put back when another one is. The file on disk is never touched.
$script:ArcadeOrig = @{}
function Set-ArcadeTimes($h, [string]$gameDir, [string]$slot, [string]$dir) {
    $index = @{ Tropical4 = 0; Canyon4 = 1; Alpine4 = 2; Lakeside4 = 3; Desert4 = 4; Stadium4 = 5 }
    foreach ($s in @($script:ArcadeOrig.Keys)) {
        $o = $script:ArcadeOrig[$s]; [Sr3Mem]::Write($h, $o.At, $o.Bytes, $true); $script:ArcadeOrig.Remove($s)
    }
    if ($dir -eq 's' -or -not $index.ContainsKey($slot)) { return }
    $file = Join-Path $gameDir "Main_release\track$dir\$slot\arcade_times.bin"
    if (-not (Test-Path -LiteralPath $file)) { return }
    $new = [IO.File]::ReadAllBytes($file)
    $p = Read-GameInt $h 0xB2A850; $tab = if ($p) { Read-GameInt $h ($p + 0xC) } else { 0 }
    if ($new.Length -ne 0xC60 -or -not $tab) { Log "Checkpoint times: $file not used (size $($new.Length), table $tab)."; return }
    $at = [long]$tab + 4 + 0xC60 * $index[$slot]
    $old = [Sr3Mem]::Read($h, $at, 0xC60); if ($null -eq $old) { return }
    $script:ArcadeOrig[$slot] = @{ At = $at; Bytes = $old }
    [Sr3Mem]::Write($h, $at, $new, $true)
    Log "Checkpoint times: $slot uses the times of Main_release\track$dir\$slot."
}
# Car shadows. The game's dynamic shadows are variance shadow maps; the pixel shaders read gfShadowParamsPs from four floats at
# 0x9F1068 (set once at start-up by 0x594570): +4 = the smallest variance allowed (1/512), +8 = the power the result is raised
# to (10). A smaller variance floor and a higher power give a harder edge. An added track may bring shadow.txt in its folder
# ("<variance floor> <power>", e.g. "0.0002 30": the 1995 courses want a hard shadow under the car); it is written while that
# track is chosen and the game's own two values are put back when another one is.
# A third word "noblur" also skips the 5 x 5 Gaussian blur the game runs over a render target after one of its passes (the
# only call of 0x50D960, at 0x5A5467; LIKELY the shadow map - the two numbers alone changed nothing visible, in-game run
# 2026-10-08). The call is replaced by five NOPs while the track is chosen and put back afterwards.
$script:ShadowOrig = $null; $script:ShadowBlurOff = $false
$ShadowBlurVA = 0x5A5467; $ShadowBlurOrig = [byte[]]@(0xE8, 0xF4, 0x84, 0xF6, 0xFF)
function Set-ShadowParams($h, [string]$gameDir, [string]$slot, [string]$dir) {
    if ($script:ShadowOrig) { [Sr3Mem]::Write($h, 0x9F106C, $script:ShadowOrig, $true); $script:ShadowOrig = $null }
    if ($script:ShadowBlurOff) { [Sr3Mem]::Write($h, $ShadowBlurVA, $ShadowBlurOrig, $false); $script:ShadowBlurOff = $false }
    if ($dir -eq 's') { return }
    $file = Join-Path $gameDir "Main_release\track$dir\$slot\shadow.txt"
    if (-not (Test-Path -LiteralPath $file)) { return }
    $v = @(([IO.File]::ReadAllText($file)).Trim() -split '\s+')
    $a = 0.0; $b = 0.0; $inv = [Globalization.CultureInfo]::InvariantCulture; $any = [Globalization.NumberStyles]::Float
    # (NaN refused by name: every comparison with it is false, so "NaN 30" got through the range checks before 2026-10-15)
    if ($v.Count -lt 2 -or -not [double]::TryParse($v[0], $any, $inv, [ref]$a) -or -not [double]::TryParse($v[1], $any, $inv, [ref]$b) -or [double]::IsNaN($a) -or [double]::IsNaN($b) -or $a -le 0 -or $a -gt 0.01 -or $b -lt 1 -or $b -gt 200) { Log "Car shadows: $file not used (expected two numbers, e.g. 0.0002 30)."; return }
    $old = [Sr3Mem]::Read($h, 0x9F106C, 8); if ($null -eq $old) { return }
    $script:ShadowOrig = $old
    $new = New-Object byte[] 8; [Array]::Copy([BitConverter]::GetBytes([single]$a), 0, $new, 0, 4); [Array]::Copy([BitConverter]::GetBytes([single]$b), 0, $new, 4, 4)
    [Sr3Mem]::Write($h, 0x9F106C, $new, $true)
    $blur = ''
    if ($v.Count -ge 3 -and $v[2] -eq 'noblur') {
        if (Same ([Sr3Mem]::Read($h, $ShadowBlurVA, 5)) $ShadowBlurOrig) {
            [Sr3Mem]::Write($h, $ShadowBlurVA, [byte[]]@(0x90, 0x90, 0x90, 0x90, 0x90), $false); $script:ShadowBlurOff = $true; $blur = ', blur pass off'
        } else { $blur = ', blur pass NOT touched (unexpected bytes at its call)' }
    }
    Log "Car shadows: $slot uses variance floor $a, power $b$blur (Main_release\track$dir\$slot\shadow.txt)."
}
# SHADER EXPERIMENT (2026-10-08, "SR3 track format\24_shaders.md"). Can a pixel shader of the game be swapped while it runs?
# The uber effect "ubershadergame.fx" is one chunk of shaderlib3_uber_data.sbf with 1229 precompiled techniques; every shader record
# holds, at +0x10, the pointer of the Direct3D shader the game made from it at boot, and the game reads that pointer again at every
# bind. An added track may bring shader.txt in its folder with the word
#     untextured     the pixel shader of the imported walls (technique T_Lpse_Tdnsl, record at chunk +0xABFC) is pointed at the one of
#                    T_Lps (lit, no textures, record at chunk +0x8DFC): the imported scenery should lose its pictures and nothing else
#                    change. (18 of SEGA's own materials use the same technique and would lose theirs too while it is on.)
#     untextured-own the same for the technique T_Lpse_Tdnl (record at chunk +0xAB48), which no material of the game selects: only the tiles a
#                    build names in its course setting own_shader_tiles lose their pictures.
# The pointer is put back when another track is chosen or the file is gone. Nothing is written unless all four checks of the chunk hold.
# THE GAME'S ROAD NOT DRAWN (2026-10-09). An imported 1995 course may keep its own road polygons, joined to their walls and rock
# as SEGA modelled them; SEGA Rally 3's road (TrackDeform) is then needed for the DRIVING only, and wherever it is drawn it
# shows through the 1995 surface (its 1 m grid does not follow banked 1995 polygons; making its textures transparent does not
# hide it: build RAW2, in game). 0x4EEF70 is the routine that draws the road (cdecl, two arguments, plain ret; it is called from
# the wrappers 0x4EF4C0 and 0x4EF500, reached from 0x4F00D3, 0x5A3F4D, 0x5A42CB). A track folder with road.txt holding the
# word "hide" gets its first byte (0x55, push ebp) replaced by 0xC3 (ret) while that track is selected; the byte is put back for
# every other track. Nothing is written unless the first six bytes are the expected ones.
# A second routine, 0x4EE920 (cdecl, plain ret; called twice from 0x5E0330 with a car's position), draws road cells AROUND EACH CAR
# from the same road data (LIKELY the patch that carries ruts and tyre marks). With the 1995 road in the same place it flickers against
# it under the car, more the faster the car goes (RAW3, in game). road.txt with the words "hide all" stops that one too.
$RoadDrawVA = 0x4EEF70; $RoadDrawOrig = [byte[]]@(0x55, 0x8B, 0xEC, 0x83, 0xE4, 0xF0); $script:RoadHidden = $false
$RoadCarVA = 0x4EE920; $RoadCarOrig = [byte[]]@(0x83, 0xEC, 0x3C, 0x8B, 0x00, 0x6B); $script:RoadCarHidden = $false
function Set-RoadHide($h, [string]$gameDir, [string]$slot, [string]$dir) {
    if ($script:RoadHidden) { [Sr3Mem]::Write($h, $RoadDrawVA, [byte[]]@(0x55), $false); $script:RoadHidden = $false; Log "Game's road: drawn again." }
    if ($script:RoadCarHidden) { [Sr3Mem]::Write($h, $RoadCarVA, [byte[]]@(0x83), $false); $script:RoadCarHidden = $false }
    if ($dir -eq 's') { return }
    $file = Join-Path $gameDir "Main_release\track$dir\$slot\road.txt"
    if (-not (Test-Path -LiteralPath $file)) { return }
    $word = ([IO.File]::ReadAllText($file)).Trim().ToLower()
    if ($word -ne 'hide' -and $word -ne 'hide all') { Log "Game's road: $file not used (expected: hide, or: hide all)."; return }
    $now = [Sr3Mem]::Read($h, $RoadDrawVA, 6)
    if (-not (Same $now $RoadDrawOrig)) { Log "Game's road: NOT hidden, unexpected bytes at its drawing routine ($(($now | ForEach-Object { $_.ToString('X2') }) -join ' '))."; return }
    [Sr3Mem]::Write($h, $RoadDrawVA, [byte[]]@(0xC3), $false); $script:RoadHidden = $true
    $more = ''
    if ($word -eq 'hide all') {
        if (Same ([Sr3Mem]::Read($h, $RoadCarVA, 6)) $RoadCarOrig) { [Sr3Mem]::Write($h, $RoadCarVA, [byte[]]@(0xC3), $false); $script:RoadCarHidden = $true; $more = ', nor its patch around each car' }
        else { $more = ' (the patch around each car NOT touched: unexpected bytes)' }
    }
    Log "Game's road: not drawn on $slot$more (Main_release\track$dir\$slot\road.txt); it still carries the driving."
}
$script:ShaderSwap = $null
function Set-ShaderTest($h, [string]$gameDir, [string]$slot, [string]$dir) {
    if ($script:ShaderSwap) { [Sr3Mem]::Write($h, $script:ShaderSwap.Va, $script:ShaderSwap.Old, $true); Log "Shader experiment: the wall shader is back (pointer restored)."; $script:ShaderSwap = $null }
    if ($dir -eq 's') { return }
    $file = Join-Path $gameDir "Main_release\track$dir\$slot\shader.txt"
    if (-not (Test-Path -LiteralPath $file)) { return }
    $word = ([IO.File]::ReadAllText($file)).Trim().ToLower()
    if ($word -ne 'untextured' -and $word -ne 'untextured-own') { Log "Shader experiment: $file not used (expected the word: untextured or untextured-own)."; return }
    $rec = if ($word -eq 'untextured-own') { 0xAB48 } else { 0xABFC }; $code = if ($word -eq 'untextured-own') { 0x10E420 } else { 0x1122B8 }      # the pixel shader record of the technique, and where its bytecode starts
    $u32 = { param($va) $b = [Sr3Mem]::Read($h, $va, 4); if ($null -eq $b) { return $null }; return [long][BitConverter]::ToUInt32($b, 0) }
    $n = & $u32 0x9F1280
    if ($null -eq $n -or $n -lt 1 -or $n -gt 64) { Log "Shader experiment: the effect list could not be read (count $n)."; return }
    $base = $null
    for ($i = 0; $i -lt $n; $i++) {
        $np = & $u32 (0x9F1084 + 8 * $i); if ($null -eq $np -or $np -lt 0x10000) { continue }
        $s = [Sr3Mem]::Read($h, $np, 18); if ($null -eq $s) { continue }
        if ([Text.Encoding]::ASCII.GetString($s) -eq "ubershadergame.fx`0") { $base = $np - 0xACB0; break }
    }
    if ($null -eq $base) { Log "Shader experiment: ubershadergame.fx is not in the effect list ($n effects): nothing changed."; return }
    $c1 = & $u32 $base; $c2 = & $u32 ($base + 0x70E4 + 8); $c3 = & $u32 ($base + $rec); $c4 = if ($c3) { & $u32 ($base + $code) } else { $null }
    if ($c1 -ne 0x02D604CD -or $c2 -ne ($base + 0xABFC) -or $c3 -ne ($base + $code) -or $c4 -ne 4294902528) {      # 0xFFFF0300 (written so: the literal 0xFFFF0300 is the int -64768 in PowerShell, so this check could never pass before 2026-10-15)
        Log ("Shader experiment: the effect at 0x{0:X} is not the one this was written for (checks {1:X} {2:X} {3:X} {4:X}; shader library 2 instead of 3?): nothing changed." -f $base, $c1, $c2, $c3, $c4); return
    }
    $va = $base + $rec + 0x10; $a = [Sr3Mem]::Read($h, $va, 4); $b = [Sr3Mem]::Read($h, ($base + 0x8DFC + 0x10), 4)
    $wa = if ($a) { [BitConverter]::ToUInt32($a, 0) } else { 0 }; $wb = if ($b) { [BitConverter]::ToUInt32($b, 0) } else { 0 }    # (an unreadable one is 0: ToUInt32 of nothing threw and stopped the loop)
    if ($wa -eq 0 -or $wb -eq 0) { Log "Shader experiment: a shader pointer is empty (walls $wa, plain $wb): nothing changed."; return }
    [Sr3Mem]::Write($h, $va, $b, $true); $script:ShaderSwap = @{ Va = $va; Old = $a }
    $back = [Sr3Mem]::Read($h, $va, 4)
    Log ("Shader experiment: effect at 0x{0:X}; wall pixel shader 0x{1:X} replaced by the untextured one 0x{2:X} (read back 0x{3:X}). Imported scenery should show without its pictures." -f $base, [BitConverter]::ToUInt32($a, 0), [BitConverter]::ToUInt32($b, 0), [BitConverter]::ToUInt32($back, 0))
}

# ---- In a race: START = a screenshot, VIEW CHANGE held = back to the main menu ----
# A short press of START takes a screenshot when START is let go (held for $StartHoldSeconds or more it does nothing: until
# 2026-10-14 that hold left the race). VIEW CHANGE held for $StartHoldSeconds leaves the race for the game's main menu (owner,
# 2026-10-14: "Replace long START to exit with long VIEW CHANGE"); a short press is the game's own camera change, and the
# camera the hold stepped to is put back when the race is left (Undo-ViewStep). The game has no flag we know that tells a
# race from the attract loop, so a race is what follows the menus, and the picture is held back 1.5 s: if the menus come up
# in that time, START was "begin a game" and the picture is dropped. Pictures are at least 2 s apart, and the file name is
# shown only after the picture was taken, so it is never in it. Step-Start is the decision alone, apart from the game
# (tools\start_mocktest.ps1 drives it): it returns what to do now, any of 'grab' (take the picture), 'save' (write the held
# one), 'drop' (forget it), 'exit'. The buttons are the game's own inputs (Get-GameButtons), in XInput's bits: START 0x10, View Change 0x1000.
$StartHoldSeconds = 1.2
function New-StartState { return @{ Was = $false; At = [datetime]::MinValue; Armed = $false; VWas = $false; VAt = [datetime]::MinValue; VArmed = $false; Long = $false; Race = $false; WasMenu = $false; HeldAt = $null; ShotAt = [datetime]::MinValue } }
function Step-Start($s, [bool]$down, [bool]$view, [bool]$menu, [datetime]$now) {
    $acts = @()
    if ($s.WasMenu -and -not $menu) { $s.Race = $true }
    if ($null -ne $s.HeldAt) {
        if ($menu) { $s.HeldAt = $null; $s.Race = $false; $acts += 'drop' }                  # that START began a new game
        elseif (($now - $s.HeldAt).TotalSeconds -ge 1.5) { $s.HeldAt = $null; $acts += 'save' }
    }
    if ($menu) { $s.Armed = $false; $s.VArmed = $false }                                  # a press that sees the menus does nothing
    if ($down -and -not $s.Was) { $s.Armed = $s.Race -and -not $menu; $s.At = $now }
    elseif (-not $down -and $s.Was) {
        if ($s.Armed -and ($now - $s.At).TotalSeconds -lt $StartHoldSeconds -and $null -eq $s.HeldAt -and ($now - $s.ShotAt).TotalSeconds -gt 2) { $s.HeldAt = $now; $s.ShotAt = $now; $acts += 'grab' }
        $s.Armed = $false
    }
    if ($view -and -not $s.VWas) { $s.VArmed = $s.Race -and -not $menu; $s.VAt = $now; $s.Long = $false }
    elseif ($view -and $s.VArmed -and -not $s.Long -and ($now - $s.VAt).TotalSeconds -ge $StartHoldSeconds) { $s.Long = $true; $acts += 'exit' }
    elseif (-not $view) { $s.VArmed = $false }
    $s.Was = $down; $s.VWas = $view; $s.WasMenu = $menu
    return $acts
}
# What a screenshot carries (PNG tEXt chunk "SR3Lab", one line of JSON, read when the picture is grabbed). The view: 0x5A1A70
# builds it every frame from the camera the frame is drawn from ([mgr + 0x184], whatever its class: the game's, CamLab's
# chase slots, the debug cameras, a blend) and keeps per local player (block 0x9EB930 + 0x4D0 x [0x9F05F0]): +0 the view
# matrix (D3DXMatrixLookAtLH), +0x40 its inverse, camera to world, rows right / up / forward / eye, +0x478 the field of
# view in radians (the camera state's +0x178, the value CamLab's profiles set in degrees). The camera's name is the one the
# camera block shows (its race-list index, as the block's popup works it out). The car: [mgr + 0x1C8], + 0xAC its place as
# drawn, + 0x135C its matrix (forward row + 0x20).
function Read-GameFloats($h, [long]$va, [int]$n) {
    $b = [Sr3Mem]::Read($h, $va, 4 * $n); if (-not $b -or $b.Length -lt 4 * $n) { return $null }
    $o = New-Object double[] $n; for ($i = 0; $i -lt $n; $i++) { $o[$i] = [Math]::Round([double][BitConverter]::ToSingle($b, 4 * $i), 4) }
    return ,$o
}
function Get-ShotInfo($h, [long]$base, [string]$track, [string]$dir, [string]$title, [datetime]$at) {
    $info = [ordered]@{ time = $at.ToString('yyyy-MM-ddTHH:mm:ss.fff'); coords = 'game (y up)' }
    $pl = Read-GameInt $h 0x9F05F0; if ($pl -lt 0 -or $pl -gt 3) { $pl = 0 }
    $v = Read-GameFloats $h (0x9EB970 + 0x4D0 * $pl) 16
    $fov = Read-GameFloats $h (0x9EBDA8 + 0x4D0 * $pl) 1
    $cam = [ordered]@{ source = 'view matrix 0x9EB970 (the frame''s camera to world)' }
    if ($v) { $cam.eye = @($v[12], $v[13], $v[14]); $cam.forward = @($v[8], $v[9], $v[10]); $cam.up = @($v[4], $v[5], $v[6]) }
    if ($fov) { $cam.fov_deg = [Math]::Round($fov[0] * 180 / [Math]::PI, 2) }
    $mgr = Read-GamePtr $h 0x9EB4EC
    if ($mgr) {
        $mgr += 0x18; $drawn = Read-GamePtr $h ($mgr + 0x184); $idx = Read-GameInt $h ($mgr + 0x230)
        $cam.vtable = '0x{0:X}' -f (Read-GamePtr $h $drawn); $cam.list_index = $idx
        $nm = ''
        if ($base -and $idx -ge 0 -and $idx -lt 21 -and $drawn -eq (Read-GamePtr $h ($mgr + 0x234 + 4 * $idx))) {   # the race list's camera (the block's popup naming)
            $ng = Read-GameInt $h ($base + 0x2260); $ns = Read-GameInt $h ($base + 0x20)
            if ($idx -eq 0) { $nm = Read-GameString $h ($base + 0x100) 32 }
            elseif ($idx -gt $ng -and ($idx - $ng) -lt $ns) { $nm = Read-GameString $h ($base + 0x100 + 32 * ($idx - $ng)) 32 }
            else {
                $off = $drawn - $mgr; if ($idx -eq (Read-GameInt $h ($base + 0x225C))) { $off = $off -bor [long]2147483648 }   # (the literal 0x80000000 is the int -2147483648 in PowerShell: -bor set every high bit and nothing matched)
                for ($i = 0; $i -lt $CycleGameCams; $i++) { if ((Read-GamePtr $h ($base + 0x21B0 + 4 * $i)) -eq $off) { $nm = Read-GameString $h ($base + 0x2000 + 32 * $i) 32 } }
            }
        }
        $cam.name = $(if ($nm) { $nm } else { 'not a race-list camera (intro, replay, trackside)' })
        $car = Read-GamePtr $h ($mgr + 0x1C8)
        if ($car) { $p = Read-GameFloats $h ($car + 0xAC) 3; $f = Read-GameFloats $h ($car + 0x135C + 0x20) 3; if ($p -and $f) { $info.car = [ordered]@{ pos = @($p[0], $p[1], $p[2]); forward = @($f[0], $f[1], $f[2]) } } }
    }
    $info.camera = $cam
    $info.track = [ordered]@{ name = $track; folder = $(if (-not $track) { '' } elseif ($dir -eq 's') { "tracks\$track" } else { "track$dir\$track" }); title = $title }
    return ($info | ConvertTo-Json -Compress -Depth 5)
}
function Add-PngText([byte[]]$png, [string]$key, [string]$text) {             # a tEXt chunk right after IHDR (8 + 25 bytes)
    if (-not ('Sr3Png' -as [type])) {
        Add-Type @'
public static class Sr3Png {
  public static byte[] Insert(byte[] png, string key, string text) {
    var l1 = System.Text.Encoding.GetEncoding(28591);
    byte[] k = l1.GetBytes("tEXt" + key), t = l1.GetBytes(text), d = new byte[k.Length + 1 + t.Length];
    System.Array.Copy(k, d, k.Length); System.Array.Copy(t, 0, d, k.Length + 1, t.Length);
    uint crc = 0xFFFFFFFF;
    foreach (byte b in d) { crc ^= b; for (int i = 0; i < 8; i++) crc = (crc & 1) != 0 ? 0xEDB88320 ^ (crc >> 1) : crc >> 1; }
    crc ^= 0xFFFFFFFF;
    var o = new System.IO.MemoryStream(); int n = d.Length - 4;
    o.Write(png, 0, 33);
    o.WriteByte((byte)(n >> 24)); o.WriteByte((byte)(n >> 16)); o.WriteByte((byte)(n >> 8)); o.WriteByte((byte)n);
    o.Write(d, 0, d.Length);
    o.WriteByte((byte)(crc >> 24)); o.WriteByte((byte)(crc >> 16)); o.WriteByte((byte)(crc >> 8)); o.WriteByte((byte)crc);
    o.Write(png, 33, png.Length - 33);
    return o.ToArray();
  }
}
'@
    }
    if ($png.Length -lt 33 -or [Text.Encoding]::ASCII.GetString($png, 12, 4) -ne 'IHDR') { return ,$png }
    return ,([Sr3Png]::Insert($png, $key, $text))
}
# Leaving a race the way the game itself does (FINDINGS.md, "Leaving a race"): the race update (0x5C89D0, every frame on
# the game's thread) watches [0x9DB4F4]; when it is set it clears it and makes the next state 0x1B (CSR_GameMode::Finish),
# which ends the mode and goes on to the race teardown (0x2A) and the front end. The pause menu's Quit (0x635970) and the
# Classic result page (0x60DFA0) set the same flag, and like them this first starts the 0.5 s fade to black (0x5FBB10 keeps
# its state at 0x9DB490-0x9DB4AB, timed by the game's clock [0x9C4A08] in microseconds; the teardown waits for it).
# Only while a race runs: main state [0x7ECE10] = 0x27 with no change pending ([0x7ECE14] = 0x27), in a player's mode
# [0x728598] (5 Quick Race, 6 Championship, 7 Classic; 2 is the attract demo, 3 "Press START"). In a Championship the stage
# number [0x9DB820] is set to the number of stages first, as the Quit does, so that it ends instead of going on to its next
# stage; and as the end of a championship takes a leader (race position [0x9DD61C] = 1) on to the Stadium4 bonus stage
# (0x6358A2), the position reads 2 once the race has stopped (cars and positions move only in states 0x27 and 0x1C).
$RaceExitFlagVA = 0x9DB4F4; $GameStateVA = 0x7ECE10; $GameModeVA = 0x728598; $FadeVA = 0x9DB490; $GameClockVA = 0x9C4A08
$ChampStageVA = 0x9DB820; $PlayerPositionVA = 0x9DD61C; $RaceModes = @{ 5 = 'Quick Race'; 6 = 'Championship'; 7 = 'Classic race' }
$script:RaceExit = $null
# The press that began a VIEW CHANGE hold was also the game's View Change: one step forward in the race camera list
# (mgr + 0x230 = (index + 1) mod count, mgr + 0x190 = that camera). When the hold leaves the race, the camera before it is
# put back the way the camera block itself puts a camera back (+0x190, then +0x230), with the block's last index cleared so
# it takes that camera's settings again (and keeps it for the next race) and QUIET so it shows no name; with the game
# suspended, so the block never sees half of it.
function Undo-ViewStep($h, [long]$base) {
    $mgr = Read-GamePtr $h 0x9EB4EC
    if (-not $mgr -or -not $base) { return }
    $mgr += 0x18; $n = Read-GameInt $h ($mgr + 0x22C); $i = Read-GameInt $h ($mgr + 0x230)
    if ($n -lt 2 -or $n -gt 21 -or $i -lt 0 -or $i -ge $n) { return }
    $p = ($i - 1 + $n) % $n; $cam = Read-GamePtr $h ($mgr + 0x234 + 4 * $p)
    if (-not $cam) { return }
    [Sr3Mem]::Suspend($h)
    try {
        Write-GameInt $h ($mgr + 0x190) $cam; Write-GameInt $h ($base + 0xB0) 1
        Write-GameInt $h ($mgr + 0x230) $p; [Sr3Mem]::Write($h, $base + 0x1C, ([BitConverter]::GetBytes([int]-1)), $true)
    } finally { [Sr3Mem]::Resume($h) }
}
function Request-RaceExit($h, [datetime]$now) {
    $st = [Sr3Mem]::Read($h, $GameStateVA, 8); $mode = Read-GameInt $h $GameModeVA
    if ($null -eq $st) { Log 'Race exit: the game state could not be read; nothing done.'; return }
    $cur = [BitConverter]::ToInt32($st, 0); $next = [BitConverter]::ToInt32($st, 4)
    if ($cur -ne 0x27 -or $next -ne 0x27 -or -not $RaceModes.ContainsKey($mode)) { Log ("Race exit: VIEW CHANGE was held, but no race is running (game state 0x{0:X} / 0x{1:X}, mode {2}); nothing done." -f $cur, $next, $mode); return }
    $x = @{ At = $now; Mode = $mode; Taken = $false; Stage = $null; Fade = $false; Pos = $false }
    if ($mode -eq 6) {
        $n = Read-GameInt $h ((Read-GameInt $h ((Read-GameInt $h 0xB2A850) + 0x10)) + 4)
        if ($n -lt 1 -or $n -gt 16) { Log "Race exit: the championship's number of stages could not be read ($n); nothing done."; return }
        $x.Stage = Read-GameInt $h $ChampStageVA; Write-GameInt $h $ChampStageVA $n
    }
    # the fade to black as 0x5FBB10(500 ms, 0, 1) starts it, in one write: from now (+0, ms), out (+8 = 0), +0xC = 1, +0x10 = 0, 500.0 (+0x18)
    $f = [Sr3Mem]::Read($h, $FadeVA, 0x1C); $c1 = [Sr3Mem]::Read($h, $GameClockVA, 8); $c2 = [Sr3Mem]::Read($h, $GameClockVA, 8)
    if ($f -and $c1 -and $c2 -and [BitConverter]::ToInt32($f, 8) -ne 0 -and [BitConverter]::ToInt32($c1, 4) -eq [BitConverter]::ToInt32($c2, 4)) {
        $x.Fade = $f.Clone()
        $us = [BitConverter]::ToInt64($c2, 0); $ms = [long](($us - ($us % 1000)) / 1000)
        Put $f 0 ([BitConverter]::GetBytes([long]$ms)); Put $f 8 ([BitConverter]::GetBytes([int]0)); Put $f 0xC ([BitConverter]::GetBytes([int]1))
        Put $f 0x10 ([BitConverter]::GetBytes([int]0)); Put $f 0x18 ([BitConverter]::GetBytes([single]500))
        [Sr3Mem]::Write($h, $FadeVA, $f, $true)
    }
    # still racing? (a race that ended or a load that began in these few milliseconds gets nothing: the flag is read only
    # by the race update, and a load must never be cut short - its abort path can hang the game for good)
    $st = [Sr3Mem]::Read($h, $GameStateVA, 8)
    if ($null -eq $st -or [BitConverter]::ToInt32($st, 0) -ne 0x27 -or [BitConverter]::ToInt32($st, 4) -ne 0x27) { Undo-RaceExit $h $x 'the race ended just then'; return }
    Write-GameInt $h $RaceExitFlagVA 1
    $script:RaceExit = $x
    Log "Race exit: VIEW CHANGE held $StartHoldSeconds s: leaving the $($RaceModes[$mode]) for the main menu."          # ("$x" writes a number the same in every culture, -f does not)
}
function Undo-RaceExit($h, $x, [string]$why) {
    Write-GameInt $h $RaceExitFlagVA 0
    if ($null -ne $x.Stage) { Write-GameInt $h $ChampStageVA $x.Stage }
    if ($x.Fade) { [Sr3Mem]::Write($h, $FadeVA, $x.Fade, $true) }                        # the fade as it was: the picture is back at once
    Log "Race exit: $why; nothing changed in the game."
    $script:RaceExit = $null
}
# After the request, on each pass: whether the game has taken it, the championship leader's position, and safety nets: a
# request the game has not taken after 2 s, or one still waiting when the race ends some other way, is withdrawn
# (everything put back), and a fade still not done after 4 s is let go (the teardown waits only while it runs).
function Step-RaceExit($h, [datetime]$now) {
    $x = $script:RaceExit; if (-not $x) { return }
    $t = ($now - $x.At).TotalSeconds
    $st = [Sr3Mem]::Read($h, $GameStateVA, 8); if ($null -eq $st) { $script:RaceExit = $null; return }
    $cur = [BitConverter]::ToInt32($st, 0); $next = [BitConverter]::ToInt32($st, 4)
    if (-not $x.Taken) {
        if ((Read-GameInt $h $RaceExitFlagVA) -eq 0 -or $next -eq 0x1B -or $cur -eq 0x1B -or $cur -eq 0x2A) { $x.Taken = $true }
        elseif ($cur -eq 0x27 -and $next -eq 0x27) { if ($t -ge 2) { Undo-RaceExit $h $x 'the game did not take the request within 2 s' }; return }
        else { Undo-RaceExit $h $x ("the race ended another way before the game read the request (state 0x{0:X} / 0x{1:X})" -f $cur, $next); return }
    }
    $stopped = ($cur -eq 0x27 -and $next -ne 0x27) -or $cur -eq 0x1B -or $cur -eq 0x2A
    if ($x.Mode -eq 6 -and $stopped -and (Read-GameInt $h $PlayerPositionVA) -eq 1) {
        Write-GameInt $h $PlayerPositionVA 2
        if (-not $x.Pos) { $x.Pos = $true; Log 'Race exit: you were leading the championship; the bonus stage is skipped.' }
    }
    if ($cur -eq 0x2A -and $t -gt 4 -and (Read-GameInt $h ($FadeVA + 8)) -eq 0) { Write-GameInt $h ($FadeVA + 8) 1; Log 'Race exit: the fade to black did not finish; the game goes on without it.' }
    if (-not $stopped -and $cur -ne 0x27) { Log ("Race exit: done, the game is on its way to the menus (state 0x{0:X})." -f $cur); $script:RaceExit = $null; return }
    if ($t -gt 15) { Log ("Race exit: the game is still in state 0x{0:X} / 0x{1:X} after 15 s; no longer followed." -f $cur, $next); $script:RaceExit = $null }
}

# ---- the watchdog: crashes and freezes recorded as they happen ----
# watchdog.cs attaches to the game as a debugger once it has booted and the camera patch is in (TeknoParrot looks at the
# process during its first seconds, hence not earlier). It changes nothing in the game: every exception goes back to it as
# without a debugger, and when this window closes Windows detaches it and the game runs on. A crash, a freeze (the game's
# window does not answer for $FreezeSeconds) or a message box of the game's is written to SR3CamLab\crash\ (a log per
# session, plus a minidump), with a line here. -NoWatchdog leaves it out (another debugger cannot attach while it runs).
# A load that never ends is one such freeze: the main thread waits without end on the loader threads in 0x5877E0
# (WaitForSingleObject, no message loop), so the window stops answering; the samples show every loader thread by its
# start address. No data breakpoints: debug registers on the game's threads made it quit by itself (2026-10-14).
# Each record also gives the main state, the one pending, the mode and the menus flag (see Request-RaceExit).
$FreezeSeconds = 10; $GameWindowVA = 0x728CF4                         # where the game keeps its window handle (written at 0x558D4B, right after CreateWindowExA "RacingClass")
$WatchdogValues = 'state=0x7ECE10, next=0x7ECE14, mode=0x728598, menus=0x9D6E3C:1'
$script:WatchdogOn = $false
function Start-Watchdog($game) {
    $cs = Join-Path $PSScriptRoot 'watchdog.cs'
    if (-not (Test-Path -LiteralPath $cs)) { Log 'Watchdog: watchdog.cs is missing next to sr3mods.ps1; crashes and freezes are not recorded this time.'; return }
    try {
        if (-not ('Sr3Watchdog' -as [type])) { Add-Type -Path $cs -ErrorAction Stop }
        [Sr3Watchdog]::Values = $WatchdogValues
        [void][Sr3Watchdog]::Start($game.Id, (Join-Path $PSScriptRoot 'crash'), $FreezeSeconds, $GameWindowVA)
        $script:WatchdogOn = $true
    } catch { Log "Watchdog: could not start ($($_.Exception.Message)); crashes and freezes are not recorded this time."; return }
    for ($i = 0; $i -lt 30 -and -not [Sr3Watchdog]::Attached -and -not [Sr3Watchdog]::Finished; $i++) { Start-Sleep -Milliseconds 100 }
    Start-Sleep -Milliseconds 100; Show-WatchdogNews
}
# Ctrl+Scroll Lock in the game (Bruno, 2026-10-15): the watchdog now, without starting the game again (it records from then
# on; one started with the game, the default, is already on). The popup's two lines. (pc_live.c asks its front end, GameMem.watch.)
function Request-Watchdog($game) {
    if (-not $script:WatchdogOn) { Start-Watchdog $game }
    if ($script:WatchdogOn) { return @('Watchdog on', [IO.Path]::GetFileName([Sr3Watchdog]::LogPath)) }
    return @('Watchdog not started', 'see play.log')
}
function Show-WatchdogNews { if ($script:WatchdogOn) { for ($m = [Sr3Watchdog]::NextMessage(); $null -ne $m; $m = [Sr3Watchdog]::NextMessage()) { Log "Watchdog: $m" } } }
function Stop-Watchdog {
    if (-not $script:WatchdogOn) { return }
    if (-not [Sr3Watchdog]::WaitFinished(5000)) { [Sr3Watchdog]::Stop(5000) }           # the game has closed: its last events are in
    Show-WatchdogNews
}
function Wait-GameExit($game) {
    while (-not $game.HasExited) {
        if ($script:CarListPending) {                                  # (Set-CarLists: the menus were up when it ran)
            $hc = [Sr3Mem]::Open($game.Id)
            try { if (Complete-CarLists $hc) { Log 'Car lists: every car in every mode from this game on.' } } finally { [Sr3Mem]::Close($hc) }
        }
        Show-WatchdogNews; Start-Sleep -Milliseconds 250
    }
    $game.WaitForExit(); Show-WatchdogNews
}

# Runs until the game closes.
# What the loop asks of the world outside the game's memory, each in a function of its own: the mock tests and the trace
# lockstep (tools\sr3mods\live_lockstep.py) put fakes in their place, and patchcore (pc_live.c) asks its GameMem the same
# questions (now, key, front, shot).
function Initialize-Host {
    Add-Type -AssemblyName System.Drawing, System.Windows.Forms
    if (-not ('Sr3Pad' -as [type])) {
        Add-Type @'
using System; using System.Runtime.InteropServices;
public static class Sr3Pad {
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern short GetAsyncKeyState(int vk);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
'@
    }
    [Sr3Pad]::SetProcessDPIAware() | Out-Null
}
function Get-Now { return (Get-Date) }
# START and VIEW CHANGE as the game itself sees them: its logical inputs, a dword each at 0x9DBAD0 + 4 x entry (90 of them;
# the low 15 bits = held this frame, the previous frame shifted by 15, bit 30 = pressed this frame): START = entry 53
# (0x9DBBA4), View Change = entry 15 (0x9DBB0C), the same in the menus and in a race (found in the game 2026-10-15; gas is
# 29, handbrake 32). So a keyboard, TeknoParrot's mapping, a wheel or a test pad all count. Until 2026-10-15 XInput pad 0
# was read directly, which saw nothing else. Returned in XInput's bits, START 0x10 and View Change 0x1000, for Step-Start.
function Get-GameButtons($h) { $b = 0; if ((Read-GameInt $h 0x9DBBA4) -band 0x7FFF) { $b = $b -bor 0x10 }; if ((Read-GameInt $h 0x9DBB0C) -band 0x7FFF) { $b = $b -bor 0x1000 }; return $b }
function Test-KeyDown([int]$vk) { return ([Sr3Pad]::GetAsyncKeyState($vk) -band 0x8000) -ne 0 }
function Get-FrontWindow { return [long][Sr3Pad]::GetForegroundWindow() }
function New-ScreenGrab {                                          # the whole primary screen, as it is now
    $sb = [Windows.Forms.Screen]::PrimaryScreen.Bounds; $bmp = New-Object Drawing.Bitmap $sb.Width, $sb.Height
    $gr = [Drawing.Graphics]::FromImage($bmp); $gr.CopyFromScreen($sb.Location, [Drawing.Point]::Empty, $sb.Size); $gr.Dispose()
    return $bmp
}
function Save-ScreenGrab($bmp, [string]$path, $info) {             # as PNG, with the shot's info in a tEXt chunk (Add-PngText)
    $ms = New-Object IO.MemoryStream; $bmp.Save($ms, [Drawing.Imaging.ImageFormat]::Png); $png = $ms.ToArray(); $ms.Dispose()
    if ($info) { $png = Add-PngText $png 'SR3Lab' $info }
    [IO.File]::WriteAllBytes($path, $png)
}
function Close-ScreenGrab($bmp) { if ($bmp) { $bmp.Dispose() } }
function Watch-Tracks($game, [string]$gameExe) {
    Initialize-Host
    $start = New-StartState; $script:RaceExit = $null; $shotUntil = [datetime]::MinValue; $shotName = ''; $shotHeld = $null; $shotInfo = $null
    $slots = Read-TrackSwitch $gameExe
    if (-not $slots) { $slots = [ordered]@{} }                                # no alternative tracks: the loop still runs for START (screenshot, race exit)
    $h = [Sr3Mem]::Open($game.Id)
    try {
        $base = Find-Cycle $h
        if (-not $base) { Log 'Alternative tracks, the START screenshot and the VIEW CHANGE race exit need the camera patch; it is not in the game.'; Wait-GameExit $game; return }
        $tdCave = $null; $script:TrackDirLast = $null
        if ($slots.Count) {
            Log ('Alternative tracks: ' + ((@($slots.Keys | Sort-Object) | ForEach-Object { "$_ +$($slots[$_].Count - 1)" }) -join ', ') + '. On the stage-select screen, View Change steps through them.')
            Initialize-TrackVideos $h $base $slots
            $tdCave = Install-TrackDir $h
            if ($tdCave) { Log 'Track folders: chosen in the game''s own path code (each load reads one folder).' }
        }
        $cardsOpen = (Open-CarCards $h $base) -ne $false                 # before the first menus: the car select looks its cards up when they are built
        $text = $base + $SwitchTextOff
        [Sr3Mem]::Write($h, $text + 0x40, (Str 'Press VIEW CHANGE to select alternative tracks' 64), $true)
        $choice = [ordered]@{}; foreach ($s in $slots.Keys) { $choice[$s] = 0 }
        $soundNow = '//'; $tuneNow = ''; $script:TuneOwn = $null; $ids = @{}; $pvsHeld = $false; $pvsWas = 0
        $modeSeen = $null; $modeLast = $null; $nameWas = ''; $classicVal = $null
        $classicFile = Join-Path (Split-Path -Parent $gameExe) 'Main_release\tracks\_SR3Extras\classic_mode.txt'
        if (Test-Path -LiteralPath $classicFile) { $t = ([IO.File]::ReadAllText($classicFile)).Trim(); if ($t -match '^-?\d+$') { $classicVal = [int]$t } }
        $dirNow = 's'; $wasDown = $false; $wasMenu = $false; $deep = $false; $showing = $false; $shown = ''; $timesNow = ''
        $keysDown = @{}; $labelUntil = [datetime]::MinValue; $labelLines = @('', ''); $watchKeyWas = $false
        while (-not $game.HasExited) {
            $g = [Sr3Mem]::Read($h, 0x9D6E3C, 1)
            if ($null -eq $g) { break }
            $menu = $g[0] -eq 1
            if ($script:CarListPending -and -not $menu -and (Complete-CarLists $h)) { Log 'Car lists: every car in every mode from this game on.' }   # (Set-CarLists: the menus were up when it ran)
            if ($menu -and -not $wasMenu) {                           # a new game: every card back to its own track
                if (-not $cardsOpen) { $cardsOpen = (Open-CarCards $h $base) -ne $false }
                $deep = $false
                foreach ($s in @($choice.Keys)) {
                    if ($choice[$s] -ne 0) { Set-CardTrack $h $base $s $slots[$s][0] $true }
                    $choice[$s] = 0
                }
            }
            $count = Read-GameInt $h 0x9C442C
            if ($menu -and ($count -ge 6 -or $count -eq 2)) { $deep = $true }      # past the mode menu, which also has 3 entries (the car select: 6, or every car with Set-CarLists; ">= 4" took a screen before the mode menu for it, 2026-10-14)
            $stage = $menu -and $deep -and $count -eq 3
            $p1 = Read-GameInt $h 0x9DBDB0
            $name = ''
            if ($p1) { $p2 = Read-GameInt $h ($p1 + 0x18); if ($p2) { $name = Read-GameString $h $p2 24 } }
            # the card the stage selector is on
            $hi = Read-GameInt $h ($base + 0x226C); $hiName = ''
            if ($hi -ne -1) { if (-not $ids.ContainsKey($hi)) { $ids = Read-TrackNames $h }; $hiName = "$($ids[$hi])" }
            $stage = $stage -and $hiName
            $hlist = if ($stage) { $slots[$hiName] } else { $null }
            $vb = [Sr3Mem]::Read($h, 0x9DBB0C, 1); $down = [bool]($vb -and $vb[0] -ne 0)     # (unreadable = not held; indexing nothing threw and stopped the loop)
            if ($hlist -and $down -and -not $wasDown) {
                $choice[$hiName] = ($choice[$hiName] + 1) % $hlist.Count
                Set-CardTrack $h $base $hiName $hlist[$choice[$hiName]] ($choice[$hiName] -eq 0)
            }
            # Classic has no stage select: its tracks (the Desert4 slot) are stepped through on the first menu,
            # the one with Championship / Quick Race / Classic (3 entries, before the car and gearbox menus)
            $mode = $menu -and (-not $deep) -and $count -eq 3 -and $slots.Contains($ClassicSlot)
            # ... and only while that menu is on Classic. Which of the selector's values is Classic is learnt
            # the first time Classic is picked (the current track becomes Desert4 right after) and kept in
            # tracks\_SR3Extras\classic_mode.txt; until then the text shows on all three.
            $modeVal = Read-GameInt $h ($base + 0x2278)
            if ($mode -and $modeVal -ne -1) { if ($modeVal -ne $modeSeen) { Log "Alternative tracks: first menu is on entry $modeVal."; $modeSeen = $modeVal } ; $modeLast = $modeVal }
            # (learnt once: a value already kept is never overwritten. Menus gone through quickly, as a script does, can leave the poll
            # without the last steps, and on 2026-10-14 such a run turned Classic = 2 into 0 and the Classic popup went away)
            if ($name -eq $ClassicSlot -and $nameWas -and $nameWas -ne $ClassicSlot -and $null -ne $modeLast -and $null -eq $classicVal) {
                $classicVal = $modeLast; Log "Alternative tracks: Classic is entry $classicVal of the first menu."
                try { [IO.File]::WriteAllText($classicFile, "$classicVal") } catch { }
            }
            if ($name) { $nameWas = $name }
            if ($mode -and $null -ne $classicVal -and $modeVal -ne $classicVal) { $mode = $false }
            if ($mode -and $down -and -not $wasDown) {
                $clist = $slots[$ClassicSlot]
                $choice[$ClassicSlot] = ($choice[$ClassicSlot] + 1) % $clist.Count
                Set-CardTrack $h $base $ClassicSlot $clist[$choice[$ClassicSlot]] ($choice[$ClassicSlot] -eq 0)
            }
            # the game reads the files of the chosen track: of the highlighted card while choosing, of the current track after
            if ($stage) { $name = $hiName }
            $list = $slots[$name]
            $dir = if ($list) { $list[$choice[$name]].Dir } else { 's' }
            if ($tdCave) { Write-TrackDirTable $h $tdCave $slots $choice }   # the game's path code picks the folder from this table
            if ($dir -ne $dirNow) {
                if (-not $tdCave) { foreach ($a in $TrackDirSites) { [Sr3Mem]::Write($h, $a, [byte[]]@([byte][char]$dir), $true) } }
                if ($script:TrackArt) {
                    [Sr3Mem]::Write($h, $TrackBkgdSite, [byte[]]@([byte][char]$(if ($dir -eq 's') { 'D' } else { $dir })), $true)
                    foreach ($a in $TrackBannerSites) { [Sr3Mem]::Write($h, $a, [byte[]]@([byte][char]$(if ($dir -eq 's') { 'R' } else { $dir })), $true) }
                }
                $dirNow = $dir
            }
            if ("$name/$dir" -ne $timesNow) { Set-ArcadeTimes $h (Split-Path -Parent $gameExe) $name $dir; Set-ShadowParams $h (Split-Path -Parent $gameExe) $name $dir; Set-ShaderTest $h (Split-Path -Parent $gameExe) $name $dir; Set-RoadHide $h (Split-Path -Parent $gameExe) $name $dir; $timesNow = "$name/$dir" }
            # ... and its sounds are the chosen track's, where the game has them
            $cur = if ($list) { $list[$choice[$name]] } else { $null }
            $sound = if ($cur) { "$($cur.Ambience)/$($cur.Music)/$($cur.Events)" } else { '//' }
            if ($sound -ne $soundNow) {
                foreach ($t in $TrackSoundSites) {
                    $id = if ($cur) { $cur[$t.Kind] } else { '' }
                    $to = $t.Own
                    if ($id) { $to = $base + $t.Text; [Sr3Mem]::Write($h, $to, (Str ($t.Name -f $id) 64), $true) }
                    [Sr3Mem]::Write($h, $t.Site, ([BitConverter]::GetBytes([int]$to)), $true)
                }
                $soundNow = $sound
            }
            # ... and its own tune, when it has one (the slot's own music otherwise)
            $tune = if ($cur) { $cur.Tune } else { $null }
            $tuneKey = if ($tune) { "$($tune.Stream)/$($tune.Offset)/$($tune.Bytes)/$($tune.LoopStart)" } else { '' }
            if ($tuneKey -ne $tuneNow -and (Set-CourseTune $h $tune)) { $tuneNow = $tuneKey }
            # An added track's scenery was sorted for its own game's cameras: with the game's visibility
            # lists on, far scenery comes and goes with the camera. While such a track is raced, every
            # scenery node counts as visible ([0xA65794], as for the CamLab cameras; the camera block
            # only writes it when the camera changes, so this holds it).
            $allVisible = (-not $menu) -and $dir -ne 's'
            if ($allVisible) {
                $v = Read-GameInt $h 0xA65794
                if (-not $pvsHeld) { $pvsWas = $v; $pvsHeld = $true }
                if ($v -ne 1) { [Sr3Mem]::Write($h, 0xA65794, ([BitConverter]::GetBytes([int]1)), $true) }
            } elseif ($pvsHeld) {
                [Sr3Mem]::Write($h, 0xA65794, ([BitConverter]::GetBytes([int]$pvsWas)), $true); $pvsHeld = $false
            }
            # in a race: START takes a screenshot when it is let go, VIEW CHANGE held leaves the race (Step-Start)
            $buttons = Get-GameButtons $h
            $startDown = ($buttons -band 0x10) -ne 0; $viewDown = ($buttons -band 0x1000) -ne 0
            foreach ($act in (Step-Start $start $startDown $viewDown $menu (Get-Now))) {
                if ($act -eq 'grab') {
                    try {
                        $shotHeld = New-ScreenGrab
                        $shotInfo = $null
                        try { $shotInfo = Get-ShotInfo $h $base $name $dir $(if ($cur) { $cur.Title } else { '' }) (Get-Now) } catch { Log "Screenshot: no coordinates ($($_.Exception.Message))" }
                    } catch { Log "Screenshot failed: $($_.Exception.Message)"; Close-ScreenGrab $shotHeld; $shotHeld = $null; $start.HeldAt = $null }
                } elseif ($act -eq 'save' -and $shotHeld) {
                    try {
                        $shotDir = Join-Path (Split-Path -Parent $PSScriptRoot) 'Screenshots'; New-Item -ItemType Directory -Force $shotDir | Out-Null
                        $shotName = 'SR3_{0:yyyyMMdd_HHmmss}.png' -f $start.ShotAt
                        Save-ScreenGrab $shotHeld (Join-Path $shotDir $shotName) $shotInfo          # where the picture was taken (Get-ShotInfo)
                        $shotUntil = (Get-Now).AddSeconds(3); Log "Screenshot: $shotName"
                    } catch { Log "Screenshot failed: $($_.Exception.Message)" }
                    Close-ScreenGrab $shotHeld; $shotHeld = $null
                } elseif ($act -eq 'drop' -and $shotHeld) { Close-ScreenGrab $shotHeld; $shotHeld = $null }  # that START began a new game
                elseif ($act -eq 'exit') { Request-RaceExit $h (Get-Now); if ($script:RaceExit) { Undo-ViewStep $h $base } }
            }
            if ($script:RaceExit) { Step-RaceExit $h (Get-Now) }
            Show-WatchdogNews
            if ($script:Handling -and $script:Handling.Flavors.Count -and (Get-FrontWindow) -eq (Read-GamePtr $h $GameWindowVA)) {     # the handling keys (Set-Handling)
                foreach ($vk in $HandlingKeyCodes) {
                    $dn = Test-KeyDown $vk
                    if ($dn -and -not $keysDown[$vk]) {
                        $car = Get-KeyCar $h $base $menu; $lines = $null
                        if (-not $car) { $lines = @('No car yet', 'pick one on the car select') }
                        elseif ($HandlingKeys.ContainsKey($vk)) { $lines = Set-CarHandlingLive $h $car $HandlingKeys[$vk] }
                        else { $lines = Show-CarHandling $h $car }
                        if ($lines) { $labelLines = $lines; $labelUntil = (Get-Now).AddSeconds(2.5) }
                    }
                    $keysDown[$vk] = $dn
                }
            }
            if ((Get-FrontWindow) -eq (Read-GamePtr $h $GameWindowVA)) {   # Ctrl+Scroll Lock: the watchdog now (Request-Watchdog), its label
                $dn = (Test-KeyDown 0x11) -and (Test-KeyDown 0x91)
                if ($dn -and -not $watchKeyWas) { $labelLines = Request-Watchdog $game; Log "Watchdog key: $($labelLines -join ', ')."; $labelUntil = (Get-Now).AddSeconds(2.5) }
                $watchKeyWas = $dn
            }
            if ($labelUntil -gt (Get-Now)) {                          # a handling (or watchdog) key's label, over everything else for 2.5 s
                $lt = $labelLines -join '|'
                if ($lt -ne $shown) { [Sr3Mem]::Write($h, $text, (Str $labelLines[0] 48), $true); [Sr3Mem]::Write($h, $text + 0x80, (Str $labelLines[1] 64), $true); $shown = $lt }
                [Sr3Mem]::Write($h, $base + 0x50, ([BitConverter]::GetBytes([int]$text)), $true)
                [Sr3Mem]::Write($h, $base + 0xE60, ([BitConverter]::GetBytes([uint32]4288479034)), $true)
                [Sr3Mem]::Write($h, $base + 0x2268, ([BitConverter]::GetBytes([int]($text + 0x80))), $true)
                [Sr3Mem]::Write($h, $base + 0xFA0, ([BitConverter]::GetBytes([int]1)), $true)
                [Sr3Mem]::Write($h, $base + 0x10, ([BitConverter]::GetBytes([int]20)), $true)
                $showing = $true
            } elseif ($mode) {
                $title = 'Classic: ' + $slots[$ClassicSlot][$choice[$ClassicSlot]].Title
                if ($title -ne $shown) { [Sr3Mem]::Write($h, $text, (Str $title 48), $true); $shown = $title }
                [Sr3Mem]::Write($h, $base + 0x50, ([BitConverter]::GetBytes([int]$text)), $true)
                [Sr3Mem]::Write($h, $base + 0xE60, ([BitConverter]::GetBytes([uint32]$(if ($choice[$ClassicSlot]) { 4288479034 } else { 4294967295 }))), $true)
                [Sr3Mem]::Write($h, $base + 0x2268, ([BitConverter]::GetBytes([int]($text + 0x40))), $true)
                [Sr3Mem]::Write($h, $base + 0xFA0, ([BitConverter]::GetBytes([int]1)), $true)
                [Sr3Mem]::Write($h, $base + 0x10, ([BitConverter]::GetBytes([int]20)), $true)
                $showing = $true
            } elseif ($stage -and $list) {
                $title = $list[$choice[$name]].Title
                if ($title -ne $shown) { [Sr3Mem]::Write($h, $text, (Str $title 48), $true); $shown = $title }
                [Sr3Mem]::Write($h, $base + 0x50, ([BitConverter]::GetBytes([int]$text)), $true)                                   # the popup's first line
                [Sr3Mem]::Write($h, $base + 0xE60, ([BitConverter]::GetBytes([uint32]$(if ($choice[$name]) { 4288479034 } else { 4294967295 }))), $true)
                [Sr3Mem]::Write($h, $base + 0x2268, ([BitConverter]::GetBytes([int]($text + 0x40))), $true)                        # its second line
                [Sr3Mem]::Write($h, $base + 0xFA0, ([BitConverter]::GetBytes([int]1)), $true)
                [Sr3Mem]::Write($h, $base + 0x10, ([BitConverter]::GetBytes([int]20)), $true)
                $showing = $true
            } elseif ($shotUntil -gt (Get-Now)) {
                if ($shotName -ne $shown) { [Sr3Mem]::Write($h, $text, (Str $shotName 48), $true); $shown = $shotName }
                [Sr3Mem]::Write($h, $base + 0x50, ([BitConverter]::GetBytes([int]$text)), $true)
                [Sr3Mem]::Write($h, $base + 0xE60, ([BitConverter]::GetBytes([uint32]4294967295)), $true)
                [Sr3Mem]::Write($h, $text + 0x78, [byte[]]@(0, 0), $true)                                            # an empty second line (0 here would bring the popup's own hint back)
                [Sr3Mem]::Write($h, $base + 0x2268, ([BitConverter]::GetBytes([int]($text + 0x78))), $true)
                [Sr3Mem]::Write($h, $base + 0xFA0, ([BitConverter]::GetBytes([int]1)), $true)
                [Sr3Mem]::Write($h, $base + 0x10, ([BitConverter]::GetBytes([int]20)), $true)
                $showing = $true
            } elseif ($showing) {
                [Sr3Mem]::Write($h, $base + 0x10, ([BitConverter]::GetBytes([int]0)), $true)
                [Sr3Mem]::Write($h, $base + 0xFA0, ([BitConverter]::GetBytes([int]0)), $true)
                [Sr3Mem]::Write($h, $base + 0x2268, ([BitConverter]::GetBytes([int]0)), $true)
                $showing = $false
            }
            Sync-RaceFlavor $h                                            # every car of the next race on the player's car's handling
            if ($wasMenu -and -not $menu) {                               # a race starts
                if ($script:RaceFlavor) { Log "Handling: this race on $($FlavorTitles[$script:RaceFlavorName]), the player's car's ($($script:RaceFlavor -replace '/.*$', '')); every car in it loads that handling." }
            }
            $wasDown = $down; $wasMenu = $menu
            Start-Sleep -Milliseconds 15
        }
    }
    catch { if (-not $game.HasExited) { Log "Alternative tracks stopped: $($_.Exception.Message)" } }
    finally { [Sr3Mem]::Close($h) }
    Wait-GameExit $game
}

# The arcade's menus count down and then choose for you. The owner wants no timers in the menus at all (2026-10-14).
# The time is a constant in each menu's code, compared with the time the menu has been up and handed to the countdown
# on screen: the mode select, the accept-challenge prompt, the three car select pages (one per mode), the Classic car
# select, the track select and the link-play car select have 15 s, the three gearbox pages 10 s, the name entry of
# the scoreboard 30 s. All of them are set to $MenuTimerMs (24 days) while the game runs, and the countdown itself
# (the frontend's flash_fade_timer element, on six screens) is not drawn: its draw routine leaves at once, so no
# digits and no last-seconds beeps. Left as they were: the retire screen (5 s, 15 s when it offers a continue), which
# is a results screen that would otherwise wait for a button.
$MenuTimerMs = 0x7FFFFFFF
$MenuTimerSites = [ordered]@{
    0x63D900 = 15000; 0x6480FA = 15000; 0x6481A5 = 15000; 0x648333 = 15000; 0x648563 = 15000; 0x64862D = 15000; 0x648795 = 15000
    0x6487B0 = 15000; 0x6488A2 = 15000; 0x648933 = 15000; 0x648AD2 = 15000; 0x648B7B = 15000; 0x64E209 = 15000; 0x64E2A6 = 15000
    0x650B84 = 15000; 0x65B489 = 15000; 0x666223 = 15000; 0x666C39 = 15000
    0x64801D = 10000; 0x64844F = 10000; 0x648A2D = 10000; 0x6667CB = 10000                 # the gearbox pages and their countdown
    0x644492 = 30000; 0x65B551 = 30000                                                      # the name entry's deadline and its countdown
}
$TimerDrawSite = 0x61827A; $TimerDrawOrig = '0f84f8020000'; $TimerDrawNew = 'e9f902000090'   # je -> jmp to the routine's end (0x618578)
function Set-MenuTimers($game) {
    $h = [Sr3Mem]::Open($game.Id); $n = 0; $hidden = $false
    try {
        foreach ($e in $MenuTimerSites.GetEnumerator()) {        # (an [ordered] table indexed with an int takes it as a position)
            $a = [long]$e.Key; $b = [Sr3Mem]::Read($h, $a, 4); if (-not $b) { continue }
            $v = [BitConverter]::ToInt32($b, 0)
            if ($v -eq $e.Value -or $v -eq 120000) { [Sr3Mem]::Write($h, $a, ([BitConverter]::GetBytes([int]$MenuTimerMs)), $true); $n++ }   # 120000: set by an older PLAY.bat
            elseif ($v -eq $MenuTimerMs) { $n++ }
        }
        $cur = [Sr3Mem]::Read($h, $TimerDrawSite, 6)
        if (Same $cur (HexToBytes $TimerDrawOrig)) {
            [Sr3Mem]::Suspend($h); try { [Sr3Mem]::Write($h, $TimerDrawSite, (HexToBytes $TimerDrawNew), $false) } finally { [Sr3Mem]::Resume($h) }
        }
        $hidden = Same ([Sr3Mem]::Read($h, $TimerDrawSite, 6)) (HexToBytes $TimerDrawNew)
        # (2026-10-07: a brighter stand-in for the light-map fallback 0xFF808080 was tried at 0x5001A6, 0x51186C, 0x5D6441 and
        # 0x640D89. It washed the whole picture out and did not help the cars: 0x80 is the neutral value. The cars were dark
        # because the road's overlay page texture, a sun / shadow map, was written as all shadow. Fixed in the track.)
    } catch { Log "Menu timers: $($_.Exception.Message)" } finally { [Sr3Mem]::Close($h) }
    Log ("Menu timers: {0} of {1} off; countdown {2}." -f $n, $MenuTimerSites.Count, $(if ($hidden) { 'hidden' } else { 'NOT hidden (unexpected bytes)' }))
}

# Every car in every car select (the owner, 2026-10-14). The game fills its car selector from the car library of the
# ArcadeDatabase with one of three routines: 0x600790 the cars with neither flag (Championship, Quick Race: the six SR3
# cars), 0x6006F0 the cars with the Classic flag (Classic: ST205, Delta), 0x600740 the bonus cars (the secret-car page:
# Bowler, Enduro). The first two get a jump to a routine of ours that adds the mode's own cars first and then every other
# car of the library, in its order; the secret-car page keeps its two. Source and notes: tools\build_carlist.py. The
# selector holds up to 38 cars; the library is a list read from the database file, with no fixed size.
$CarListCode = 'ba00000000eb0eba01000000eb07ba02000000eb0085ff746256535589d38b0789f9ff505831eda150a8b2008b700483c608743e31c0837e14007405b802000000837e10007405b80100000031c939d80f95c139e975158b46048b4e408b176a006a006aff505189f9ff52548b3685f675c24583fd0272af5d5b5ec3'
$CarListSites = @(@(0x600790, 0, '85ff74518b'), @(0x6006F0, 7, '85ff74408b'))      # site, entry in our routine, the game's bytes there
$CardHookCode = '85ed7433e8000000005e83c63d803e00742589e989f28a013a027516414284c075f48b4e208b098b4424145f5e5d89085bc383c624ebd68b4424145f5e5dc700ffffffff5bc3'
$CardHookExit = '8b4424145f5e5dc700ffffffff5bc3'
$ExtraCards = @(,@('CARSLIDE_HORNET_GRAVEL_1', 0x72870C, 'HORNET.wmv'))  # card name, the game's video handle cell it borrows until its own video is open (0x72870C: the TV-static loop), its own video in frontend\PC\Videos (Open-CarCards); (the comma keeps a one-entry list a list of lists)
$CardCells = 0x800                                         # in the card routine's cave: the handle cells of the cars' own videos
function Set-CarLists($game) {
    $h = [Sr3Mem]::Open($game.Id); $n = 0; $late = $false; $script:CarListPending = $null
    try {
        $todo = @()
        foreach ($s in $CarListSites) {
            $cur = [Sr3Mem]::Read($h, $s[0], 5)
            if (Same $cur (HexToBytes $s[2])) { $todo += ,$s }
            elseif ($cur -and $cur[0] -eq 0xE9) { $n++ }                                  # already ours (PLAY.bat run again on a running game)
            else { Log ("Car lists: unexpected bytes at 0x{0:X}; that list is left as it is." -f $s[0]) }
        }
        if ($todo.Count) {
            $cave = [Sr3Mem]::Alloc($h, 0x1000); [Sr3Mem]::Write($h, $cave, (HexToBytes $CarListCode), $true)
            $script:CarListPending = @{ Cave = $cave; Todo = $todo }
            if (Complete-CarLists $h) { $n += $todo.Count }
            else { $late = $true }
        }
        # A car the game does not know by name (an added one, e.g. a Daytona car) gets the speedo's top speed like the ten:
        # 0x599A20 compares the car's name with the ten and sets vehicle +0x1708 for each; for any other name it skipped the
        # last write (jne at 0x599D7A), so +0x1708 stayed 0 and the speedo showed 0. All ten values are made the same way.
        $sp = [Sr3Mem]::Read($h, 0x599D78, 4)
        if (Same $sp (HexToBytes '3bc87510')) { [Sr3Mem]::Write($h, 0x599D7A, [byte[]]@(0x90, 0x90), $false) }
        # ... and a card on the car select: the card is the video named CARSLIDE_<FOLDER>_GRAVEL_1 in the game's table of 18
        # (0x728630, looked up by 0x61C2C0); a name not in it got no video (a blank card). The lookup's not-found exit
        # (0x61C30B) now jumps to tools\build_cardhook.py's routine, which gives the cars below a video handle of the
        # game's table (a stand-in until a car has its own video), and -1 as before for any other name.
        $ex = [Sr3Mem]::Read($h, 0x61C30B, 15)
        if (Same $ex (HexToBytes $CardHookExit)) {
            $list = New-Object Collections.Generic.List[byte]
            foreach ($c in $ExtraCards) { $nm = [Text.Encoding]::ASCII.GetBytes($c[0]); $list.AddRange($nm); $list.AddRange((New-Object byte[] (32 - $nm.Length))); $list.AddRange([BitConverter]::GetBytes([int]$c[1])) }
            $list.AddRange((New-Object byte[] 36))
            $cc = [Sr3Mem]::Alloc($h, 0x1000); [Sr3Mem]::Write($h, $cc, ((HexToBytes $CardHookCode) + $list.ToArray()), $true)
            $j = CallTo 0x61C30B $cc; $j[0] = 0xE9
            [Sr3Mem]::Suspend($h); try { [Sr3Mem]::Write($h, 0x61C30B, $j, $false) } finally { [Sr3Mem]::Resume($h) }
        }
    } catch { Log "Car lists: $($_.Exception.Message)" } finally { [Sr3Mem]::Close($h) }
    if ($late) { Log 'Car lists: a game was started before the launcher was ready, so its car selects keep their own cars; every car in every mode from the next game on.' }
    else { Log $(if ($n -eq $CarListSites.Count) { 'Car lists: every car in every mode (each mode''s own cars first).' } else { "Car lists: $n of $($CarListSites.Count) changed." }) }
}
# The jumps into the car-list routine go in only while the menus' scene does not exist ([0x9D6E3C] = number of scenes,
# [0x9D6E50] = the scene). The scene is built when a game starts (0x64DA20 -> 0x62DD00), and its car nodes take their cards
# from the fill routines then (0x62CE10 / 0x62CE60 / 0x62CEB0: a selector on the stack, filled, made into the node's list),
# while the selector itself is refilled each time the car select comes up (0x662338 -> 0x606930 / 0x6069D0). With the
# jumps put in between the two, the selector had every car but the node only the mode's own (Classic: 2), and the game's
# move sound / scroll code (0x628DF0, 0x622270) indexes the node's list with the selector's cursor without a check: past
# the Lancia and back, item 2 of a 2-item list is null and 0x628EA9 reads [0 + 0x80] (in game 2026-10-14). So a game
# started before the launcher was ready keeps the game's own lists; Watch-Tracks completes this when that game's menus close.
function Complete-CarLists($h) {
    $p = $script:CarListPending
    if (-not $p) { return $true }
    $done = $false
    [Sr3Mem]::Suspend($h)
    try {
        $sc = [Sr3Mem]::Read($h, 0x9D6E3C, 4); $sp = [Sr3Mem]::Read($h, 0x9D6E50, 4)
        if ($sc -and $sp -and [BitConverter]::ToInt32($sc, 0) -eq 0 -and [BitConverter]::ToInt32($sp, 0) -eq 0) {
            foreach ($s in $p.Todo) { $j = CallTo $s[0] ($p.Cave + $s[1]); $j[0] = 0xE9; [Sr3Mem]::Write($h, $s[0], $j, $false) }   # jmp rel32
            $done = $true
        }
    } finally { [Sr3Mem]::Resume($h) }
    if ($done) { $script:CarListPending = $null }
    return $done
}
# An added car's own card video (frontend\PC\Videos\<file>, $ExtraCards). The game has 20 video objects (0x16C bytes at
# 0xAD2F90) and fills 18: the 17 of its table that 0x621600 loads and LOADING_TEXTURE (0x621500, once). Its allocator
# 0x4DE430 takes the first object whose +4 is 0 and never frees one, so objects 19 and 18 stay empty. Each car with a file
# gets one of them, opened by the camera block's REOPEN on the game's own thread (as a stage card's other track is), and its
# entry in the card routine's list then names a cell holding that object. Without the file, or if the open fails, the card
# keeps its stand-in. Run before the first menus: the car select looks its cards up when its pages are built (at the first
# menus, then at each new game). The stand-in's video gives the folder the game reads its videos from.
function Open-CarCards($h, [long]$base) {
    $j = [Sr3Mem]::Read($h, 0x61C30B, 5)
    if (-not $j -or $j[0] -ne 0xE9) { return }
    $cc = 0x61C30B + 5 + [BitConverter]::ToInt32($j, 1)                # the card routine (Set-CarLists)
    $list = $cc + $CardHookCode.Length / 2
    $obj = 19
    for ($i = 0; $i -lt $ExtraCards.Count; $i++) {
        $c = $ExtraCards[$i]
        if ($c.Count -lt 3 -or -not $c[2]) { continue }
        $entry = $list + 36 * $i
        if ((Read-GameString $h $entry 32) -ne $c[0]) { Log "Car cards: the card list in the game isn't this launcher's; $($c[0]) keeps its stand-in."; return }
        $stand = Read-GameInt $h $c[1]
        if ($stand -eq -1) {                                           # the game hasn't loaded its videos yet: have it do so now
            [Sr3Mem]::Write($h, $base + 0x2264, ([BitConverter]::GetBytes([int]1)), $true)
            for ($t = 0; $t -lt 400 -and (Read-GameInt $h $c[1]) -eq -1; $t++) { Start-Sleep -Milliseconds 25 }
            $stand = Read-GameInt $h $c[1]
        }
        if ($stand -lt 0 -or $stand -ge 20) { return $false }         # still not loaded: tried again when the menus come up
        $path = (Read-GameString $h (0xAD2F90 + 0x16C * $stand + 0xC) 255) -replace '[^\\]+\.wmv$', $c[2]
        $onDisk = if ([IO.Path]::IsPathRooted($path)) { $path } else { Join-Path (Split-Path -Parent $script:GameExePath) $path }
        if ($path -notmatch '\\[A-Za-z0-9_]+\.wmv$' -or -not (Test-Path -LiteralPath $onDisk)) { continue }
        $have = -1                                                     # already open (PLAY.bat run again on a running game)
        for ($k = 18; $k -lt 20; $k++) { if ((Read-GameInt $h (0xAD2F90 + 0x16C * $k + 4)) -and (Read-GameString $h (0xAD2F90 + 0x16C * $k + 0xC) 255) -eq $path) { $have = $k } }
        if ($have -lt 0) {
            while ($obj -ge 18 -and (Read-GameInt $h (0xAD2F90 + 0x16C * $obj + 4))) { $obj-- }
            if ($obj -lt 18) { Log "Car cards: no spare video object for $($c[2]); the card keeps its stand-in."; return }
            [Sr3Mem]::Write($h, $base + 0x2500, (Str $path 256), $true)
            [Sr3Mem]::Write($h, $base + 0x2274, ([BitConverter]::GetBytes([int]($base + 0x2500))), $true)
            [Sr3Mem]::Write($h, $base + 0x2270, ([BitConverter]::GetBytes([int]($obj + 1))), $true)
            for ($t = 0; $t -lt 3000 -and -not $proc.HasExited -and (Read-GameInt $h ($base + 0x2270)) -ne 0; $t++) { Start-Sleep -Milliseconds 10 }
            if ((Read-GameInt $h ($base + 0x2270)) -ne 0) { Log "Car cards: video request still pending; retrying when menus open."; return $false }
            if (-not (Read-GameInt $h (0xAD2F90 + 0x16C * $obj + 4))) { Log "Car cards: the game didn't open $path; the card keeps its stand-in."; continue }
            $have = $obj; $obj--
        }
        Write-GameInt $h ($cc + $CardCells + 4 * $i) $have
        Write-GameInt $h ($entry + 32) ($cc + $CardCells + 4 * $i)
        Log "Car cards: $($c[0]) plays $path."
    }
}

# Handling flavors (docs\kb\28_handling_flavors.md; the owner, 2026-10-14): each car drives with SEGA's handling ("sr3") or
# with a flavor (SRC = SEGA Rally Championship 1995, Realism, ...). A flavor is a folder of car files
# Main_release\car<digit>\ (and, if it has one, a grip file SurfacePairEffect<digit>\surfacepairdata_xdata.sbf), built on the
# owner's machine from SEGA's own files by tools\handling\build_flavor.py; nothing of SEGA's ships. handling.json next to
# PLAY.bat (example: handling.example.json) says which car drives which flavor:
#   {"version": 1, "default": "sr3", "cars": {"ST205": "src"}, "flavors": {"src": {"digit": "1", "grip_file": true}}}
# No file, or "default": "sr3" and no car on a flavor: nothing is patched.
# The race loader 0x5C5D30 makes each car's data path when a race loads (so a change takes effect at the next race):
#   the ten known cars: "\main_release\cars\%s%s_data" (0x6C630C, pushed at 0x5C6144) with "bespoke";
#   any other car (Hornet): the same pattern at 0x6C6360 with "gravel" (<name>gravel_data);
#   the grip file: "\SurfacePairEffects\surfacepairdata_xdata" (0x6C6164, read by the race loader 0x5C6290 each race).
# - Every known car on one flavor: the 's' of "cars" (0x6C631D) becomes the flavor's digit (one character, as the tracks).
# - A mix: `push 0x6C630C` becomes `call` to tools\build_flavorhooks.py's CARPATH routine, which compares the car's name
#   (ebp) with the ten names of 0x5C6000 and pushes its own pattern with that car's digit (its flag), or SEGA's 0x6C630C.
# - The added cars: the 's' at 0x6C6371, one flavor for all of them (they share that pattern).
# - The grip file: the 's' of "Effects" (0x6C6176) when a flavor in use has one; one grip file per race (the first such).
# A flavor whose folder or a car whose file is missing: that car keeps SEGA's file (a Log line), never a load of a file that
# is not there. A flavor's grip file only changes its own tyre type's records (SRC: Tyre_Road), so SR3's cars are unaffected.
$HandlingCarNames = 'C4', 'RSFocus', 'SubaruImpreza', 'SX4', 'MitsubishiEvo', '207', 'ST205', 'Delta_HF', 'Bowler', 'Enduro'   # car library ids 0..9
$CarPathCode = '80626c00020000000000000084626c00080000000000000090626c00050000000000000098626c000600000000000000a0626c000700000000000000a8626c000300000000000000ac626c000d00000000000000bc626c000300000000000000c0626c000600000000000000c8626c000d00000000000000000000005c6d61696e5f72656c656173655c636172315c257325735f6461746100000000000000005657e8000000005f8db759ffffff8b0685c07427ff76045055b810f44a00ffd083c40c85c0750f8a460884c0740d8847e68d47d5eb0a83c60cebd3b80c636c005f5e870424ffe0'
$CarPathEntry = 0xA0                                                           # flags (folder digit, 0 = SEGA's) at +8 + 12 x i, in this order:
$CarPathOrder = 'C4', 'Delta_HF', 'ST205', 'Enduro', 'RSFocus', '207', 'SubaruImpreza', 'SX4', 'Bowler', 'MitsubishiEvo'
$CarPathSite = 0x5C6144; $CarPathBytes = '680c636c00'
$CarDirSite = 0x6C631D; $AddedCarDirSite = 0x6C6371; $GripDirSite = 0x6C6176
# Steering: SEGA's own for every handling. The steering-rate hook (a call at 0x5CFF32 to a routine of ours, 2026-10-15) was taken out on the
# owner's word the same night ("remove the rads tuning"); a game a launcher of that day had hooked gets SEGA's call back (Remove-SteerHook).
$SteerSite = 0x5CFF32; $SteerBytes = 'e8c98ce7ff'                                  # call 0x448C00
function Read-Handling([string]$gameExe) {
    $file = Join-Path $PSScriptRoot 'handling.json'
    if (-not $gameExe -or -not (Test-Path -LiteralPath $file)) { return $null }
    try { $j = [IO.File]::ReadAllText($file) | ConvertFrom-Json } catch { Log "Handling: $file can't be read; every car keeps SEGA's handling."; return $null }
    $gameDir = Split-Path -Parent $gameExe
    $default = 'sr3'; if ($j.default) { $default = "$($j.default)".ToLower() }
    $fl = @{}
    if ($j.flavors) {
        foreach ($p in $j.flavors.PSObject.Properties) {
            $k = $p.Name.ToLower(); $v = $p.Value; $d = "$($v.digit)"
            if ($k -eq 'sr3') { continue }
            if ($d -notmatch '^[1-9]$') { Log "Handling: flavor $k has no folder digit 1..9; skipped."; continue }
            $dir = Join-Path $gameDir "Main_release\car$d"
            if (-not (Test-Path -LiteralPath $dir)) { Log "Handling: flavor $k's folder Main_release\car$d is missing; skipped."; continue }
            $grip = $false
            if ($v.grip_file) {
                if (Test-Path -LiteralPath (Join-Path $gameDir "SurfacePairEffect$d\surfacepairdata_xdata.sbf")) { $grip = $true }
                else { Log "Handling: flavor $k's grip file SurfacePairEffect$d\surfacepairdata_xdata.sbf is missing; its cars keep SEGA's tyre grip." }
            }
            $fl[$k] = @{ Name = $k; Digit = $d; Dir = $dir; Grip = $grip }      # (steer_rate / steer_return_s / steer_linear of older files: ignored)
        }
    }
    $want = @{}
    if ($j.cars) { foreach ($p in $j.cars.PSObject.Properties) { $want[$p.Name.ToLower()] = "$($p.Value)".ToLower() } }
    $cars = [ordered]@{}                                              # car -> its data file name (SEGA's ten, then the added ones as the folder lists them)
    foreach ($c in $HandlingCarNames) { $cars[$c] = "$($c.ToLower())bespoke_data.sbf" }
    foreach ($f in @(Get-ChildItem -LiteralPath (Join-Path $gameDir 'Main_release\cars') -Filter '*gravel_data.sbf' -ErrorAction SilentlyContinue)) {
        $n = $f.Name -replace '(?i)gravel_data\.sbf$', ''
        if ($HandlingCarNames -notcontains $n) { $cars[$n] = $f.Name }   # an added car (SEGA's per-surface leftovers of the ten are skipped)
    }
    $plan = [ordered]@{}; $any = $false
    foreach ($c in @($cars.Keys)) {
        $f = $default; if ($want.ContainsKey($c.ToLower())) { $f = $want[$c.ToLower()] }
        if ($f -ne 'sr3') {
            if (-not $fl.ContainsKey($f)) { Log "Handling: $c asks for flavor $f, which is not available; it keeps SEGA's handling."; $f = 'sr3' }
            elseif (-not (Test-Path -LiteralPath (Join-Path $fl[$f].Dir $cars[$c]))) { Log "Handling: Main_release\car$($fl[$f].Digit) has no $($cars[$c]); $c keeps SEGA's handling."; $f = 'sr3' }
        }
        $plan[$c] = $f; if ($f -ne 'sr3') { $any = $true }
    }
    if (-not $any) { return $null }
    return @{ Plan = $plan; Flavors = $fl }
}
function Set-DirChar($h, [long]$va, [string]$ch, [string]$what) {
    $cur = [Sr3Mem]::Read($h, $va, 1)
    if (-not $cur -or -not ($cur[0] -eq 0x73 -or ($cur[0] -ge 0x31 -and $cur[0] -le 0x39))) { Log ("{0}: unexpected byte at 0x{1:X}; left as it is." -f $what, $va); return }
    if ($cur[0] -ne [byte][char]$ch) { [Sr3Mem]::Write($h, $va, [byte[]]@([byte][char]$ch), $true) }
}
function Set-Handling($game) {
    $script:Handling = Read-Handling $script:GameExePath; $script:CarPathCave = $null; $script:RaceFlavor = $null
    $cfg = $script:Handling
    if (-not $cfg) { $cfg = New-HandlingLive $script:GameExePath; $script:Handling = $cfg }      # nothing asked for, but a flavor is built: every car on SEGA's, ready for the keys
    $h = [Sr3Mem]::Open($game.Id)
    try {
        Remove-SteerHook $h
        # SRC turning port (option B, a669d4d) disabled after Bruno reported no steering in-game (2026-10-16).
        # SRC files use SR3's own turning chain; remove an earlier session's hook too. Game retest remains necessary.
        Remove-SrcPort $h
        $site = [Sr3Mem]::Read($h, $CarPathSite, 5)
        $hooked = $site -and $site[0] -eq 0xE8                       # ours already (PLAY.bat run again on a running game)
        if (-not $cfg) {                                              # nothing asked for: SEGA's paths (also undoes an earlier run)
            foreach ($a in $CarDirSite, $AddedCarDirSite, $GripDirSite) { Set-DirChar $h $a 's' 'Handling' }
            if ($hooked) { $cave = $CarPathSite + 5 + [BitConverter]::ToInt32($site, 1) - $CarPathEntry; for ($i = 0; $i -lt $CarPathOrder.Count; $i++) { [Sr3Mem]::Write($h, $cave + 8 + 12 * $i, [byte[]]@(0), $true) } }
            return
        }
        $plan = $cfg.Plan; $fl = $cfg.Flavors
        $one = @($HandlingCarNames | ForEach-Object { $plan[$_] } | Sort-Object -Unique)
        if ($one.Count -eq 1 -and -not $hooked -and -not $fl.Count) {   # (with a flavor built the per-car routine goes in, so the keys can change a car)
            $ch = 's'; if ($one[0] -ne 'sr3') { $ch = $fl[$one[0]].Digit; Log "Handling: every known car on flavor $($one[0]) (Main_release\car$ch)." }
            Set-DirChar $h $CarDirSite $ch 'Handling (known cars)'
        } else {
            $cave = $null
            if ($hooked) {
                $cave = $CarPathSite + 5 + [BitConverter]::ToInt32($site, 1) - $CarPathEntry
                if (-not (Same ([Sr3Mem]::Read($h, $cave + $CarPathEntry, 8)) ((HexToBytes $CarPathCode)[$CarPathEntry..($CarPathEntry + 7)]))) { Log 'Handling: the car path code holds a call that is not ours; per-car flavors are off.'; $cave = $null }
            } elseif (Same $site (HexToBytes $CarPathBytes)) {
                $cave = [Sr3Mem]::Alloc($h, 0x1000); [Sr3Mem]::Write($h, $cave, (HexToBytes $CarPathCode), $true)
                [Sr3Mem]::Suspend($h); try { [Sr3Mem]::Write($h, $CarPathSite, (CallTo $CarPathSite ($cave + $CarPathEntry)), $false) } finally { [Sr3Mem]::Resume($h) }
            } else { Log ("Handling: unexpected bytes at 0x{0:X}; per-car flavors are off." -f $CarPathSite) }
            if ($cave) {
                Set-DirChar $h $CarDirSite 's' 'Handling (known cars)'
                for ($i = 0; $i -lt $CarPathOrder.Count; $i++) {
                    $f = $plan[$CarPathOrder[$i]]; $b = 0; if ($f -ne 'sr3') { $b = [byte][char]$fl[$f].Digit }
                    [Sr3Mem]::Write($h, $cave + 8 + 12 * $i, [byte[]]@([byte]$b), $true)
                }
                Log ('Handling per car: ' + (($HandlingCarNames | ForEach-Object { "$_ $($plan[$_])" }) -join ', ') + '. A race runs every car on the player''s car''s handling.')
                $script:CarPathCave = $cave
            }
        }
        $added = @($plan.Keys | Where-Object { $HandlingCarNames -notcontains $_ })
        if ($added.Count) {
            $ao = @($added | ForEach-Object { $plan[$_] } | Sort-Object -Unique)
            if ($ao.Count -eq 1) { $ch = 's'; if ($ao[0] -ne 'sr3') { $ch = $fl[$ao[0]].Digit; Log "Handling: added cars ($($added -join ', ')) on flavor $($ao[0])." }; Set-DirChar $h $AddedCarDirSite $ch 'Handling (added cars)' }
            else { Set-DirChar $h $AddedCarDirSite 's' 'Handling (added cars)'; Log "Handling: the added cars ($($added -join ', ')) ask for different flavors; they keep SEGA's handling (they share one path pattern)." }
        }
        $used = @($plan.Values | Where-Object { $_ -ne 'sr3' } | Sort-Object -Unique)
        $grip = @($used | Where-Object { $fl[$_].Grip })
        $gch = 's'
        if ($grip.Count) { $gch = $fl[$grip[0]].Digit; if ($grip.Count -gt 1) { Log "Handling: $($grip -join ' and ') each have a grip file; one is read per race: $($grip[0])'s." } }
        Set-DirChar $h $GripDirSite $gch 'Handling (grip file)'
        if ($fl.Count) { Log ('Handling keys (game window in front): 1 / 2 / 3 = ' + (($FlavorTitles.Keys | ForEach-Object { $FlavorTitles[$_] + $(if ($_ -ne 'sr3' -and -not $fl.ContainsKey($_)) { ' (not built)' } else { '' }) }) -join ' / ') + ' for the highlighted car (car select) or your car; 0 = show.') }
    } catch { Log "Handling: $($_.Exception.Message)" } finally { [Sr3Mem]::Close($h) }
}
# Live handling keys (the owner, 2026-10-14: "Do A and A+, assign to num keys. Live labels for live value changes (camlab style)").
# While the game window is in front: 1 / 2 / 3 (number row or keypad) = SEGA Rally 3's own handling / SEGA Rally Championship's / Realism
# for one car: on the car select the highlighted one (camera block + 0x227C, CARSEL), anywhere else the player's car. It takes effect at
# that car's next race load (its flag in the per-car routine; the added cars' path character; the grip file's character) and is written
# to handling.json. 0 = show what the car has. Every key shows a label (the camera block's popup, as the camera names do).
$HandlingKeys = @{ 0x31 = 'sr3'; 0x32 = 'src'; 0x33 = 'realism'; 0x61 = 'sr3'; 0x62 = 'src'; 0x63 = 'realism' }
$InfoKeys = @(0x30, 0x60)
$CarTitles = @{ C4 = 'Citroen C4 WRC'; RSFocus = 'Ford Focus RS WRC 07'; SubaruImpreza = 'Subaru Impreza WRC2008'; SX4 = 'Suzuki SX4 WRC'; MitsubishiEvo = 'Mitsubishi Lancer Evolution X'; '207' = 'Peugeot 207 Super 2000'; ST205 = 'Toyota Celica ST205'; Delta_HF = 'Lancia Super Delta HF integrale'; Bowler = 'Bowler Nemesis'; Enduro = 'McRae Enduro' }
function Get-CarTitle([string]$car) { if ($CarTitles.ContainsKey($car)) { return $CarTitles[$car] }; return (Get-Culture).TextInfo.ToTitleCase($car) }      # the labels' names: the menu's
$HandlingKeyCodes = @(0x31, 0x32, 0x33, 0x61, 0x62, 0x63) + $InfoKeys                     # in this order (a hashtable's keys come in no set order; pc_live.c goes through them the same way)
$FlavorTitles = [ordered]@{ sr3 = "SEGA Rally 3's own"; src = 'SEGA Rally Championship'; realism = 'Realism' }
$DefaultFlavors = [ordered]@{ src = @{ Digit = '1'; Grip = $true }; realism = @{ Digit = '2'; Grip = $false } }
# no handling.json (or nothing on a flavor): the flavors that are built, every car on SEGA's handling; $null when none is built
function New-HandlingLive([string]$gameExe) {
    if (-not $gameExe) { return $null }
    $gameDir = Split-Path -Parent $gameExe; $fl = @{}
    foreach ($k in $DefaultFlavors.Keys) {
        $v = $DefaultFlavors[$k]; $dir = Join-Path $gameDir "Main_release\car$($v.Digit)"
        if (@(Get-ChildItem -LiteralPath $dir -Filter '*_data.sbf' -ErrorAction SilentlyContinue).Count) {
            $fl[$k] = @{ Name = $k; Digit = $v.Digit; Dir = $dir; Grip = ($v.Grip -and (Test-Path -LiteralPath (Join-Path $gameDir "SurfacePairEffect$($v.Digit)\surfacepairdata_xdata.sbf"))) }
        }
    }
    if (-not $fl.Count) { return $null }
    $plan = [ordered]@{}; foreach ($c in $HandlingCarNames) { $plan[$c] = 'sr3' }
    foreach ($f in @(Get-ChildItem -LiteralPath (Join-Path $gameDir 'Main_release\cars') -Filter '*gravel_data.sbf' -ErrorAction SilentlyContinue)) {
        $n = $f.Name -replace '(?i)gravel_data\.sbf$', ''; if ($HandlingCarNames -notcontains $n) { $plan[$n] = 'sr3' }
    }
    return @{ Plan = $plan; Flavors = $fl }
}
# handling.json as the settings app writes it (default = the handling most of SEGA's ten have, cars = the others)
function Save-Handling {
    $cfg = $script:Handling; if (-not $cfg) { return }
    $known = @($HandlingCarNames | ForEach-Object { $cfg.Plan[$_] })
    $default = @($known | Group-Object | Sort-Object Count -Descending)[0].Name
    $cars = [ordered]@{}; foreach ($c in @($cfg.Plan.Keys | Sort-Object)) { if ($cfg.Plan[$c] -ne $default) { $cars[$c] = $cfg.Plan[$c] } }
    $flv = [ordered]@{}
    foreach ($k in $DefaultFlavors.Keys) {
        $v = $DefaultFlavors[$k]; $flv[$k] = [ordered]@{ digit = $v.Digit; grip_file = [bool]$v.Grip }
    }
    try { [IO.File]::WriteAllText((Join-Path $PSScriptRoot 'handling.json'), ([ordered]@{ version = 1; default = $default; cars = $cars; flavors = $flv } | ConvertTo-Json -Depth 4)) }
    catch { Log "Handling: handling.json can't be written: $($_.Exception.Message)" }
}
# the car library's name of a car id: SEGA's ten by their file names, an added car by its node's LANG_ID_<NAME> (handling.json's name for it)
function Get-HandlingCarName($h, [int]$id) {
    if ($id -ge 0 -and $id -lt $HandlingCarNames.Count) { return $HandlingCarNames[$id] }
    $p = Read-GamePtr $h 0xB2A850; if (-not $p) { return $null }
    $n = (Read-GamePtr $h ($p + 4)) + 8
    for ($i = 0; $i -lt 64 -and $n -gt 8; $i++) {
        if ((Read-GameInt $h ($n + 4)) -eq $id) { return (Get-AddedCarName $h $n) }
        $n = Read-GamePtr $h $n
    }
    return $null
}
function Get-AddedCarName($h, [long]$node) {
    $s = Read-GameString $h ($node + 0x40) 32
    if ($s -notmatch '^[A-Za-z0-9_]+$') { $q = Read-GamePtr $h ($node + 0x40); if ($q) { $s = Read-GameString $h $q 32 } }
    $s = $s -replace '^(?i)LANG_ID_', ''
    foreach ($k in @($script:Handling.Plan.Keys)) { if ($k -ieq $s) { return $k } }
    return $s.ToLower()
}
# the car a key is for: the highlighted one on the car select, else the player's car (its library node, set on the car select)
function Get-KeyCar($h, [long]$base, [bool]$menu) {
    if ($menu) { $id = Read-GameInt $h ($base + 0x227C); if ($id -ge 0) { return (Get-HandlingCarName $h $id) } }
    $node = Read-GamePtr $h (0x9DBDA0 + 0xC); if (-not $node) { return $null }
    return (Get-HandlingCarName $h (Read-GameInt $h ($node + 4)))
}
# a car on a handling: its flag in the per-car routine (SEGA's ten) or the added cars' character, the grip file's character; handling.json
function Set-CarHandlingLive($h, [string]$car, [string]$f) {
    $cfg = $script:Handling; $fl = $cfg.Flavors
    if ($f -ne 'sr3' -and -not $fl.ContainsKey($f)) { return @("$($FlavorTitles[$f]) isn't built", 'build it in the settings app: Options, Handling...') }
    $known = $HandlingCarNames -contains $car
    if ($known) {
        if (-not $script:CarPathCave) { return @('Handling per car is off', 'see play.log') }
        $i = [Array]::IndexOf($CarPathOrder, $car); $b = 0; if ($f -ne 'sr3') { $b = [byte][char]$fl[$f].Digit }
        if ($f -ne 'sr3' -and -not (Test-Path -LiteralPath (Join-Path $fl[$f].Dir "$($car.ToLower())bespoke_data.sbf"))) { return @("$($FlavorTitles[$f]): no file", "$(Get-CarTitle $car) keeps its handling") }
        [Sr3Mem]::Write($h, $script:CarPathCave + 8 + 12 * $i, [byte[]]@([byte]$b), $true)
    } else {
        if ($f -ne 'sr3' -and -not (Test-Path -LiteralPath (Join-Path $fl[$f].Dir "$($car.ToLower())gravel_data.sbf"))) { return @("$($FlavorTitles[$f]): no file", "$(Get-CarTitle $car) keeps its handling") }
        foreach ($c in @($cfg.Plan.Keys)) { if ($HandlingCarNames -notcontains $c) { $cfg.Plan[$c] = $f } }       # (the added cars share one path pattern)
        $ch = 's'; if ($f -ne 'sr3') { $ch = $fl[$f].Digit }; Set-DirChar $h $AddedCarDirSite $ch 'Handling (added cars)'
    }
    $cfg.Plan[$car] = $f
    $grip = @($cfg.Plan.Values | Where-Object { $_ -ne 'sr3' -and $fl[$_].Grip } | Sort-Object -Unique)
    $gch = 's'; if ($grip.Count) { $gch = $fl[$grip[0]].Digit }; Set-DirChar $h $GripDirSite $gch 'Handling (grip file)'
    $script:RaceFlavor = $null                                        # Sync-RaceFlavor writes the race's flags again
    Save-Handling; Log "Handling: $car on $f (from its next race)."
    return @("Handling: $($FlavorTitles[$f])", "$(Get-CarTitle $car), from its next race")
}
# The race's handling is the player's car's (the owner, 2026-10-14: "only if the 'pace' applies to all cars in the race
# (balance)"): every car of a race loads the files of the player's car's flavor, the computer's cars too. The race loader
# makes every car's path through the per-car routine at 0x5C6144, so all ten flags, the added cars' character and the grip
# file's character are set to that one flavor (a car with no file in it keeps SEGA's). The player's car is the library node
# [0x9DBDA0 + 0xC], set when the car select is confirmed (0x5AF760), before the gearbox page and the race load. Watch-Tracks
# runs this every pass; it writes only when the player's car or its flavor changed (a key, the next car select).
function Sync-RaceFlavor($h) {
    $cfg = $script:Handling; if (-not $cfg -or -not $script:CarPathCave) { return }
    $node = Read-GamePtr $h (0x9DBDA0 + 0xC); if (-not $node) { return }
    $id = Read-GameInt $h ($node + 4); $car = Get-HandlingCarName $h $id; if (-not $car) { return }
    $f = $cfg.Plan[$car]; if (-not $f -or ($f -ne 'sr3' -and -not $cfg.Flavors.ContainsKey($f))) { $f = 'sr3' }
    if ("$car/$f" -eq $script:RaceFlavor) { return }
    $fl = $cfg.Flavors
    for ($i = 0; $i -lt $CarPathOrder.Count; $i++) {
        $b = 0; if ($f -ne 'sr3' -and (Test-Path -LiteralPath (Join-Path $fl[$f].Dir "$($CarPathOrder[$i].ToLower())bespoke_data.sbf"))) { $b = [byte][char]$fl[$f].Digit }
        [Sr3Mem]::Write($h, $script:CarPathCave + 8 + 12 * $i, [byte[]]@([byte]$b), $true)
    }
    $ch = 's'
    if ($f -ne 'sr3') {                                               # the added cars share one pattern: the flavor only if it has a file for each
        $added = @($cfg.Plan.Keys | Where-Object { $HandlingCarNames -notcontains $_ })
        if (@($added | Where-Object { -not (Test-Path -LiteralPath (Join-Path $fl[$f].Dir "$($_.ToLower())gravel_data.sbf")) }).Count -eq 0) { $ch = $fl[$f].Digit }
    }
    Set-DirChar $h $AddedCarDirSite $ch 'Handling (added cars)'
    $gch = 's'; if ($f -ne 'sr3' -and $fl[$f].Grip) { $gch = $fl[$f].Digit }; Set-DirChar $h $GripDirSite $gch 'Handling (grip file)'
    $script:RaceFlavor = "$car/$f"; $script:RaceFlavorName = $f
}
function Show-CarHandling($h, [string]$car) {
    $f = $script:Handling.Plan[$car]; if (-not $f) { $f = 'sr3' }
    return @("Handling: $($FlavorTitles[$f])", "$(Get-CarTitle $car)")
}
# SEGA's call at 0x5CFF32 back in place when a launcher of 2026-10-15 left its steering-rate routine there (PLAY.bat run again on a running game)
function Remove-SteerHook($h) {
    $a = [Sr3Mem]::Read($h, $SteerSite, 5); if (-not $a -or (Same $a (HexToBytes $SteerBytes)) -or $a[0] -ne 0xE8) { return }
    [Sr3Mem]::Suspend($h); try { [Sr3Mem]::Write($h, $SteerSite, (HexToBytes $SteerBytes), $false) } finally { [Sr3Mem]::Resume($h) }
    Log 'Steering: the steering-rate routine of an earlier launcher taken out; SEGA''s own steering.'
}
# SRC turning (2026-10-15; docs\kb\29_src_steering_code.md section 12): SEGA Rally Championship's turning, read from its
# code, for the cars on the SRC files. A routine of ours runs after every vehicle step (CVehicle vtable 0x678864 slot 5,
# the entry at 0x678878 = 0x45C820) and, for a car whose tyres stand on Tyre_Road surface records (only the SRC files use
# that tyre), sets the yaw rate and the side velocity from SRC's equations, with SR3's own speed, surfaces and suspension;
# SR3 keeps the speed along the car, pitch, roll, walls and the air. tools\build_srcport.py builds it from tools\srcport.c
# (and writes the lines below with --embed); tools\srcport_emu.py checks it on an emulated CPU. The blob is relocated here:
# each 4-hex-digit offset in $SrcPortRelocs is a dword that gets the cave's address added. The data block (+$SrcPortData):
# +8 mode (0 off, 1 observe, 2 on), +0xC every car on the SRC files (1) or the player's only (0, the default).
$SrcPortCode = '5553575681ec9802000089cff30f108424ac020000833de8230000000f84600200008b470885c00f8455020000f30f108870010000f30f118c24b4000000f30f108874010000f30f114c241cf30f10887c010000f30f114c2450f30f108880010000f30f114c2474f30f108878010000f30f118c24ec000000f30f108884010000f30f114c2420f30f110424b820c8450089f9ffd083ec048b35b0240000468935b02400008b5f08a1ccba9d0085c074188138c8d06e00751081b8e4070000c8ba9d000f84dd010000a1e4d99d0085c0f30f10a424ac02000074188138c8d06e00751081b8e4070000e0d99d000f84de010000a1fcf89d0085c074188138c8d06e00751081b8e4070000f8f89d000f84d6010000a114189e0085c074188138c8d06e00751081b8e407000010189e000f84ce010000a12c379e0085c074188138c8d06e00751081b8e407000028379e000f84c6010000a144569e0085c074188138c8d06e00751081b8e407000040569e000f84be010000c744241000000000833dec23000000b8000000000f840801000085db0f84000100008b6f2c85ed0f84f50000000f2e25b02200000f87e80000000f57c00f2ee00f86dc000000837f30040f85d20000008b0d2824000081f980000000ba800000000f42d1899424a40000008b550085d20f84ac00000089742470896c244c895c24248b3504240000f30f10050c2400008b0d08240000898c2494000000f30f1015102400008b6a0c8b5a100f57edb10185ed897424080f8424010000837c3500000f84190100008b8c2494000000f30f10740d00f30f59f0f30f58f2f30f100db4220000f30f5dce0f57dbf30fc2f3010f55f1c7442418ffffffffb101898c24dc00000031c9e9eb000000f30f110424b820c8450089f9ffd083ec04ff05b024000081c4980200005e5f5b5dc204008b885808000085c90f8415feffff3979040f850cfeffffb101894c2410f30f10a424ac020000e9c0feffff8b885808000085c90f8414feffff3979040f850bfeffffeb628b885808000085c90f841cfeffff3979040f8513feffffeb498b885808000085c90f8424feffff3979040f851bfeffffeb308b885808000085c90f842cfeffff3979040f8523feffffeb178b885808000085c90f8434feffff3979040f852bfeffffb101894c2410e93afeffffc78424dc00000000000000c7442418000000000f57f6f30f101df02300008b521485db8b6c24087408f30f10ab84010000c7442404ffffffff85d2742d8b521c3b9424a400000073210fb6923024000081faff000000741289d3c0eb0784c9750b83e20389542404eb0231db8b4c244c8b510485d20f84c7feffff89de8b4a0c8b52140f57c90f118c24e0010000b301895c240c85c90f8482000000833c290089f30f848a00000089ee8bac2494000000f30f103c2989f5f30f59f8f30f58faf30f100db4220000f30f5dcf0f28e60f28f00f28c20f28d50f28eb0f57dbf30fc2fb010f28dd0f28ea0f28d00f28c60f28f4f30f10a424ac0200000f55f90f11bc24e0010000c7442414ffffffffb101894c2438c744240c00000000eb24c744243800000000c74424140000000089f3eb10c744243800000000c7442414000000000fb6cb85d2744e8b521c3b9424a400000073420fb69a3024000081fbff000000743384dbba010000000f49d18954243c807c240c008b542404751683e30385d2781b0fb68b6c2300003a8a6c230000770c89d3eb088b5c2404894c243c8b4c244c8b510885d20f8494fdffff895c24048b4a0c8b52140f57ffb301895c240c85c97477833c2900747189ee8bac2494000000f30f103c2989f5f30f59f8f30f58faf30f100db4220000f30f5dcf0f28e60f28f00f28c20f28d50f28eb0f57dbf30fc2fb010f28dd0f28ea0f28d00f28c60f28f4f30f10a424ac0200000f55f9c7842484000000ffffffffb101894c2434c744240c00000000eb13c744243400000000c7842484000000000000008b5c240485d2744c8b4a1c3b8c24a400000073400fb6913024000081faff000000743184d2b9010000000f494c243c894c2404807c240c00751683e20385db781d0fb68a6c2300003a8b6c230000770e89daeb0a89da8b4c243c894c24048b4c244c8b490c85c90f8486fcffff89d68b590c8b49140f57c9b2018954243c85db7441833c2b00743b8bac2494000000f30f59042bf30f58c2f30f100db4220000f30f5dc80f57d2f30fc2c2010f55c1bd01000000b301c744243c000000000f28c8eb0431db31ed85c9896c240c74508b491c3b8c24a400000073440fb6893024000081f9ff000000743584c9bd010000000f496c2404807c243c00751e83e10385f67821895c24300fb6996c2300003a9e6c2300008b5c2430770a89f1eb0689f18b6c2404833d1424000000741e85ed751a807c2410000f84b6fbffffc705bc24000001000000e9a7fbffff895c24308b15c024000039fa0f849a0100008b1de024000039fb8b6c24240f84980100008b350025000039fe0f849901000089b424a40000008b352025000039fe0f8493010000897424048b354025000089b4249400000039fe0f84890100008b356025000039fe0f848a01000089b424cc0000008b35802500008974243c39fe0f8480010000895c24288b35a02500008974246039fe0f84790100008b35f02400008b1dd024000039de0f42debde0240000bec02400000f42f5391d10250000bb002500000f42f38b2d302500003b6e10bd202500000f42f58b2d502500003b6e10bd402500000f42f58b2d702500003b6e10bd602500000f42f58b2d902500003b6e108b6c2424bb802500000f42f38974240831db83bc24a400000000be002500000f44de837c24280089debbe02400000f44f385d2bac02400000f44f209742404ba202500000f44f209b42494000000ba402500000f44f209b424cc000000ba602500000f44f20974243cba802500000f44f209742460baa02500000f44f289f28b1db02500008b7424083b5e10bba02500000f42f385d20f45f2893e897424088d5614e992000000c7442408c024000031d28b6c2424eb67c7442408e0240000ba01000000eb58c744240800250000ba02000000eb49c744240820250000ba03000000eb3ac744240840250000ba04000000eb2bc744240860250000ba05000000eb1cc744240880250000ba06000000eb0dc7442408a0250000ba07000000c1e2058b5c24702b9ad024000081fb91010000720c8d92d4240000c702000000000f119c24a4000000f30f114c2428f30f108588000000f30f109590000000b201895424608b542408837a1400f30f11ac24340100000f11b424200200000f11bc241002000074360f28c8f30f5c4a180f28daf30f5c5a1cf30f59dbf30f59c9f30f58cb0f2e0db82200007609c7421400000000eb08c744246000000000f30f114218f30f11521c31db85c90f4fd9895c2404f30f10351c240000f30f1085fc000000f30f106c241cf30f59c5f30f108df8000000f30f109424b4000000f30f59caf30f58c8f30f10bd00010000f30f109c24ec000000f30f59fbf30f58f9f30f59fef30f108508010000f30f59c5f30f108d04010000f30f59caf30f58c8f30f10850c010000f30f59c3f30f58c10f14f80f108424a40000000fc6c0000f118424000200000f5ef80f28d70fc6d7550f2805c02200000f1174243c0f57c60f28f00f11bc24940000000f28cff30f59cf0f1194240c0100000f28c2f30f59c20f118c24b00100000f118424cc000000f30f58c80f57fff30fc2f9010f57d2f30f51d1807c24100074320fb788841c0000660f6ec90f57db660f60cb660f61cb0f5bc90f28e90fc6e955f30f5ce9f30f5e2dd02200008b5c2414eb1b8b4f280f57ed85c98b5c24147405f30f106908f30f592d2c2400000f54faf30f592df42300000f2e2dd4220000f30f100dd82200008b4c2460770cf30f59cdf30f5e0dd4220000f30f1085ec000000f30f118424a0010000f30f1085f0000000f30f11842438010000f30f1085f4000000f30f118424fc000000f30fc22ddc22000001f30f101de02200000f54dd0f55e9f30f101520240000f30f59d60f56eb0f108424a4000000f30f59c484c9740cf30f116a04c7420c00000000f30f1184249c010000d984249c010000d905b0220000d9f1d9c0d9fcdce9d9c9d9f0d9e8dec1d9fdddd9d99c2498010000f30f100db4220000f30f5c8c2498010000035c2418f30f105a040f28e5f30f5ce3f30f59e1f30f58e3f30f1162040f57db0f2e3de42200000f57c9f30f114c2418f30f115424148b6c240c0f11b424c00100000f86a40000000f28f40f109c2494000000f30f5edff30f100db42200000f28f9f30f5dfbf30f1015e8220000f30fc2da010f28e30f55e70f54da0f56dcf30f119c2494010000f30f59dbf30f5ccb0f57d2f30f51d10f57dbf30f115c2418f30fc2d9010f54daf30f119c2490010000d9842494010000d9842490010000d9f3d99c248c010000f30f109c248c01000084c9750e0f28cbf30f5c4a08f30f114c2418f30f105424140f28e6039c2484000000f30f115a088b7f3885ff7409837f24000f95c1eb0231c939dd0f84ec02000084c90f85e40200000f118424d0010000f30f104c241cf30f10b42438010000f30f59cef30f108424b4000000f30f10bc24a0010000f30f59c7f30f58c1f30f1144242cf30f108c24ec000000f30f119c2420010000f30f109c24fc000000f30f59cbf30f10442474f30f59c6f30f10742450f30f59f7f30f58f0f30f10442420f30f59c30f5725c0220000f30f58c6f30f59c20fb68c24dc000000f30f5e8424a40000000f11a42448020000f30f11a42488010000d9842488010000d9c0d9fed99c247c010000f30f10a4247c010000d9ffd99c2480010000f30f109424800100000f119424a0010000f30f11442420f30f11842484010000d9842484010000d9c0d9fed99c2474010000f30f10b42474010000d9ffd99c2478010000f30f101d002400000f2805c02200000f28d30f57d00f11a424fc0000000f57e00f11642474f30f10bc2478010000f30f1025f8230000898c241c01000085c90f11ac24580200000f119c24dc0000000f117c24500f119424840000000f8496010000f30f114c240c0f28c60f28f4f30f59b424c00100000f28c80f28e8f30f59ca0f28c6f30f59c7f30f58c1f30f58842494000000f30f5cc60f28cff30f59cbf30f59f50f28fdf30f58f10f10ac240c010000f30f58f5f30f5cf30f28cef30f59ce0f28d8f30f59d8f30f58d90f57c9f30f51cb0f57d2f30fc2d3010f57db0f54d1f30f100dec2200000f2eca0f57c90f87b8000000f30f5ec2f30f5ef20f108c24a0010000f30f59ce0f28d8f30f595c2474f30f58d90f28eb0f280dc02200000f57e9f30f5febf30f101db42200000f28cbf30f5dcdf30f59b424fc000000f30f598424a0010000f30f58c60f57f60f28e8f30fc2ee040f54c50f55eb0f28f3f30f59c9f30f5cf10f28df0f57fff30fc2fe010f57c9f30f51ce0f54f90f28cf0f28fb0f57db0f56e8f30fc22d68230000010f28c50f55c10f570dc02200000f54cd0f10ac240c0100000f56c8f30f58cb0f14ca0f114c2460bd01000000f30f104c240c0f109c24dc000000eb3ec74214010000008b442470894210807c2410000f8493f2ffff0fb6c183c802a3bc240000e983f2ffff0f57c00f1144246031ed0f10ac240c0100000f28fef30f584c242c807c2438000f11bc24380100000f844b010000f30f114c240cf30f5964243c0f28c7f30f598424840000000f28f40f104c2450f30f59f1f30f58f0f30f58b42494000000f30f5cf40f28c1f30f59c3f30f59e7f30f58e0f30f58ecf30f5ceb0f28c5f30f59c50f28cef30f59cef30f58c80f57d2f30fc2d1010f57c0f30f51c10f54d0f30f1005ec2200000f2ec20f57c90f10bc24a40000000f879e000000f30f5ef2f30f5eea0f10a424a00100000f28c4f30f59c50f105c2474f30f59def30f58d80f28c30f280dc02200000f57c1f30f5fc3f30f100db42200000f28d9f30f5dd8f30f59ac24fc000000f30f59f4f30f58f50f57c00f28e6f30fc2e0040f54f40f55e10f28e9f30f59dbf30f5ceb0f57c9f30fc2cd010f57dbf30f51dd0f54cb0f56e6f30fc2e0010f28c40f55c10f570dc02200000f54cc0f56c80f14ca0f104424600f58c10f1144246045f30f104c240c0f109c24dc000000eb080f10bc24a40000000f10b424c0010000f30f5ecff30f1015fc230000807c2434000f10ac248400000089bc24c4000000f30f114c240c0f84470100000f1194240c010000f30f59f20f108c24380100000f104424500f14c80f28d30f14d50f59d10fc6f6000fc6c9e10f59ce0f58ca0f108424940000000f58c80f14f30f28d90f5cde0f58f10f28ce0f59ce0fc6c9550f28e3f30f59e3f30f58e10f57c9f30f51cc0f57c0f30fc2c4010f57d20f54c1f30f100dec2200000f114424740f2ec80f57ff0f87a10000000fc6f3010fc6f3e20f104c24740fc6c9000f5ef10f28fe0fc6fe550f57db0f28eef30f59ebf30f58ef0f28cd0f2825c02200000f57ccf30f5fcd0f28d6f30f1035b4220000f30f59fbf30f5cd70f28ee0f28faf30fc2fb040f54d70f55fef30f5df1f30f59f6f30f5cee0f57c9f30f51cd0f57c0f30fc2c5010f10ac24840000000f54c10f56fa0f57d2f30fc2fb010f28cf0f55c80f57c40f54c70f28f80f56f9f30f58fabb01000000f30f104c240c0f1094240c010000eb0d31db0f57ff0f57c00f114424740f28e1f30f59e18b4c24048d14c9807c2430000f104424500f843e010000f30f5954243c0f28f20f109424380100000f14d00f109c24dc0000000f28cb0f14cd0f59ca0fc6f6000fc6d2e10f59d60f58d10f108424940000000f58d00f14f30f28ca0f5cce0f58f20f28d60f28de0f59de0fc6db550f28f1f30f59f1f30f58f30f57edf30fc2ee010f57dbf30f51de0f54ebf30f101dec2200000f2edd0f57f60f879c0000000fc6d1010fc6d1e20f28cd0fc6cd000f5ed10f117c24500f28fa0fc6fa550f57db0f28f2f30f59f3f30f58f70f28ce0f2805c02200000f57c8f30f5fcef30f1035b4220000f30f59fbf30f5cd70f28fe0f28c2f30fc2c3040f54d00f55c6f30f5df1f30f59f6f30f5cfe0f57c9f30f51cf0f57f6f30fc2f7010f107c24500f54f10f56c2f30fc2c3010f28c80f55ce0f5735c02200000f54f00f56f1f30f58fe0f117c24500f10442474f30f58c50f1144247443eb050f117c24500f108424b0010000f30f58c40f28e08d3c52660f6ecb660f6ec5660f62c1f30f7f8424840000000f57ed0f10bc2420020000f30f58bc24e00100000f10842410020000f30f584424280f28cff30f58c80f2e0d00230000f30f118424c800000076160f28d7f30f5cd0f30f5ed18b4c2408f30f10590ceb0c8b4c2408f30f10590c0f28d30f108c24cc000000f30f58cc0f118c24cc000000f30f6f842484000000660f76e80f5bf031c9f30f1194240c0100000f2ed30f96c18b54240401faf30f10a48a842300000f57c00f2ec40f57c9734ef30f11a424700100000f108c24d0010000f30f118c246c010000d9842470010000d984246c010000d9c9d9f1d9c0d9fcdce9d9c9d9f0d9e8dec1d9fdddd9d99c2468010000f30f108c2468010000660f6fe5660fdfe6f30f1094240c0100000f28f2f30f5cf3f30f59f1f30f5cd60f2e15682300000f57f60f108c24cc000000f30fc2f101f30f51c9660fdb2df0220000f30f117c242c763af30f101d04230000f30f59daf30f119c2464010000d9842464010000d9fed99c2460010000f30f109c2460010000f30f591d08230000f30f58d38b5424080f54f10f11b424c0010000660febecf30f7fac24f00100000f104c24500f104424600f16c80f114c24500f104c24740fc6c8d40f114c2474f30f11520c8b4c2424f30f10a170010000f30f108974010000f20f10b1040100000f28de0fc6de55f30f118c2428010000f30f59cbf30f11a4242c010000f30f59e6f30f58e1f30f108178010000f30f10890c0100000f11842488020000f30f59c1f30f58c40f28e0f30f1005242400000f118424cc000000f30f10050c347800f30f118424b0010000f30f103d10347800f30f102d143478000f57c00f1144246085dbf30f118c24300100000f11b424780200000f11a42468020000f30f11ac2438010000f30f11bc24240100000f848f0000000f28c4f30f1064241cf30f59e30f28e9f30f108c24b4000000f30f59cef30f58ccf30f10a424ec000000f30f59e5f30f58e1f30f5cc4f30f59dff30f108c24b0010000f30f59cef30f58cbf30f109c2438010000f30f59ddf30f58d9f30f599c24cc000000f30f599c24ac020000f30f5cc3f30f59050c2300000f108c24a4000000f30f598c24d0010000f30f5ec1f30f6f8c24f0010000660f70c9440f107c24500f105c24740fc6fb22f30f6f9c24840000000f57f6660f76f385ed75030f57c0f30f1154241cf30f101d10230000f30f599c24c0010000f30f581db4220000f30f591d142300000f5ef98b4c2404f30f108c3974230000f30f59cbf30f118c24b4000000f30f10a43978230000f30f59e0660f7ef1660feff6f6c1018b6c24240f117c24500f856f0100008b4c240401f981c1702300000f28d70f2835c02200000f57d631d20f2ed70f97c2f30f5fd70f28cff30f5c0c9518230000f30fc215e4220000010f55d1f30f5919f30f103db4220000f30f587c241cf30f59fb0f57f2f30f5ff2f30f100d202300000f11b424ec000000f30f59cef30f101d24230000f30f5dd9f30f119c245c010000d984245c010000d9fed99c2458010000f30f10b42458010000f30f59f70f28ccf30f59cc0f28def30f59def30f58d90f57c9f30fc2cb01f30f51db0f54cb0f57db0f2ecf7649f30f5ef90f57c9f30f51cf0f57edf30fc2ef010f54e9f30f100d28230000f30f59cff30f59cff30f592d2c230000f30f58e9f30f59f5f30f593530230000f30f59ec0f116c2460eb080f28cc0f116424600f280dc02200000f57cef30fc2da060f54f30f55d90f56de0f107c24500f28cf660f15cff30f598c24ec000000f30f1015342300000f2ed1f30f1035b42200008b542408760bf30f5e0d342300000f28f1f30f59f30f57c9f30f6f942484000000660f76d1660fc5ca02660fefd20f57ed0f57c9f6c1010f118424f0010000f30f11b424ec0000000f8540010000f30f1035b4220000f30f5c74241cf30f59b424b4000000f30f5cc40f28cf0fc6cf550f2825c02200000f57e10f118c24b4000000f30f5fe1f30f100d04230000f30f59ccf30f101d24230000f30f5dd9f30f119c2454010000d9842454010000d9fed99c2450010000f30f109c2450010000f30f59de0f28c8f30f59c80f28ebf30f59ebf30f58e90f57c9f30fc2cd01f30f51ed0f54cd0f28ee0f57f60f2ecd7647f30f5ee90f28fdf30f51ed0f57c9f30fc2cf010f54cdf30f102d38230000f30f59eff30f59ef0f107c2450f30f590d3c230000f30f58cdf30f59d9f30f591d30230000f30f59c10f28e80f280dc02200000f57cbf30fc2b424b4000000060f54de0f55f10f56f30f28cf0fc6cffff30f59ccf30f1005342300000f2ec1760af30f5e0d34230000eb08f30f100db4220000f30f59cef30f10b424ec000000f30f11ac24b40000000f114c24740f57e40f106c2460f30f5fe5f30f5d2d402300000f108424fc000000f30f59c40f109c24a0010000f30f59def30f104c242c0f2e0d00230000f30f1164240876470f57c90f2ee10f1064243cf30f10bc24c8000000763ff30f100d30230000f30f59cc0f109424e0010000f30f5c942420020000f30f59d1f30f5e54242cf30f591544230000eb0e0f1064243cf30f10bc24c80000000f2e3d00230000f30f58ac24b4000000f30f5cd80f57c076300f2ee8762bf30f100d30230000f30f59ccf30f10442428f30f5c842410020000f30f59c1f30f5ec7f30f5905482300000f107424740f28cef30f5ccb0f116c2460f30f59c50f28eb0f109c24dc000000f30f59d9f30f58d8f30f59542408f30f5cda0f10bc24d00100000f28c70f119c24dc000000f30f59c3f30f5e054c230000f30f58442420f30f100db0220000f30f5dc8f30f101550230000f30fc2c2010f28d80f55d90f54c20f56c30f28ddf30f101554230000f30f59542418f30f11bc244c010000d984244c010000d90558230000d9f1d9c0d9fcdce9d9c9d9f0d9e8dec1d9fdddd9d99c2448010000f30f100db4220000f30f5c8c2448010000f30f58d0f30f59c8f30f5cd1f30f11942484000000f30f58def30f59dff30f5e1d0c230000f30f589c24940000000f10ac24cc000000f30f59ecf30f10a500010000833d18240000000f57f6741d0f10b424fc000000f30f59b424ec000000f30f59f7f30f5e350c2300000f14def20f1085f80000000f28c80fc6c855f30f10942424010000f30f59d1f30f108c24b0010000f30f59c8f30f58caf30f10942438010000f30f59d4f30f58d1f30f59eaf30f108c24ac020000f30f59e90f108c24680200000f14e90f109424000200000f5eea0f58ebf20f10bdec0000000f28cf0fc6cf55f30f109c2428010000f30f59d9f30f108c242c010000f30f59cff30f58cbf30f109df4000000f30f119c24b4000000f30f11a424fc0000000f10b42488020000f30f59f3f30f58f10f105c243cf30f59dd0f28cb0f14cb0f59c80f11ac24cc0000000fc6ed550f11ac24b00100000f108424780200000f59c50f58c80f59ca0f28c60f14c60f59c70f58c8f30f10a584010000f30f11a424000200000f138c243c020000f20f10957c0100000f28c70f59c20fc6c0550f28caf30f59cff30f58c8f30f59a424b4000000f30f58e10f28cc0f14cc0f59cf0f5cd1f30f10442414f30f598424840000000f10ac24a4000000f30f59c50f28c80f14c80f59cf0f58ca0f28d50f138c2430020000f30f108c2430010000f30f598c24b0010000f30f599c24fc000000f30f58d9f30f10ac24b4000000f30f59f5f30f59daf30f58def30f119c24440200000f28ccf30f59cdf30f109c2400020000f30f5cd9f30f59c5f30f58c3f30f11842438020000c74214010000008b4c2470894a108b0de8230000807c2410000f84f40200000fb66c24388b15b82400000fb6f28d3cb6c1e705f30f1005b4240000f20f101d60230000660f56c3f20f5cc3f20f5ac08b1dc02500008b35b424000089742410f30f11043bf30f108424ac020000f30f11443b040f10842458020000f30f11443b080f10842448020000f30f11443b0c0f108424940000000f13443b10f30f10442420f30f11443b18f30f10842420010000f30f11443b1cf30f10442418f30f11443b200f104424500f11443b24f30f108424ec000000f30f11443b340f10442474f30f11443b38f30f10442408f30f11443b3c0f10442460f30f11443b400f108424dc000000f30f11443b44f30f1044241cf30f11443b48f30f1084240c010000f30f11443b4c89ce8b8c241c0100008d2c690fb64c24348d4c8d000fb66c24308d0ce98b6c2424660f6ec1660f6e4c2404660f62c80f5bc10f13443b500f10842420020000f30f11443b580f108424e0010000f30f11443b5c0f10842410020000f30f11443b60f30f10442428f30f11443b640f108424f0010000f30f11443b68f30f10842484000000f30f11443b6c0f108424cc0000000f13443b70f30f10442414f30f59c4f30f5ec2f30f11443b78f30f108574010000f30f5985fc000000f30f108d70010000f30f598df8000000f30f58c8f30f108578010000f30f598500010000f30f58c10f104c243cf30f59c8f30f5ecaf30f114c3b7c89742420660f6ec6660febc3f20f5cc3f20f5ac00f108c24c0010000f30f118c3b80000000f30f11843b84000000f30f1044240cf30f11843b88000000f30f10842434010000f30f11843b8c0000000fb688851c00000f57c0f30f2ac10fb680841c00000f57c9f30f2ac8f30f5cc1f30f5e05d0220000f30f11843b900000008d043b8b4c244c8b098b791085ff740af30f108790010000eb030f57c08b8c24c4000000f30f1180940000000f108424d0010000f30f11809800000085c97407f30f104128eb08f30f1005e82200008b4c2420f30f11809c000000428915b82400008b44241040a3b4240000c705bc2400000000000083f9020f8222e0ffff8d84243c020000890424b820a1450089e9ffd083ec048d842430020000890424b8a0a1450089e9ffd083ec04e9f1dfffff0000000000000000cdcccc3d0000803f0000c843000000000000008000000080000000800000008000007f430000a0423d0a573f0000a0c23d0a57bf0ad7233c000080bfffe6db2e0000803f0000803f0000000000000000bd378635db0f49400ad7a33d00007a449a99993e036233400ad7233c0ad723bc920a0640db0fc93fd0cc4cbe9a99993fcdcc8c3f0ad7a33c9a99193fcdcccc3e000000805c8f223fc3f5283f00408f44cdccccbd295c8fbd7b146e3f00000000000000000000304300000000000102036666a63f6666a63f0000803e295c8f3d295c8f3dcdcccc3dcdcccc3ecdcc8c3fcdcc8c3f0000803e295c8f3d295c8f3dcdcc4c3dcdcccc3e0000003f0000003f0000803e295c8f3d295c8f3dcdcccc3dcdcccc3e9a99993f9a99993f1f856b3e295c8f3d295c8f3dcdcccc3dcdcccc3e53524350010000000200000000000000000066420000be425c8f223fc3f5283f0000a03f580000008c0000000000803f0000000001000000010000000000803f0000803f0000803f660000006666e63fffffffff010101010101000003038181818183838181808001010101030301010000ffff00000000808001010101818102028200008001010101818101810101010101818101018100000000808001018101018100008000008000008081010102028201018100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000d0250000000000000000000000000000'
$SrcPortEntry = 0x0; $SrcPortData = 0x23E0; $SrcPortAlloc = 0x10000; $SrcPortVersion = 1
$SrcPortRelocs = '0017009a00a1018101a701c901fb02030209021802570295037103a3041b04af04de04e4053e05bd05ea05f00642068406b106b706cd06e506f807060718072d073f07540769077f0791079707a107a607af07b407bd07c507ce07d607df07e707f007fc08120821082b0837084608550861086d0878088408a208b208c108d008df08ee08fd090c091e092c099c09cc0a680ae70b080b130b1a0b220b340b6f0b780b860bbf0be20c120c4a0c590d880e220e290e500f040f3b0f4a0fac0fba100d10b810fa1109116411a712431287129913b513f71406145714d3154415c415e015f0161e16cf17ad18031814181c182c1842186c18761891189918a918c218d6194719571967198119af19ba19c81a101a311a481a541ac81add1aed1afb1b241b311b3b1b6a1b8f1bb51bdc1bf31c121c351c861c941ca01cbc1cd81cfb1d291d4c1d6f1f6b1f811f921f9a1fac1fb221eb224322562260226625c0'
$SrcPortSite = 0x678878; $SrcPortStock = 0x45C820
function Install-SrcPort($h) {
    if (-not $SrcPortCode) { return }
    $cur = Read-GamePtr $h $SrcPortSite
    if ($cur -ne $SrcPortStock) {
        $old = $cur - $SrcPortEntry
        if ((Read-GameInt $h ($old + $SrcPortData)) -ne 0x50435253) { Log ("SRC turning: the vehicle step (0x{0:X}) points to code that isn't ours; not installed." -f $SrcPortSite); return }
        if ((Read-GameInt $h ($old + $SrcPortData + 4)) -eq $SrcPortVersion) { $script:SrcPortCave = $old; Log 'SRC turning: already in this game (an earlier PLAY.bat); kept.'; return }
    }
    $cave = [Sr3Mem]::Alloc($h, $SrcPortAlloc)
    $b = HexToBytes $SrcPortCode
    for ($i = 0; $i -lt $SrcPortRelocs.Length; $i += 4) {
        $o = [Convert]::ToInt32($SrcPortRelocs.Substring($i, 4), 16)
        $v = ([long][BitConverter]::ToUInt32($b, $o) + $cave) -band 0xFFFFFFFFL
        [Array]::Copy([BitConverter]::GetBytes([uint32]$v), 0, $b, $o, 4)
    }
    [Sr3Mem]::Write($h, $cave, $b, $true)
    [Sr3Mem]::Suspend($h); try { [Sr3Mem]::Write($h, $SrcPortSite, [BitConverter]::GetBytes([uint32]($cave + $SrcPortEntry)), $false) } finally { [Sr3Mem]::Resume($h) }
    if ((Read-GamePtr $h $SrcPortSite) -ne $cave + $SrcPortEntry) { Log 'SRC turning: the hook did not take; SR3''s own turning.'; return }
    $script:SrcPortCave = $cave
    Log ("SRC turning: in (0x{0:X}): cars on the SRC handling turn by SEGA Rally Championship's own equations (the player's car)." -f $cave)
}
function Remove-SrcPort($h) {
    $script:SrcPortCave = $null
    $cur = Read-GamePtr $h $SrcPortSite
    if ($cur -eq $SrcPortStock -or (Read-GameInt $h ($cur - $SrcPortEntry + $SrcPortData)) -ne 0x50435253) { return }
    [Sr3Mem]::Suspend($h); try { [Sr3Mem]::Write($h, $SrcPortSite, [BitConverter]::GetBytes([uint32]$SrcPortStock), $false) } finally { [Sr3Mem]::Resume($h) }
    Log 'SRC turning: taken out (SEGA''s vehicle step).'
}

function Release-StuckKeys($game) {
    Log 'Leave this window open: when the game closes it releases any stuck Alt/Ctrl/Shift/Win key.'
    Set-MenuTimers $game
    Set-CarLists $game
    Set-Handling $game
    Watch-Tracks $game $script:GameExePath
    foreach ($vk in 0x12, 0xA4, 0xA5, 0x11, 0xA2, 0xA3, 0x10, 0xA0, 0xA1, 0x5B, 0x5C) { [SR3.Keys]::keybd_event([byte]$vk, 0, 2, [UIntPtr]::Zero) }
    Log 'Game closed. Modifier keys released.'
}

# The camera patch into a running game: the check, then the install (pc_install_cameras in tools\sr3mods\patchcore.c does the
# same, write for write: live_lockstep.py's re-attach scenarios run both on a game already patched with other settings).
# Every site must still hold the original bytes, or ours. The cave's "SR3C" signature also recognises an older build of this
# patch, which is then replaced in place. Returns whether an older build is in; throws on bytes that are neither.
function Test-CameraSites($h) {
    $sig = [Sr3Mem]::Read($h, $CaveVA, 4)
    $ours = $sig -and [Text.Encoding]::ASCII.GetString($sig) -eq 'SR3C'
    $already = $true; $older = $false
    foreach ($p in $Patches) {
        $cur = [Sr3Mem]::Read($h, $p.VA, $p.NewB.Length)
        if (Same $cur $p.OrigB) { $already = $false; continue }
        if ($p.VA -eq $CaveVA -and $cur) {   # cave with possibly different tuning
            $a = $cur.Clone(); $b = $p.NewB.Clone(); for ($i = $TunableLo; $i -lt $SettingsHi; $i++) { $a[$i] = 0; $b[$i] = 0 }
            if (Same $a $b) { continue }
        } elseif (Same $cur $p.NewB) { continue }
        if ($ours) { $older = $true; continue }
        throw ("Unexpected bytes at 0x{0:X} ({1}) - not the expected game version. Nothing changed." -f $p.VA, $p.Desc)
    }
    if ($older) { Log 'An older build of the camera patch is active; replacing it.' }
    elseif ($already) { Log 'Camera patch was already applied; updating the tuning values.' }
    return $older
}
# with the game's threads held: the old build unhooked (if any), every site written, the camera block made or updated
# (Install-Cycle); then each site read back (the cave without the parts its code changes while running)
function Install-CameraPatch($h, [bool]$older) {
    [Sr3Mem]::Suspend($h)
    try {
        if ($older) { for ($i = $Patches.Count - 1; $i -ge 1; $i--) { [Sr3Mem]::Write($h, $Patches[$i].VA, $Patches[$i].OrigB, $false) } }   # unhook the old build
        foreach ($p in $Patches) { [Sr3Mem]::Write($h, $p.VA, $p.NewB, ($p.VA -eq $CaveVA)) }
        try { Install-Cycle $h; $cycleOk = $true }
        catch { $cycleOk = $false; $cycleError = $_.Exception.Message }
    }
    finally { [Sr3Mem]::Resume($h) }
    foreach ($p in $Patches) {
        $cur = [Sr3Mem]::Read($h, $p.VA, $p.NewB.Length); $exp = $p.NewB.Clone()
        if ($p.VA -eq $CaveVA -and $cur) {
            for ($i = $DiagLo + 4; $i -lt $DiagHi; $i++) { $cur[$i] = 0; $exp[$i] = 0 }
            for ($i = $DebugLo; $i -lt $DebugHi; $i++) { $cur[$i] = 0; $exp[$i] = 0 }
        }
        if (-not (Same $cur $exp)) { throw ("Verification failed at 0x{0:X}" -f $p.VA) }
    }
    if ($Canary) { Log 'CANARY MODE: in a race the chase camera should look at your car from the SIDE.' }
    Log 'Camera mod is ACTIVE for this session. Have fun!'
    Log ("  Profile '$ProfileName'")
    if (-not $cycleOk) { Log "  Camera cycle NOT installed: $cycleError" }
    else { Log ("  View Change cycles: Game: Chase cam, Bumper cam, Bonnet cam, then " + ((@($slots | Select-Object -Skip 1) | ForEach-Object { $_.Name }) -join ', ') + $(if ($showHidden) { ', then the Debug cameras' } else { '' })) }
    Log $(if ($overlayPx -gt 0) { "  Camera name popup: $overlayPx px (at 1080p)" } else { '  Camera name popup: off' })
    if ($cycleOk) {
        Log $(if ($lookSmooth -gt 0) { "  Cameras you steer: mouse smoothed over $([int][Math]::Round(1000 * $lookSmooth)) ms, keys over $([int][Math]::Round(2000 * $lookSmooth)) ms" } else { '  Cameras you steer: raw mouse and keys (no smoothing)' })
        Log $(if ($blendSec -le 0) { '  View Change: cuts to the next camera (no blend, the game''s own code path)' } elseif ($script:BlendHooked) { "  View Change: the view travels to the next camera in $([int][Math]::Round(1000 * $blendSec)) ms" } else { '  View Change: cuts to the next camera (the blend could not be installed)' })
    }
    Log ('  Strength={0:0.00}  FadeIn={1}-{2} km/h  Stiffness={3}-{4}  Damping={5}  MaxAngle={6} deg  CapStiffness={7}' -f $Strength, $FadeInStartKmh, $FadeInFullKmh, $StiffnessMin, $StiffnessMax, $Damping, $MaxAngleDeg, $CapStiffness)
    if ($Framing) { Log ('  Framing: distance {0} m, height {1} m, field of view {2} deg' -f $Distance, $Height, $Fov) }
    else { Log '  Framing: SR3 default' }
}
# ---- launch (unless the game is already running) ----
$gameSetup = $null
if ($Setup) {
    $gameSetup = Get-GameSetup -Force
    if (-not $gameSetup) { throw 'Setup cancelled; nothing was changed.' }
    Log "Saved to setup.yaml: TeknoParrot $($gameSetup.teknoparrot), profile '$($gameSetup.profile)', game $($gameSetup.game)"
}
$proc = Get-Process -Name Rally -ErrorAction SilentlyContinue | Select-Object -First 1
$launched = -not $proc
if (-not $proc) {
    if ($NoLaunch) { throw 'Rally.exe is not running.' }
    if (-not $gameSetup) { $gameSetup = Get-GameSetup }
    if (-not $gameSetup) { throw 'Setup cancelled: PLAY.bat needs to know where TeknoParrot and SEGA Rally 3 are. Run PLAY.bat again (or PLAY.bat -Setup) to open the setup.' }
    $tpDir = Split-Path -Parent $gameSetup.teknoparrot
    $script:GameExePath = $gameSetup.game
    if (Get-Process -Name TeknoParrotUi -ErrorAction SilentlyContinue) {
        Log 'Note: TeknoParrot is already open. If the game does not start, close TeknoParrot and run PLAY.bat again.'
    }
    $tp = if ($TpProfile) { $TpProfile } else { $gameSetup.profile }                     # -TpProfile: another TeknoParrot profile for this run only (e.g. SR3Windowed, for the monitor off)
    Log "Starting SEGA Rally 3 through TeknoParrot (profile '$tp')..."
    Start-Process -FilePath $gameSetup.teknoparrot -ArgumentList "--profile=$tp.xml" -WorkingDirectory $tpDir
    $t0 = Get-Date
    while (-not ($proc = Get-Process -Name Rally -ErrorAction SilentlyContinue | Select-Object -First 1)) {
        if (((Get-Date) - $t0).TotalSeconds -gt 120) {
            throw ("TeknoParrot did not start SEGA Rally 3 within 2 minutes. Check that the game runs when you start it from " +
                   "TeknoParrot yourself (and that TeknoParrot isn't waiting on a message or an update), then try again. " +
                   "To check where PLAY.bat looks for TeknoParrot and the game, run PLAY.bat -Setup.")
        }
        Start-Sleep -Milliseconds 250
    }
}
# The game caches every video it plays (about 20) in its own DirectShow graph, and Windows' WMV
# decoder starts a thread per CPU core in each: ~140 MB of the 32-bit game's 4 GB per video on a
# 32-thread CPU, which ends in "Out of memory for VB" or a white screen. With 4 cores allowed a
# video costs ~70 MB. Set before the game loads its first video; the game itself needs one core.
if ($Cores -gt 0 -and $Cores -lt [Environment]::ProcessorCount) {
    $step = if ([Environment]::ProcessorCount -ge 2 * $Cores) { 2 } else { 1 }   # one per physical core where we can
    $mask = [int64]0; for ($i = 0; $i -lt $Cores; $i++) { $mask = $mask -bor ([int64]1 -shl ($i * $step)) }
    try { $proc.ProcessorAffinity = [IntPtr]$mask; Log ("Game limited to {0} of {1} CPU threads (keeps its video decoders' memory down)." -f $Cores, [Environment]::ProcessorCount) }
    catch { Log "Could not limit the game's CPU cores: $($_.Exception.Message)" }
}
# The in-game part runs from sr3mods.exe (tools\sr3mods: the same C as sr3mods.dll, in lockstep with this script's own code
# below, checked at every build by tools\sr3mods\lockstep.py and live_lockstep.py): it waits for the game, patches the
# cameras and, for a game this script started, runs the live loop and the watchdog (Ctrl+Scroll Lock too) until the game
# closes, then releases stuck modifier keys. This script's own code stays the reference those checks compare with, and runs
# instead only for -Off and when sr3mods.exe is not built or was built from another sr3mods.ps1 (python
# tools\sr3mods\build.py builds it; PLAY.bat never builds on its own).
$sr3mods = Join-Path $PSScriptRoot 'tools\sr3mods\build\sr3mods.exe'
$useExe = $false
if (-not $Off) {
    if (Test-Path -LiteralPath $sr3mods) {
        $want = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $PSScriptRoot 'sr3mods.ps1')).Hash.ToLower()
        $got = ("$(& $sr3mods source 2>$null)" -replace '^\s*\[[^\]]*\]\s*', '').Trim()           # its one line: [hh:mm:ss] <sha256>
        if ($got -eq $want) { $useExe = $true }
        else { Log 'sr3mods.exe was built from another sr3mods.ps1 (python tools\sr3mods\build.py builds it again); the PowerShell patches run this time.' }
    } else { Log 'sr3mods.exe is not built yet (python tools\sr3mods\build.py); the PowerShell patches run this time.' }
}
if ($useExe) {
    $a = @('attach', "$($proc.Id)", '--delay', "$DelaySeconds", '--mod', $PSScriptRoot)
    if ($CameraProfile) { $a += '--camera-profile', $CameraProfile }
    if ($ProfilesFile) { $a += '--profiles-file', $ProfilesFile }
    if ($Overlay -ge 0) { $a += '--overlay', "$Overlay" }
    if ($MouseSmoothing -ge 0) { $a += '--mouse-smoothing', "$MouseSmoothing" }                    # ("$x": the same number text in every culture)
    if ($CameraBlend -ge 0) { $a += '--camera-blend', "$CameraBlend" }
    if ($Canary) { $a += '--canary' }
    if ($NoWatchdog) { $a += '--no-watchdog' }
    if (-not $launched) { $a += '--no-live' }                                                      # (the run that started the game keeps its live loop)
    & $sr3mods @a | ForEach-Object {                                                              # its lines carry their own time
        Write-Host $_
        if ($script:PlayLog) { try { [IO.File]::AppendAllText($script:PlayLog, "$_`r`n") } catch { } }
    }
    $code = $LASTEXITCODE
    if ($code -ne 0) { throw "sr3mods.exe stopped with exit code $code (the lines above say why: 1 settings, 2 the game's bytes or no game, 3 the game closed or could not be opened)." }
    return
}
Log "Rally.exe running (pid $($proc.Id)). Waiting for the game to finish booting..."            # (sr3mods.exe says it itself when it waits)
$h = [Sr3Mem]::Open($proc.Id)
try {
    $t0 = Get-Date
    while ($true) {
        if ($proc.HasExited) { throw 'The game closed before it finished booting.' }
        $f = [Sr3Mem]::Read($h, $LoadedFlagVA, 4)
        if ($f -and [BitConverter]::ToUInt32($f, 0) -ne 0) { break }
        if (((Get-Date) - $t0).TotalSeconds -gt 180) { throw 'Timed out waiting for the game to boot.' }
        Start-Sleep -Milliseconds 250
    }
    Log "Game data loaded after $([int]((Get-Date) - $t0).TotalSeconds) s. Waiting $DelaySeconds s more so TeknoParrot's checks are done..."
    Start-Sleep -Seconds $DelaySeconds
    if ($proc.HasExited) { throw 'The game closed during start-up (before any patching).' }

    $older = Test-CameraSites $h

    if ($Off) {   # live un-patch: unhook first, then clear the cave
        Remove-SrcPort $h
        [Sr3Mem]::Suspend($h)
        try { Remove-Cycle $h; for ($i = $Patches.Count - 1; $i -ge 0; $i--) { [Sr3Mem]::Write($h, $Patches[$i].VA, $Patches[$i].OrigB, $false) } }
        finally { [Sr3Mem]::Resume($h) }
        foreach ($p in $Patches) { if (-not (Same ([Sr3Mem]::Read($h, $p.VA, $p.OrigB.Length)) $p.OrigB)) { throw ("Restore verification failed at 0x{0:X}" -f $p.VA) } }
        Log 'Camera patch REMOVED from the running game (original camera).'
        return
    }
    Install-CameraPatch $h $older
}
finally { [Sr3Mem]::Close($h) }
if ($launched -and -not $Off) {
    if (-not $NoWatchdog) { Start-Watchdog $proc }                # the patch is in and TeknoParrot's checks are long done
    Release-StuckKeys $proc
    Stop-Watchdog
}

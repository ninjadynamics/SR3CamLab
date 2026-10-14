<#
  SEGA Rally 3 - SR3CamLab chase camera, in-memory edition
  -----------------------------------------------------------
  Rally.exe on disk is never modified. This script launches the game through
  TeknoParrot as usual, waits until it has finished booting (and TeknoParrot's
  version check has passed), then patches the camera in the game's memory.

    ON  = start the game with PLAY.bat (runs this script)
    TEST = patch.ps1 -Canary: camera looks at the car from the side (proves the patch is live)
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
  START in a race: a short press saves a screenshot (..\Screenshots) when you let go; held for
  1.2 seconds it leaves the race for the game's main menu instead (Step-Start; it runs in the
  alternative tracks' loop, so with SR3 Extras tracks installed).
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
      [double]$MouseSmoothing = -1, [double]$CameraBlend = -1, [switch]$NoWatchdog)

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
$CycleCode = '9c60e8000000005d81ed0710000083bd64220000007411c7856422000000000000b800166200ffd083c8ff833d480f9c0000741a6a17b9fc536e00b8d0705400ffd083c40489c7b890646000ffd089856c22000083c8ff833d480f9c0000741a6a16b9145e6e00b8d0705400ffd083c40489c7b890646000ffd08985782200008b857022000085c00f84d10000004883f8140f83bd0000005069f86c01000081c7902fad00837f0400746c8b872001000085c074068b0850ff5124bb2c0100008b041f85c0740dc7041f000000008b0850ff510883eb0481fb1c01000073e18b874401000085c07410c78744010000000000008b0850ff5108c7873001000000000000c70700000000c7470400000000c74708000000008b8d7422000055b880dc4d00ffd05d85c074288b87200100008b0850ff511c85c07c06c707000000008b04246a016a0050b870e34d00ffd083c40c83c404c78570220000000000008b35ecb49e0085f60f844003000083c61881be1005000008b86e000f852d0300008dbe1005000039be340200000f851b0300008b862c0200003b452875093975580f849e01000083f8010f82fe020000c7855c2200000000000083f8150f87eb02000031c931d239c173288b9c8e3402000039fb741a83fa0c731539755875083b95bc0000007308899c95802100004241ebd439755874098995bc00000089455c89956022000031c983f90c735d8b9c8de021000083fbff745185db782b01f3833b0074215131c939d1730c399c8d80210000741041ebf083fa0c7308899c9580210000425941ebc081e3ffffff7f01f3833b0074f083fa0c73eb899c95802100004289955c220000ebdb8b4d208d1c1183fb150f873402000083bd5c22000000740749018d5c22000089552c89755889be34020000bb0100000031c93b8d6022000073128b848d8021000089849e340200004341ebe6b9010000003b4d20730b89bc9e340200004341ebf08b8d6022000039d173128b848d8021000089849e340200004341ebea899e2c020000895d288b85a80f000085c074054839d8722e8b452483f8fe751c8d8ec408000031c039d8730c398c8634020000741140ebf031c0eb0a85c07406038560220000898630020000c7451cffffffffc785b0000000010000008b86300200003b451c0f845a0100008b4d1c83f9ff74358d51013b5528720231d239d074278b948634020000399690010000750d8b948e34020000899690010000898e30020000e91d0100003b862c0200000f831101000089451c8d4801898da80f00008b8c863402000029f131d281f9ec0e0000741081f9780c0000740881f9681d00007501428995a00f0000e8bf01000031c985c074093b8560220000760141890d9457a60085c074173b8560220000762d89c12b8d602200003b4d20732089c8e80b0200008b8c85000e0000898d600e0000c1e0058d840500010000eb668b9c8634020000813bb8b86e0075095031c0e8db0100005829f33b855c220000750681cb000000808d85e0000000c785600e0000ffffffff31c983f90c7327399c8db0210000751b8b848d102200008985600e000089c8c1e0058d840500200000eb0341ebd48945508b8db0000000c785b00000000000000085c9750b8b4514894510e820150000e816030000837d10000f8ed2000000ff4d108b451885c00f8ec4000000f72578db7e00b938040000f7f183f8087d05b808000000508d5d08e8720100005985c00f849400000089c351a178db7e00b90e000000f7e1b964000000f7f18985b40000008b45508985a40f00008b04248b8d600e0000e8bb0100005883bda00f000000745e506bc00b31d2b90a000000f7f10185b400000058d1e883f8087d05b808000000508d9d980f0000e8000100005985c0742d89c38b956822000085d275068d95b00f00008995a40f000089c8b9e0e0e0ffe85c010000eb07c7451000000000619da10cd17e00c3608dbe381a0000813ff0bd6e0075708d95402200008b9d5c22000085db744c39d875488b8f9401000039d1745285c9744e898d582200008b01350000008089028b41048942048b41088942088b410c350000008089420c8b41108942108b4114894214899794010000eb14399794010000750c8b8d58220000898f9401000061c3565751526bd05c8db41500050000bf883c6700b90b000000f3a5bfd03c6700b90c000000f3a5833de83c67000075118b555885d2740ac782c0080000000070425a595f5ec33b430475038b03c3508b0b85c9740c518b11ff5208c70300000000588943048b555485d275228d4d6051ff15f441670085c074418d4d705150ff150442670085c0743289455489c2538d8d80000000516a006a046a006a016a006a0168bc0200006a00ff7304ff350cd17e00ffd285c07c038b03c3c70300000000c743040000000031c0c35131d2b916000000f7f185c075014089c76bc00731d2b90a000000f7f185c07501408985b800000089f9f7d931d2e86200000089f931d2e85900000031c989faf7dae84e00000031c989fae8450000008b8db800000089cae8380000008b8db800000089caf7dae8290000008b8db800000089caf7d9e81a0000008b8db8000000f7d989cae80b00000031c931d258e806000000c3b8000000d056898da00000008bb5b400000001d689b5a40000008b3574db7e0001ce89b5a80000008b3578db7e0001d689b5ac000000506a218db5a0000000566affffb5a40f00006a00538b33ff56385ec38b35ecb49e0085f6742a83c6188bbe900100008d86ec0e000039c774168d86780c000039c7740c8d86681d000039c77402eb01c38b35ecb49e0085f60f846f04000083c61881be1005000008b86e000f855c0400008bbe900100008d86ec0e0000bb0100000039c774288d86780c0000bb0200000039c774198d86681d000039c7740fc785300f000001000000e91f04000083bd8c0e0000000f85f60000008d8da00e000051ff15f441670085c00f84fd03000089c2528d8db00e00005152ff15044267005a8985800e0000528d8dc00e00005152ff15044267005a8985840e0000528d8dd00e00005152ff15044267005a8985880e0000528d8d400f00005152ff15044267005a8985900e00008d8d600f00005251ff15f44167005a85c0745b8d8d700f0000525150ff15044267005a8985940e00008d8df00e00005152ff150442670089858c0e000083bd800e000000742883bd840e000000741f83bd880e000000741683bd900e000000740d83bd940e000000740485c07519c7858c0e000000000000c785300f000002000000e91c030000ff958c0e00008d8d380f0000c701000000005150ff95900e0000ff95940e00003b85380f0000740fc785300f000003000000e9e5020000c785300f000004000000c785340f000000000000a174db7e00d1e88985280f0000a178db7e00d1e889852c0f00008d8d700e000051ff95800e000031c08985200f00008985240f000083bd680e00000075248b85700e00002b85280f00008985200f00008b85740e00002b852c0f00008985240f0000c785680e000000000000ffb52c0f0000ffb5280f0000ff95840e0000c785640e00000100000068c0000000ff95880e00005068dc000000ff95880e00005909c825008000008b8dd80f00008985d80f000085c0741085c9750c89f98b07ff5004e8350f0000f30f2a85200f0000f30f2a8d240f0000e89a0e0000f30f5985100f0000f30f598d100f000083fb010f8510010000f30f108dac220000f30f598dd00f0000f30f10160f57db0f2fd3761ef30f10daf30f599d140f0000f30f5ec3f30f5995180f0000f30f5ecaeb060f57c00f57c9f30f1186a8010000f30f118eb80100006a536a57e8df0100008d85a4220000e8700e0000f30f1186ac0100000f57c0f30f1186bc010000f30f10160f57db0f2fd30f8688000000f30f5995180f00008b860c05000085c07476f30f1086ac010000f30f59c2f30f584720f30f5800f30f5f85e00f0000f30f5d85e40f0000f30f5c00f30f5c4720f30f5ec2f30f1186ac010000f30f1086b8010000f30f59c2f30f584748f30f584004f30f5f85e80f0000f30f5d85ec0f0000f30f5c4004f30f5c4748f30f5ec2f30f1186b8010000c3f30f1097300200000f57db0f2fd3760af30f5ec2f30f5ecaeb12f30f59851c0f0000f30f598d1c0f0000eb30f30f10d9f30f59daf30f589f68020000f30f5d9d900f0000f30f5f9d940f0000f30f5c9f68020000f30f5edaf30f10cbf30f1186a8010000f30f118eac0100000f57c0f30f1186c40100006a576a53e8a80000008d8598220000e8390d0000f30f1186b00100006a446a41e88c0000008d859c220000e81d0d0000f30f1186b40100006a206a11e8700000008d85a0220000e8010d0000f30f1186b8010000c3c785680e00000100000083bd640e0000007448c785640e000000000000e8090d00008b755885f6743231c08986a80100008986ac0100008986b00100008986b40100008986b80100008986bc0100008986c00100008986c4010000c35331dbff74240cff95880e0000660985340f000066a90080740143ff742408ff95880e000066a9008074014bf30f2ac35bc208009c60e8000000005d81ed101d0000e8e0faffff619d68001e5f00c39c60e8000000005d81ed2b1d0000e8c5faffff619d68e03f5f00c39c60e8000000005d81ed461d00008b4d0885c97414518b11ff5208c7450800000000c7450c000000008b8d980f000085c9741a518b11ff5208c785980f000000000000c7859c0f000000000000619d6820125900c3'
$CycleSize = 0x4000; $CycleDraw = 0x1000; $CycleLost = 0x1d3f; $CycleRot = 0x1d09; $CycleFree = 0x1d24
# the block's second code area (constants, then code): the smoothing of the steerable cameras and the blend between cameras
$CycleCode2 = '0000803f000040400000803ecdcccc3dbd3786350000803d0000000000000000ffffffffffffffffffffffff000000005175657279506572666f726d616e6365436f756e746572005175657279506572666f726d616e63654672657175656e63790000000000000000000000000000000000803f000000000000803f00000000000000000000803f00000000000000000000803f00000000000080bf00000000f30f1095002800000f57db0f2f1873427a40f30f10260f2fe376370f2fa508280000772ed906d830d9e0d9eadec9d9c0d9fcdce9d9c9d9f0d9e8dec1d9fdddd9d9e8dee1d99db4220000f30f1095b4220000c3f30f58000f28d8f30f59c2f30f5cd80f28e3f30f59e40f2fa5102800007307f30f58c30f57dbf30f1118c38d8584220000e877fffffff30f1195b02200008d8580220000e864ffffff8d8590220000e8acfffffff30f1185a82200000f28c18d8594220000e896fffffff30f1185ac2200000f28c8f30f1085a8220000c3f30f1095b02200000f28e8f30f5c00f30f59c2f30f58000f28ddf30f5cd8f30f59db0f2f9d1028000073030f28c5f30f1100c35031c089859022000089859422000089859822000089859c2200008985a02200008985a422000058c3508b86300200008b8486340200003b85f022000074128985e8220000c785ec2200007800000058c3c785e422000001000000c785e82200000000000058c30f28da0fc6db55f30f58da0f12d2f30f58d3c30f5cc80f59ce0f58c1c35331dbf30f1000f30f59049af30f104804f30f594c9a04f30f58c1f30f104808f30f594c9a08f30f58c1f30f11041983c30483fb0c72cc5bc35331dbf30f1000f30f59041af30f104804f30f594c1a10f30f58c1f30f104808f30f594c1a20f30f58c1f30f11041983c30483fb0c72cc5bc3c785d82200000000000083bdb82200000075528d85600f000050ff15f441670085c00f84bd00000089c78d8d482800005157ff150442670085c00f84a50000008d8dc022000051ffd08d8d302800005157ff150442670085c00f84860000008985b82200008d85c822000050ff95b82200008b85c82200008b95cc2200008b8dd02200008b9dd42200008985d02200008995d422000089cf09df744929c819da753785c078338985c8220000db85c8220000dfadc0220000def9d99dd8220000f30f1085d8220000f30f5d850c280000f30f1185d8220000c38b850c2800008985d8220000c3a1ecb49e0085c00f84c704000083c01839f00f85bc040000a110ce7e003b0514ce7e00750a83f827741283f81c740d833d00b89d00000f84980400000f57c90f2f8d882200000f836e0400000f8a68040000e8c3feffff83bdb8220000000f84560400008bbe8401000085ff0f844804000089f98b07ff505c89c38b96c801000085d20f843104000081c25c1300000f10bd202800003bbdf0220000741d89bdf02200003bbde8220000745ac785e022000000000000e9c300000083bde422000000754283bde8220000007412ff8dec2200007f0ac785e82200000000000083bde0220000000f8492000000f30f1085dc220000f30f5885d8220000f30f1185dc220000eb78c785e422000000000000c785e82200000000000083bdf422000000745b31c90f10140a0f54d70f59d2e857fdfffff30f5c9500280000f30f59d20f2f951428000077357a3383c11083f93072d256578db5002300008dbd40230000b910000000f3a55f5ec785dc22000000000000c785e0220000010000000f10020f54c70f104a100f54cf0f58c10f104a200f54cf0f58c10f104a300f54cf0f58c10f57c90f59c10f28d0e8dbfcffff0f2ed10f8a010300000f1042200f54c70f5985702800000f28d00f59d2e8b9fcffff0f2f95102800000f86db020000f30f51d20fc6d2000f5ec20f1185e02700000f108d802800000f118dd02700000f28c80fc6c9c60f598d902800000f10120f54d70f59d1e870fcffff0f57db0f2fd373060f5cd90f28cb0f118dc02700000f1042300f1185f02700008d95c02700000f1043300f54c70f1185802300000f104b6c0f54cf0f5cc80f28d10f59d2e827fcffff0f2f95102800000f8649020000f30f51d2f30f1195b02300000fc6d2000f5eca0f118d902300000f1083200100000f54c70f1185a02300008b83780100008985b423000083bde0220000000f8497010000f30f10b5dc220000f30f5eb5882200000f2fb5002800000f83700100000f28c6f30f58c0f30f108d04280000f30f5cc8f30f59cef30f59f10fc6f6008d85402300008d8dd0230000e8dffbffff0f1085d02300000f54c70f104a300f54cf0f58c10f108d80230000e87cfbffff0f1185802300008d8550230000e8adfbffff0f1085d02300000f54c70f108d90230000e854fbffff0f28d00f59d2e836fbffff0f2f95102800007612f30f51d20fc6d2000f5ec20f1185902300008d8560230000e866fbffff0f1085d02300000f54c70f108da0230000e80dfbffff0f1185a02300000f1085702300000f108db0230000e8f3faffff0f1385b0230000f30f1085b02300000fc6c0000f108d902300000f59c80f1085802300000f58c80f118dc02300000f1095a02300000f58d10f58d0e8a0fafffff30f5895b42300000f57dbf30f59d30f2ed30f8ab70000000f1343300f12c0f30f1143380f134b6c0f12c9f30f114b740f1085a02300000f1383200100000f12c0f30f1183280100008b85b4230000898378010000eb0ac785e0220000000000000f1085802300000f104a300f54cf0f5cc10f1185d02300008d85d02300008d8d00230000e833faffff8d85902300008d8d10230000e822faffff8d85a02300008d8d20230000e811faffff8b85b02300008985302300008b85b4230000898534230000c785f422000001000000c331c08985f42200008985e02200008985e42200008985e8220000c3ff742404b890165f00ffd09c60e8000000005d81ed67300000e80dfbffff619dc20400'
$CycleCode2At = 0x2800; $CycleBlend = 0x3055
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
$TrackVideoEntry = @{ Tropical4 = 0x728710; Alpine4 = 0x728720; Canyon4 = 0x728730 }
$SwitchTextOff = 0x2400                                                          # free room in the camera block
function Read-TrackSwitch([string]$gameExe) {
    if (-not $gameExe) { return $null }
    $dir = Split-Path -Parent $gameExe
    $file = Join-Path $dir 'Main_release\tracks\_SR3Extras\switch.json'
    if (-not (Test-Path -LiteralPath $file)) { return $null }
    try { $j = [IO.File]::ReadAllText($file) | ConvertFrom-Json } catch { Log "Alternative tracks: $file can't be read; ignoring it."; return $null }
    $slots = @{}
    foreach ($p in $j.slots.PSObject.Properties) {
        $list = New-Object System.Collections.ArrayList
        [void]$list.Add(@{ Title = "$($p.Value.title)"; Dir = 's'; Video = ''; Speech = "$($p.Value.speech)"; Ambience = ''; Music = ''; Events = ''; Tune = $null })   # 0 = the game's own track
        foreach ($a in @($p.Value.tracks)) {
            $d = "$($a.dir)"
            if ($d -notmatch '^[1-9]$') { continue }
            if (-not (Test-Path -LiteralPath (Join-Path $dir "Main_release\track$d\$($p.Name)"))) { Log "Alternative tracks: $($a.title) is listed but Main_release\track$d\$($p.Name) is missing; skipped."; continue }
            $video = "$($a.video)"
            if ($video -and @(Get-ChildItem -LiteralPath (Join-Path $dir 'frontend\PC\Videos') -Filter "LANG_*_$video.wmv" -ErrorAction SilentlyContinue).Count -lt 1) { $video = '' }
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
        if ($path -notmatch '_[A-Za-z0-9]+\.wmv$') { Log "Alternative tracks: the card video of $slot isn't where expected; the card keeps its own picture."; continue }
        $script:CardVideo[$slot] = @{ Handle = $own; Path = $path }
        $slots[$slot][0].Path = $path
        for ($k = 1; $k -lt $slots[$slot].Count; $k++) {
            $alt = $slots[$slot][$k]
            $alt.Path = if ($alt.Video) { $path -replace '_[A-Za-z0-9]+\.wmv$', "_$($alt.Video).wmv" } else { $path }
        }
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
    if ($v.Count -lt 2 -or -not [double]::TryParse($v[0], $any, $inv, [ref]$a) -or -not [double]::TryParse($v[1], $any, $inv, [ref]$b) -or $a -le 0 -or $a -gt 0.01 -or $b -lt 1 -or $b -gt 200) { Log "Car shadows: $file not used (expected two numbers, e.g. 0.0002 30)."; return }
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
    if ($c1 -ne 0x02D604CD -or $c2 -ne ($base + 0xABFC) -or $c3 -ne ($base + $code) -or $c4 -ne 0xFFFF0300) {
        Log ("Shader experiment: the effect at 0x{0:X} is not the one this was written for (checks {1:X} {2:X} {3:X} {4:X}; shader library 2 instead of 3?): nothing changed." -f $base, $c1, $c2, $c3, $c4); return
    }
    $va = $base + $rec + 0x10; $a = [Sr3Mem]::Read($h, $va, 4); $b = [Sr3Mem]::Read($h, ($base + 0x8DFC + 0x10), 4)
    if ($null -eq $a -or $null -eq $b -or [BitConverter]::ToUInt32($a, 0) -eq 0 -or [BitConverter]::ToUInt32($b, 0) -eq 0) { Log "Shader experiment: a shader pointer is empty (walls $([BitConverter]::ToUInt32($a, 0)), plain $([BitConverter]::ToUInt32($b, 0))): nothing changed."; return }
    [Sr3Mem]::Write($h, $va, $b, $true); $script:ShaderSwap = @{ Va = $va; Old = $a }
    $back = [Sr3Mem]::Read($h, $va, 4)
    Log ("Shader experiment: effect at 0x{0:X}; wall pixel shader 0x{1:X} replaced by the untextured one 0x{2:X} (read back 0x{3:X}). Imported scenery should show without its pictures." -f $base, [BitConverter]::ToUInt32($a, 0), [BitConverter]::ToUInt32($b, 0), [BitConverter]::ToUInt32($back, 0))
}

# ---- START in a race: a screenshot, or back to the main menu ----
# A short press takes a screenshot when START is let go; held for $StartHoldSeconds it leaves the race for the game's main
# menu instead, and no picture is taken. The game has no flag we know that tells a race from the attract loop, so a race is
# what follows the menus, and the picture is held back 1.5 s: if the menus come up in that time, START was "begin a game"
# and the picture is dropped. Pictures are at least 2 s apart, and the file name is shown only after the picture was
# taken, so it is never in it. Step-Start is the decision alone, apart from the game (tools\start_mocktest.ps1 drives it):
# it returns what to do now, any of 'grab' (take the picture), 'save' (write the held one), 'drop' (forget it), 'exit'.
$StartHoldSeconds = 1.2
function New-StartState { return @{ Was = $false; At = [datetime]::MinValue; Armed = $false; Long = $false; Race = $false; WasMenu = $false; HeldAt = $null; ShotAt = [datetime]::MinValue } }
function Step-Start($s, [bool]$down, [bool]$menu, [datetime]$now) {
    $acts = @()
    if ($s.WasMenu -and -not $menu) { $s.Race = $true }
    if ($null -ne $s.HeldAt) {
        if ($menu) { $s.HeldAt = $null; $s.Race = $false; $acts += 'drop' }                  # that START began a new game
        elseif (($now - $s.HeldAt).TotalSeconds -ge 1.5) { $s.HeldAt = $null; $acts += 'save' }
    }
    if ($menu) { $s.Armed = $false }                                                       # a press that sees the menus does nothing
    if ($down -and -not $s.Was) { $s.Armed = $s.Race -and -not $menu; $s.At = $now; $s.Long = $false }
    elseif ($down -and $s.Armed -and -not $s.Long -and ($now - $s.At).TotalSeconds -ge $StartHoldSeconds) { $s.Long = $true; $acts += 'exit' }
    elseif (-not $down -and $s.Was) {
        if ($s.Armed -and -not $s.Long -and $null -eq $s.HeldAt -and ($now - $s.ShotAt).TotalSeconds -gt 2) { $s.HeldAt = $now; $s.ShotAt = $now; $acts += 'grab' }
        $s.Armed = $false
    }
    $s.Was = $down; $s.WasMenu = $menu
    return $acts
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
function Request-RaceExit($h, [datetime]$now) {
    $st = [Sr3Mem]::Read($h, $GameStateVA, 8); $mode = Read-GameInt $h $GameModeVA
    if ($null -eq $st) { Log 'Race exit: the game state could not be read; nothing done.'; return }
    $cur = [BitConverter]::ToInt32($st, 0); $next = [BitConverter]::ToInt32($st, 4)
    if ($cur -ne 0x27 -or $next -ne 0x27 -or -not $RaceModes.ContainsKey($mode)) { Log ("Race exit: START was held, but no race is running (game state 0x{0:X} / 0x{1:X}, mode {2}); nothing done." -f $cur, $next, $mode); return }
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
    Log ("Race exit: START held {0} s: leaving the {1} for the main menu." -f $StartHoldSeconds, $RaceModes[$mode])
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
    if (-not (Test-Path -LiteralPath $cs)) { Log 'Watchdog: watchdog.cs is missing next to patch.ps1; crashes and freezes are not recorded this time.'; return }
    try {
        if (-not ('Sr3Watchdog' -as [type])) { Add-Type -Path $cs -ErrorAction Stop }
        [Sr3Watchdog]::Values = $WatchdogValues
        [void][Sr3Watchdog]::Start($game.Id, (Join-Path $PSScriptRoot 'crash'), $FreezeSeconds, $GameWindowVA)
        $script:WatchdogOn = $true
    } catch { Log "Watchdog: could not start ($($_.Exception.Message)); crashes and freezes are not recorded this time."; return }
    for ($i = 0; $i -lt 30 -and -not [Sr3Watchdog]::Attached -and -not [Sr3Watchdog]::Finished; $i++) { Start-Sleep -Milliseconds 100 }
    Start-Sleep -Milliseconds 100; Show-WatchdogNews
}
function Show-WatchdogNews { if ($script:WatchdogOn) { for ($m = [Sr3Watchdog]::NextMessage(); $null -ne $m; $m = [Sr3Watchdog]::NextMessage()) { Log "Watchdog: $m" } } }
function Stop-Watchdog {
    if (-not $script:WatchdogOn) { return }
    if (-not [Sr3Watchdog]::WaitFinished(5000)) { [Sr3Watchdog]::Stop(5000) }           # the game has closed: its last events are in
    Show-WatchdogNews
}
function Wait-GameExit($game) { while (-not $game.HasExited) { Show-WatchdogNews; Start-Sleep -Milliseconds 250 }; $game.WaitForExit(); Show-WatchdogNews }

# Runs until the game closes.
function Watch-Tracks($game, [string]$gameExe) {
    Add-Type -AssemblyName System.Drawing, System.Windows.Forms
    if (-not ('Sr3Pad' -as [type])) {
        Add-Type @'
using System; using System.Runtime.InteropServices;
public static class Sr3Pad {
    [StructLayout(LayoutKind.Sequential)] public struct XState { public uint Packet; public ushort Buttons; public byte LT, RT; public short LX, LY, RX, RY; }
    [DllImport("xinput1_4.dll")] public static extern int XInputGetState(int index, ref XState state);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
}
'@
    }
    [Sr3Pad]::SetProcessDPIAware() | Out-Null
    $start = New-StartState; $script:RaceExit = $null; $shotUntil = [datetime]::MinValue; $shotName = ''; $shotHeld = $null
    $slots = Read-TrackSwitch $gameExe
    if (-not $slots) { $slots = @{} }                                # no alternative tracks: the loop still runs for START (screenshot, race exit)
    $h = [Sr3Mem]::Open($game.Id)
    try {
        $base = Find-Cycle $h
        if (-not $base) { Log 'Alternative tracks and the START button need the camera patch; it is not in the game.'; Wait-GameExit $game; return }
        if ($slots.Count) {
            Log ('Alternative tracks: ' + ((@($slots.Keys | Sort-Object) | ForEach-Object { "$_ +$($slots[$_].Count - 1)" }) -join ', ') + '. On the stage-select screen, View Change steps through them.')
            Initialize-TrackVideos $h $base $slots
        }
        $text = $base + $SwitchTextOff
        [Sr3Mem]::Write($h, $text + 0x40, (Str 'Press VIEW CHANGE to select alternative tracks' 64), $true)
        $choice = @{}; foreach ($s in $slots.Keys) { $choice[$s] = 0 }
        $soundNow = '//'; $tuneNow = ''; $script:TuneOwn = $null; $ids = @{}; $pvsHeld = $false; $pvsWas = 0
        $modeSeen = $null; $modeLast = $null; $nameWas = ''; $classicVal = $null
        $classicFile = Join-Path (Split-Path -Parent $gameExe) 'Main_release\tracks\_SR3Extras\classic_mode.txt'
        if (Test-Path -LiteralPath $classicFile) { $t = ([IO.File]::ReadAllText($classicFile)).Trim(); if ($t -match '^-?\d+$') { $classicVal = [int]$t } }
        $dirNow = 's'; $wasDown = $false; $wasMenu = $false; $deep = $false; $showing = $false; $shown = ''; $timesNow = ''
        while (-not $game.HasExited) {
            $g = [Sr3Mem]::Read($h, 0x9D6E3C, 1)
            if ($null -eq $g) { break }
            $menu = $g[0] -eq 1
            if ($menu -and -not $wasMenu) {                           # a new game: every card back to its own track
                $deep = $false
                foreach ($s in @($choice.Keys)) {
                    if ($choice[$s] -ne 0) { Set-CardTrack $h $base $s $slots[$s][0] $true }
                    $choice[$s] = 0
                }
            }
            $count = Read-GameInt $h 0x9C442C
            if ($menu -and ($count -ge 4 -or $count -eq 2)) { $deep = $true }      # past the mode menu, which also has 3 entries (the car select: 6, or every car with Set-CarLists)
            $stage = $menu -and $deep -and $count -eq 3
            $p1 = Read-GameInt $h 0x9DBDB0
            $name = ''
            if ($p1) { $p2 = Read-GameInt $h ($p1 + 0x18); if ($p2) { $name = Read-GameString $h $p2 24 } }
            # the card the stage selector is on
            $hi = Read-GameInt $h ($base + 0x226C); $hiName = ''
            if ($hi -ne -1) { if (-not $ids.ContainsKey($hi)) { $ids = Read-TrackNames $h }; $hiName = "$($ids[$hi])" }
            $stage = $stage -and $hiName
            $hlist = if ($stage) { $slots[$hiName] } else { $null }
            $down = ([Sr3Mem]::Read($h, 0x9DBB0C, 1)[0] -ne 0)
            if ($hlist -and $down -and -not $wasDown) {
                $choice[$hiName] = ($choice[$hiName] + 1) % $hlist.Count
                Set-CardTrack $h $base $hiName $hlist[$choice[$hiName]] ($choice[$hiName] -eq 0)
            }
            # Classic has no stage select: its tracks (the Desert4 slot) are stepped through on the first menu,
            # the one with Championship / Quick Race / Classic (3 entries, before the car and gearbox menus)
            $mode = $menu -and (-not $deep) -and $count -eq 3 -and $slots.ContainsKey($ClassicSlot)
            # ... and only while that menu is on Classic. Which of the selector's values is Classic is learnt
            # the first time Classic is picked (the current track becomes Desert4 right after) and kept in
            # tracks\_SR3Extras\classic_mode.txt; until then the text shows on all three.
            $modeVal = Read-GameInt $h ($base + 0x2278)
            if ($mode -and $modeVal -ne -1) { if ($modeVal -ne $modeSeen) { Log "Alternative tracks: first menu is on entry $modeVal."; $modeSeen = $modeVal } ; $modeLast = $modeVal }
            if ($name -eq $ClassicSlot -and $nameWas -and $nameWas -ne $ClassicSlot -and $null -ne $modeLast -and $classicVal -ne $modeLast) {
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
            if ($dir -ne $dirNow) {
                foreach ($a in $TrackDirSites) { [Sr3Mem]::Write($h, $a, [byte[]]@([byte][char]$dir), $true) }
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
            # START in a race: a short press takes a screenshot when it is let go, a long one leaves the race (Step-Start)
            $pad = New-Object Sr3Pad+XState
            $startDown = ([Sr3Pad]::XInputGetState(0, [ref]$pad) -eq 0) -and (($pad.Buttons -band 0x10) -ne 0)
            foreach ($act in (Step-Start $start $startDown $menu (Get-Date))) {
                if ($act -eq 'grab') {
                    try {
                        $sb = [Windows.Forms.Screen]::PrimaryScreen.Bounds; $shotHeld = New-Object Drawing.Bitmap $sb.Width, $sb.Height
                        $gr = [Drawing.Graphics]::FromImage($shotHeld); $gr.CopyFromScreen($sb.Location, [Drawing.Point]::Empty, $sb.Size); $gr.Dispose()
                    } catch { Log "Screenshot failed: $($_.Exception.Message)"; if ($shotHeld) { $shotHeld.Dispose() }; $shotHeld = $null; $start.HeldAt = $null }
                } elseif ($act -eq 'save' -and $shotHeld) {
                    try {
                        $shotDir = Join-Path (Split-Path -Parent $PSScriptRoot) 'Screenshots'; New-Item -ItemType Directory -Force $shotDir | Out-Null
                        $shotName = 'SR3_{0:yyyyMMdd_HHmmss}.png' -f $start.ShotAt
                        $shotHeld.Save((Join-Path $shotDir $shotName), [Drawing.Imaging.ImageFormat]::Png)
                        $shotUntil = (Get-Date).AddSeconds(3); Log "Screenshot: $shotName"
                    } catch { Log "Screenshot failed: $($_.Exception.Message)" }
                    $shotHeld.Dispose(); $shotHeld = $null
                } elseif ($act -eq 'drop' -and $shotHeld) { $shotHeld.Dispose(); $shotHeld = $null }  # that START began a new game
                elseif ($act -eq 'exit') { Request-RaceExit $h (Get-Date) }
            }
            if ($script:RaceExit) { Step-RaceExit $h (Get-Date) }
            Show-WatchdogNews
            if ($mode) {
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
            } elseif ($shotUntil -gt (Get-Date)) {
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
function Set-CarLists($game) {
    $h = [Sr3Mem]::Open($game.Id); $n = 0
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
            [Sr3Mem]::Suspend($h)
            try { foreach ($s in $todo) { $j = CallTo $s[0] ($cave + $s[1]); $j[0] = 0xE9; [Sr3Mem]::Write($h, $s[0], $j, $false); $n++ } }   # jmp rel32
            finally { [Sr3Mem]::Resume($h) }
        }
        # A car the game does not know by name (an added one, e.g. a Daytona car) gets the speedo's top speed like the ten:
        # 0x599A20 compares the car's name with the ten and sets vehicle +0x1708 for each; for any other name it skipped the
        # last write (jne at 0x599D7A), so +0x1708 stayed 0 and the speedo showed 0. All ten values are made the same way.
        $sp = [Sr3Mem]::Read($h, 0x599D78, 4)
        if (Same $sp (HexToBytes '3bc87510')) { [Sr3Mem]::Write($h, 0x599D7A, [byte[]]@(0x90, 0x90), $false) }
    } catch { Log "Car lists: $($_.Exception.Message)" } finally { [Sr3Mem]::Close($h) }
    Log $(if ($n -eq $CarListSites.Count) { 'Car lists: every car in every mode (each mode''s own cars first).' } else { "Car lists: $n of $($CarListSites.Count) changed." })
}

function Release-StuckKeys($game) {
    Log 'Leave this window open: when the game closes it releases any stuck Alt/Ctrl/Shift/Win key.'
    Set-MenuTimers $game
    Set-CarLists $game
    Watch-Tracks $game $script:GameExePath
    foreach ($vk in 0x12, 0xA4, 0xA5, 0x11, 0xA2, 0xA3, 0x10, 0xA0, 0xA1, 0x5B, 0x5C) { [SR3.Keys]::keybd_event([byte]$vk, 0, 2, [UIntPtr]::Zero) }
    Log 'Game closed. Modifier keys released.'
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
    Log "Starting SEGA Rally 3 through TeknoParrot (profile '$($gameSetup.profile)')..."
    Start-Process -FilePath $gameSetup.teknoparrot -ArgumentList "--profile=$($gameSetup.profile).xml" -WorkingDirectory $tpDir
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
Log "Rally.exe running (pid $($proc.Id)). Waiting for the game to finish booting..."
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

    # safety: every site must still hold the original bytes, or ours. The cave's "SR3C" signature
    # also recognises an older build of this patch, which is then replaced in place.
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
    if ($older) { Log 'An older build of the camera patch is active; replacing it.'; $already = $false }
    elseif ($already) { Log 'Camera patch was already applied; updating the tuning values.' }

    if ($Off) {   # live un-patch: unhook first, then clear the cave
        [Sr3Mem]::Suspend($h)
        try { Remove-Cycle $h; for ($i = $Patches.Count - 1; $i -ge 0; $i--) { [Sr3Mem]::Write($h, $Patches[$i].VA, $Patches[$i].OrigB, $false) } }
        finally { [Sr3Mem]::Resume($h) }
        foreach ($p in $Patches) { if (-not (Same ([Sr3Mem]::Read($h, $p.VA, $p.OrigB.Length)) $p.OrigB)) { throw ("Restore verification failed at 0x{0:X}" -f $p.VA) } }
        Log 'Camera patch REMOVED from the running game (original camera).'
        return
    }

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
finally { [Sr3Mem]::Close($h) }
if ($launched -and -not $Off) {
    if (-not $NoWatchdog) { Start-Watchdog $proc }                # the patch is in and TeknoParrot's checks are long done
    Release-StuckKeys $proc
    Stop-Watchdog
}

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
    -Cores <n>                     -> CPU threads the game may use (default 4; 0 = all). Keeps the
                                      memory its cached videos take low enough to avoid crashes.
  In a race, the game's View Change button cycles through every camera: the game's own
  ("Game:", white: Chase, Bumper, Bonnet), each profile ("CamLab:", lime), then the debug
  cameras the game hides ("Debug:", orange: far chase, cockpit, the cockpit from the driver's
  seat, wheel, car rotate, free cams).
  The name shows for 2 seconds, 14% of the way down the screen (with a mouse/WASD hint on
  the cameras you can steer).
  Car rotate cam: mouse left/right orbits, forward/back tilts, W/S zoom in and out.
  The key below Esc (~) resets the car rotate and free cams. Free cams: mouse looks, WASD moves, Space/Ctrl up/down.
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
param([string]$CameraProfile = '', [switch]$List, [switch]$NoLaunch, [switch]$Canary, [switch]$Off, [int]$DelaySeconds = 20, [string]$ProfilesFile = '', [int]$Overlay = -1, [int]$Cores = 4)

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

$Root      = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
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
function Log($m) { Write-Host ("[{0:HH:mm:ss}] {1}" -f (Get-Date), $m) }

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
$CycleCode = '9c60e8000000005d81ed071000008b35ecb49e0085f60f843b03000083c61881be1005000008b86e000f85280300008dbe1005000039be340200000f85160300008b862c0200003b452875093975580f849e01000083f8010f82f9020000c7855c2200000000000083f8150f87e602000031c931d239c173288b9c8e3402000039fb741a83fa0c731539755875083b95bc0000007308899c95802100004241ebd439755874098995bc00000089455c89956022000031c983f90c735d8b9c8de021000083fbff745185db782b01f3833b0074215131c939d1730c399c8d80210000741041ebf083fa0c7308899c9580210000425941ebc081e3ffffff7f01f3833b0074f083fa0c73eb899c95802100004289955c220000ebdb8b4d208d1c1183fb150f872f02000083bd5c22000000740749018d5c22000089552c89755889be34020000bb0100000031c93b8d6022000073128b848d8021000089849e340200004341ebe6b9010000003b4d20730b89bc9e340200004341ebf08b8d6022000039d173128b848d8021000089849e340200004341ebea899e2c020000895d288b85a80f000085c074054839d8722e8b452483f8fe751c8d8ec408000031c039d8730c398c8634020000741140ebf031c0eb0a85c07406038560220000898630020000c7451cffffffffc785b0000000010000008b86300200003b451c0f84550100008b4d1c83f9ff74358d51013b5528720231d239d074278b948634020000399690010000750d8b948e34020000899690010000898e30020000e9180100003b862c0200000f830c01000089451c8d4801898da80f00008b8c863402000029f131d281f9ec0e0000741081f9780c0000740881f9681d00007501428995a00f0000e8b001000031c985c074093b8560220000760141890d9457a60085c074173b8560220000762d89c12b8d602200003b4d20732089c8e8fc0100008b8c85000e0000898d600e0000c1e0058d840500010000eb668b9c8634020000813bb8b86e0075095031c0e8cc0100005829f33b855c220000750681cb000000808d85e0000000c785600e0000ffffffff31c983f90c7327399c8db0210000751b8b848d102200008985600e000089c8c1e0058d840500200000eb0341ebd48945508b8db0000000c785b00000000000000085c975068b4514894510e80c030000837d10000f8ec8000000ff4d108b451885c00f8eba000000f72578db7e00b938040000f7f183f8087d05b808000000508d5d08e8680100005985c00f848a00000089c351a178db7e00b90e000000f7e1b964000000f7f18985b40000008b45508985a40f00008b04248b8d600e0000e8b10100005883bda00f0000007454506bc00b31d2b90a000000f7f10185b400000058d1e883f8087d05b808000000508d9d980f0000e8f60000005985c0742389c38d95b00f00008995a40f000089c8b9e0e0e0ffe85c010000eb07c7451000000000619da10cd17e00c3608dbe381a0000813ff0bd6e0075708d95402200008b9d5c22000085db744c39d875488b8f9401000039d1745285c9744e898d582200008b01350000008089028b41048942048b41088942088b410c350000008089420c8b41108942108b4114894214899794010000eb14399794010000750c8b8d58220000898f9401000061c3565751526bd05c8db41500050000bf883c6700b90b000000f3a5bfd03c6700b90c000000f3a5833de83c67000075118b555885d2740ac782c0080000000070425a595f5ec33b430475038b03c3508b0b85c9740c518b11ff5208c70300000000588943048b555485d275228d4d6051ff15f441670085c074418d4d705150ff150442670085c0743289455489c2538d8d80000000516a006a046a006a016a006a0168bc0200006a00ff7304ff350cd17e00ffd285c07c038b03c3c70300000000c743040000000031c0c35131d2b916000000f7f185c075014089c76bc00731d2b90a000000f7f185c07501408985b800000089f9f7d931d2e86200000089f931d2e85900000031c989faf7dae84e00000031c989fae8450000008b8db800000089cae8380000008b8db800000089caf7dae8290000008b8db800000089caf7d9e81a0000008b8db8000000f7d989cae80b00000031c931d258e806000000c3b8000000d056898da00000008bb5b400000001d689b5a40000008b3574db7e0001ce89b5a80000008b3578db7e0001d689b5ac000000506a218db5a0000000566affffb5a40f00006a00538b33ff56385ec38b35ecb49e0085f6742a83c6188bbe900100008d86ec0e000039c774168d86780c000039c7740c8d86681d000039c77402eb01c38b35ecb49e0085f60f843904000083c61881be1005000008b86e000f85260400008bbe900100008d86ec0e0000bb0100000039c774288d86780c0000bb0200000039c774198d86681d000039c7740fc785300f000001000000e9e903000083bd8c0e0000000f85f60000008d8da00e000051ff15f441670085c00f84c703000089c2528d8db00e00005152ff15044267005a8985800e0000528d8dc00e00005152ff15044267005a8985840e0000528d8dd00e00005152ff15044267005a8985880e0000528d8d400f00005152ff15044267005a8985900e00008d8d600f00005251ff15f44167005a85c0745b8d8d700f0000525150ff15044267005a8985940e00008d8df00e00005152ff150442670089858c0e000083bd800e000000742883bd840e000000741f83bd880e000000741683bd900e000000740d83bd940e000000740485c07519c7858c0e000000000000c785300f000002000000e9e6020000ff958c0e00008d8d380f0000c701000000005150ff95900e0000ff95940e00003b85380f0000740fc785300f000003000000e9af020000c785300f000004000000c785340f000000000000a174db7e00d1e88985280f0000a178db7e00d1e889852c0f00008d8d700e000051ff95800e000031c08985200f00008985240f000083bd680e00000075248b85700e00002b85280f00008985200f00008b85740e00002b852c0f00008985240f0000c785680e000000000000ffb52c0f0000ffb5280f0000ff95840e0000c785640e00000100000068c0000000ff95880e00005068dc000000ff95880e00005909c825008000008b8dd80f00008985d80f000085c0740b85c9750789f98b07ff5004f30f2a85200f0000f30f2a8d240f0000f30f5985100f0000f30f598d100f000083fb010f8505010000f30f2a8d240f0000f30f598dd00f0000f30f10160f57db0f2fd3761ef30f10daf30f599d140f0000f30f5ec3f30f5995180f0000f30f5ecaeb060f57c00f57c9f30f1186a8010000f30f118eb80100006a536a57e8ae010000f30f1186ac0100000f57c0f30f1186bc010000f30f10160f57db0f2fd30f8688000000f30f5995180f00008b860c05000085c07476f30f1086ac010000f30f59c2f30f584720f30f5800f30f5f85e00f0000f30f5d85e40f0000f30f5c00f30f5c4720f30f5ec2f30f1186ac010000f30f1086b8010000f30f59c2f30f584748f30f584004f30f5f85e80f0000f30f5d85ec0f0000f30f5c4004f30f5c4748f30f5ec2f30f1186b8010000c3f30f1097300200000f57db0f2fd3760af30f5ec2f30f5ecaeb12f30f59851c0f0000f30f598d1c0f0000eb30f30f10d9f30f59daf30f589f68020000f30f5d9d900f0000f30f5f9d940f0000f30f5c9f68020000f30f5edaf30f10cbf30f1186a8010000f30f118eac0100000f57c0f30f1186c40100006a576a53e882000000f30f1186b00100006a446a41e871000000f30f1186b40100006a206a11e860000000f30f1186b8010000c3c785680e00000100000083bd640e0000007443c785640e0000000000008b755885f6743231c08986a80100008986ac0100008986b00100008986b40100008986b80100008986bc0100008986c00100008986c4010000c35331dbff74240cff95880e0000660985340f000066a90080740143ff742408ff95880e000066a9008074014bf30f2ac35bc208009c60e8000000005d81ed751b0000e81bfbffff619d68001e5f00c39c60e8000000005d81ed901b0000e800fbffff619d68e03f5f00c39c60e8000000005d81edab1b00008b4d0885c97414518b11ff5208c7450800000000c7450c000000008b8d980f000085c9741a518b11ff5208c785980f000000000000c7859c0f000000000000619d6820125900c3'
$CycleSize = 0x3000; $CycleDraw = 0x1000; $CycleLost = 0x1ba4; $CycleRot = 0x1b6e; $CycleFree = 0x1b89
$CycleMaxSlots = 21; $CycleSlotBytes = 0x5C
$HookDrawVA = 0x591C4D; $HookDrawOrig = HexToBytes 'a10cd17e00'   # mov eax,[device] before EndScene/Present
$HookLostVA = 0x591B01; $HookLostOrig = HexToBytes 'e81af7ffff'   # call 0x591220 (frees resources before Reset)
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
    $code = HexToBytes $CycleCode
    $base = Find-Cycle $h
    if (-not $base) {
        if (-not (Same ([Sr3Mem]::Read($h, $HookDrawVA, 5)) $HookDrawOrig) -or -not (Same ([Sr3Mem]::Read($h, $HookLostVA, 5)) $HookLostOrig)) {
            Log 'Camera cycle not installed: unexpected bytes at its hook sites.'; return
        }
        $base = [Sr3Mem]::Alloc($h, $CycleSize)
        [Sr3Mem]::Write($h, $base + $CycleDraw, $code, $true)
    }
    elseif (-not (Same ([Sr3Mem]::Read($h, $base + $CycleDraw, $code.Length)) $code)) {
        # a newer build: never rewrite code the game may be running; move to a fresh block,
        # keeping the state (font, camera list) and leaving the old one as it is
        $old = $base
        Restore-CockpitSeat $h $old
        $base = [Sr3Mem]::Alloc($h, $CycleSize)
        [Sr3Mem]::Write($h, $base, ([Sr3Mem]::Read($h, $old, $CycleDraw)), $true)
        [Sr3Mem]::Write($h, $base + 0xF98, (New-Object byte[] 0x10), $true)   # hint font, hint flag, text: start empty
        [Sr3Mem]::Write($h, $base + 0x2180, ([Sr3Mem]::Read($h, $old + 0x2180, 4 * $CycleGameCams)), $true)   # the game's list entries
        [Sr3Mem]::Write($h, $base + $CycleDraw, $code, $true)
    }
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
function Release-StuckKeys($game) {
    Log 'Leave this window open: when the game closes it releases any stuck Alt/Ctrl/Shift/Win key.'
    $game.WaitForExit()
    foreach ($vk in 0x12, 0xA4, 0xA5, 0x11, 0xA2, 0xA3, 0x10, 0xA0, 0xA1, 0x5B, 0x5C) { [SR3.Keys]::keybd_event([byte]$vk, 0, 2, [UIntPtr]::Zero) }
    Log 'Game closed. Modifier keys released.'
}

# ---- launch (unless the game is already running) ----
$proc = Get-Process -Name Rally -ErrorAction SilentlyContinue | Select-Object -First 1
$launched = -not $proc
if (-not $proc) {
    if ($NoLaunch) { throw 'Rally.exe is not running.' }
    Log 'Starting SEGA Rally 3 through TeknoParrot...'
    Start-Process -FilePath (Join-Path $Root 'TeknoParrotUi.exe') -ArgumentList '--profile=SR3.xml' -WorkingDirectory $Root
    $t0 = Get-Date
    while (-not ($proc = Get-Process -Name Rally -ErrorAction SilentlyContinue | Select-Object -First 1)) {
        if (((Get-Date) - $t0).TotalSeconds -gt 120) { throw 'Rally.exe did not start within 2 minutes.' }
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
    Log ('  Strength={0:0.00}  FadeIn={1}-{2} km/h  Stiffness={3}-{4}  Damping={5}  MaxAngle={6} deg  CapStiffness={7}' -f $Strength, $FadeInStartKmh, $FadeInFullKmh, $StiffnessMin, $StiffnessMax, $Damping, $MaxAngleDeg, $CapStiffness)
    if ($Framing) { Log ('  Framing: distance {0} m, height {1} m, field of view {2} deg' -f $Distance, $Height, $Fov) }
    else { Log '  Framing: SR3 default' }
}
finally { [Sr3Mem]::Close($h) }
if ($launched -and -not $Off) { Release-StuckKeys $proc }

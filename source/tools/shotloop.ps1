# Read-only: every few seconds saves a half-size screenshot plus the chase camera's state.
param([int]$Seconds = 240, [int]$EveryMs = 5000, [string]$Dir = "$PSScriptRoot\shots")
Add-Type -AssemblyName System.Drawing, System.Windows.Forms
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class SL {
  [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(int a, bool i, int pid);
  [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, IntPtr n, out IntPtr r);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public static IntPtr H;
  public static void Open(int pid) { H = OpenProcess(0x0410, false, pid); }
  public static byte[] R(long a, int n) { var b = new byte[n]; IntPtr r; ReadProcessMemory(H, (IntPtr)a, b, (IntPtr)n, out r); return b; }
}
'@
[void][SL]::SetProcessDPIAware()
New-Item -ItemType Directory -Force $Dir | Out-Null
while (-not ($gp = Get-Process Rally -ErrorAction SilentlyContinue | Select-Object -First 1)) { Start-Sleep -Milliseconds 500 }
Start-Sleep 20
[SL]::Open($gp.Id)
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$log = Join-Path $Dir 'shots.csv'
'n,time,camoff,index,framing,eyeBehind,eyeAbove,kmh' | Set-Content $log
$sw = [Diagnostics.Stopwatch]::StartNew(); $n = 0; $prev = $null; $pt = 0
while ($sw.Elapsed.TotalSeconds -lt $Seconds) {
  $t0 = $sw.ElapsedMilliseconds
  $mgr = [BitConverter]::ToUInt32([SL]::R(0x9EB4EC, 4), 0) + 0x18
  $m = [SL]::R($mgr, 0x240); $cur = [BitConverter]::ToUInt32($m, 0x190) - $mgr; $idx = [BitConverter]::ToInt32($m, 0x230)
  $b = [SL]::R($mgr + 0x510, 0x100); $fr = [BitConverter]::ToInt32([SL]::R(0x673C80 + 0x68, 4), 0)
  $F = { param($o) [BitConverter]::ToSingle($b, $o) }
  $fx = & $F 8; $fz = & $F 0x10
  $ex = & $F 0x48; $ey = & $F 0x4C; $ez = & $F 0x50; $px = & $F 0x90; $py = & $F 0x94; $pz = & $F 0x98
  $behind = [Math]::Sqrt(($px - $ex) * ($px - $ex) + ($pz - $ez) * ($pz - $ez))
  $t = $sw.Elapsed.TotalSeconds; $kmh = 0
  if ($prev) { $kmh = [Math]::Sqrt(($px - $prev[0]) * ($px - $prev[0]) + ($pz - $prev[1]) * ($pz - $prev[1])) / ($t - $pt) * 3.6 }
  $prev = @($px, $pz); $pt = $t
  $bmp = New-Object Drawing.Bitmap $bounds.Width, $bounds.Height
  $g = [Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($bounds.X, $bounds.Y, 0, 0, $bmp.Size)
  $small = New-Object Drawing.Bitmap $bmp, ([int]($bounds.Width / 2)), ([int]($bounds.Height / 2))
  $small.Save((Join-Path $Dir ('s{0:D3}.png' -f $n)), [Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $bmp.Dispose(); $small.Dispose()
  '{0},{1:N1},{2:X},{3},{4},{5:N2},{6:N2},{7:N0}' -f $n, $t, $cur, $idx, $fr, $behind, ($ey - $py), $kmh | Add-Content $log
  $n++
  $wait = $EveryMs - ($sw.ElapsedMilliseconds - $t0); if ($wait -gt 0) { Start-Sleep -Milliseconds $wait }
}

# Read-only: samples the live chase camera's geometry (relative to the car) and saves a screenshot.
param([int]$Samples = 8, [int]$IntervalMs = 250, [string]$Shot = '')
Add-Type -AssemblyName System.Drawing
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class PR {
  [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(int a, bool i, int pid);
  [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, IntPtr n, out IntPtr r);
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  public static IntPtr H;
  public static void Open(int pid) { H = OpenProcess(0x0410, false, pid); }
  public static byte[] R(long a, int n) { var b = new byte[n]; IntPtr r; ReadProcessMemory(H, (IntPtr)a, b, (IntPtr)n, out r); return b; }
}
'@
[void][PR]::SetProcessDPIAware()
[PR]::Open((Get-Process Rally).Id)
$mgr = [BitConverter]::ToUInt32([PR]::R(0x9EB4EC, 4), 0) + 0x18
$cam = $mgr + 0x510
$m = [PR]::R($mgr, 0x240)
'camera in use: mgr+{0:X}   list index {1}' -f ([BitConverter]::ToUInt32($m, 0x190) - $mgr), [BitConverter]::ToInt32($m, 0x230)
$cave = [PR]::R(0x673C80, 0x80); $f = { param($b, $o) [BitConverter]::ToSingle($b, $o) }
'cave: framing {0}  dist {1:N2} height {2:N2} fov {3:N1}  kmin/kmax {4:N1}/{5:N1} mult {6:N2}' -f [BitConverter]::ToInt32($cave, 0x68), (& $f $cave 0x6C), (& $f $cave 0x70), (& $f $cave 0x74), (& $f $cave 0x18), (& $f $cave 0x1C), (& $f $cave 0x50)
$prev = $null; $sw = [Diagnostics.Stopwatch]::StartNew(); $pt = 0
for ($k = 0; $k -lt $Samples; $k++) {
  $b = [PR]::R($cam, 0x3B4); $t = $sw.Elapsed.TotalSeconds
  $c = 0..(0x3B4 / 4 - 1) | ForEach-Object { [BitConverter]::ToSingle($b, 4 * $_) }
  $fx = $c[2]; $fz = $c[4]
  $e = @($c[0x48/4], $c[0x4C/4], $c[0x50/4]); $p = @($c[0x90/4], $c[0x94/4], $c[0x98/4]); $l = @($c[0xCC/4], $c[0xD0/4], $c[0xD4/4])
  $back = ($p[0] - $e[0]) * $fx + ($p[2] - $e[2]) * $fz
  $side = ($p[0] - $e[0]) * $fz - ($p[2] - $e[2]) * $fx
  $ahead = ($l[0] - $p[0]) * $fx + ($l[2] - $p[2]) * $fz
  $dx = $l[0] - $e[0]; $dz = $l[2] - $e[2]; $pitch = [Math]::Atan2($l[1] - $e[1], [Math]::Sqrt($dx*$dx + $dz*$dz)) * 180 / [Math]::PI
  $kmh = 0; if ($prev) { $mx = $p[0] - $prev[0]; $mz = $p[2] - $prev[2]; $kmh = [Math]::Sqrt($mx*$mx + $mz*$mz) / ($t - $pt) * 3.6 }
  '{0,4:N0} km/h | eye {1,5:N2} behind {2,5:N2} side {3,5:N2} above | look {4,5:N2} ahead {5,5:N2} above | pitch {6,6:N2} | fov {7:N1}' -f $kmh, $back, $side, ($e[1] - $p[1]), $ahead, ($l[1] - $p[1]), $pitch, $c[0x3B0/4]
  $prev = $p; $pt = $t
  Start-Sleep -Milliseconds $IntervalMs
}
if ($Shot) {
  Add-Type -AssemblyName System.Windows.Forms; $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
  $bmp = New-Object Drawing.Bitmap $bounds.Width, $bounds.Height
  $g = [Drawing.Graphics]::FromImage($bmp); $g.CopyFromScreen($bounds.X, $bounds.Y, 0, 0, $bmp.Size)
  $small = New-Object Drawing.Bitmap $bmp, ([int]($bounds.Width / 2)), ([int]($bounds.Height / 2))
  $small.Save($Shot, [Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $bmp.Dispose(); $small.Dispose()
  "screenshot: $Shot ($($bounds.Width)x$($bounds.Height), saved at half size)"
}

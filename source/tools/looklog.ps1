# Read-only: logs the chase camera's framing against speed to a CSV (eye and look-at relative to
# the camera's car point, along the car's heading).
param([int]$Seconds = 120, [int]$IntervalMs = 200, [string]$Out = "$PSScriptRoot\looklog.csv")
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class LL {
  [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(int a, bool i, int pid);
  [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, IntPtr n, out IntPtr r);
  public static IntPtr H;
  public static void Open(int pid) { H = OpenProcess(0x0410, false, pid); }
  public static float[] F(long a, int n) { var b = new byte[n*4]; IntPtr r; ReadProcessMemory(H, (IntPtr)a, b, (IntPtr)(n*4), out r); var f = new float[n]; for (int i = 0; i < n; i++) f[i] = BitConverter.ToSingle(b, i*4); return f; }
  public static uint U(long a) { var b = new byte[4]; IntPtr r; ReadProcessMemory(H, (IntPtr)a, b, (IntPtr)4, out r); return BitConverter.ToUInt32(b, 0); }
}
'@
[LL]::Open((Get-Process Rally).Id)
'time,kmh,camoff,eyeBehind,eyeSide,eyeAbove,lookAhead,lookSide,lookAbove,pitch,fov' | Set-Content $Out
$sw = [Diagnostics.Stopwatch]::StartNew(); $prev = $null; $pt = 0
while ($sw.Elapsed.TotalSeconds -lt $Seconds) {
  $mgr = [LL]::U(0x9EB4EC) + 0x18; $cur = [LL]::U($mgr + 0x190) - $mgr
  $c = [LL]::F($mgr + 0x510, 0x3B4 / 4); $t = $sw.Elapsed.TotalSeconds
  $fx = $c[2]; $fz = $c[4]
  $e = @($c[0x48/4], $c[0x4C/4], $c[0x50/4]); $p = @($c[0x90/4], $c[0x94/4], $c[0x98/4]); $l = @($c[0xCC/4], $c[0xD0/4], $c[0xD4/4])
  $kmh = 0; if ($prev) { $mx = $p[0] - $prev[0]; $mz = $p[2] - $prev[2]; $kmh = [Math]::Sqrt($mx*$mx + $mz*$mz) / ($t - $pt) * 3.6 }
  $dx = $l[0] - $e[0]; $dz = $l[2] - $e[2]; $pitch = [Math]::Atan2($l[1] - $e[1], [Math]::Sqrt($dx*$dx + $dz*$dz)) * 180 / [Math]::PI
  '{0:N2},{1:N0},{2:X},{3:N3},{4:N3},{5:N3},{6:N3},{7:N3},{8:N3},{9:N2},{10:N1}' -f $t, $kmh, $cur,
    (($p[0] - $e[0]) * $fx + ($p[2] - $e[2]) * $fz), (($p[0] - $e[0]) * $fz - ($p[2] - $e[2]) * $fx), ($e[1] - $p[1]),
    (($l[0] - $p[0]) * $fx + ($l[2] - $p[2]) * $fz), (($l[0] - $p[0]) * $fz - ($l[2] - $p[2]) * $fx), ($l[1] - $p[1]), $pitch, $c[0x3B0/4] | Add-Content $Out
  $prev = $p; $pt = $t
  Start-Sleep -Milliseconds $IntervalMs
}

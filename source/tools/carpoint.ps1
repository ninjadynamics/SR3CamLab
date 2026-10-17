# Read-only: where the chase camera's car point (cam+0x90) and eye sit in the car's own frame
# (car = [mgr+0x1C8], matrix at car+0x135C: three axis rows of 4 floats, then the position).
param([int]$Samples = 10, [int]$IntervalMs = 300)
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class CP {
  [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(int a, bool i, int pid);
  [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, IntPtr n, out IntPtr r);
  public static IntPtr H;
  public static void Open(int pid) { H = OpenProcess(0x0410, false, pid); }
  public static byte[] R(long a, int n) { var b = new byte[n]; IntPtr r; ReadProcessMemory(H, (IntPtr)a, b, (IntPtr)n, out r); return b; }
}
'@
[CP]::Open((Get-Process Rally).Id)
$mgr = [BitConverter]::ToUInt32([CP]::R(0x9EB4EC, 4), 0) + 0x18
for ($k = 0; $k -lt $Samples; $k++) {
  $car = [BitConverter]::ToUInt32([CP]::R($mgr + 0x1C8, 4), 0)
  $m = [CP]::R($car + 0x135C, 0x40); $c = [CP]::R($mgr + 0x510, 0x100)
  $cur = [BitConverter]::ToUInt32([CP]::R($mgr + 0x190, 4), 0) - $mgr; $idx = [BitConverter]::ToInt32([CP]::R($mgr + 0x230, 4), 0)
  $ax = 0..2 | ForEach-Object { $o = 16 * $_; ,@([BitConverter]::ToSingle($m, $o), [BitConverter]::ToSingle($m, $o + 4), [BitConverter]::ToSingle($m, $o + 8)) }
  $pos = @([BitConverter]::ToSingle($m, 0x30), [BitConverter]::ToSingle($m, 0x34), [BitConverter]::ToSingle($m, 0x38))
  $rel = { param($o) $d = @(([BitConverter]::ToSingle($c, $o) - $pos[0]), ([BitConverter]::ToSingle($c, $o + 4) - $pos[1]), ([BitConverter]::ToSingle($c, $o + 8) - $pos[2]))
           (0..2 | ForEach-Object { $a = $ax[$_]; '{0,6:F2}' -f ($d[0]*$a[0] + $d[1]*$a[1] + $d[2]*$a[2]) }) -join ' ' }
  'cam +{0:X} idx {1,2} | car axes x({2:F2},{3:F2},{4:F2}) y({5:F2},{6:F2},{7:F2}) z({8:F2},{9:F2},{10:F2}) | car point on x/y/z: {11} | eye on x/y/z: {12}' -f $cur, $idx,
    $ax[0][0], $ax[0][1], $ax[0][2], $ax[1][0], $ax[1][1], $ax[1][2], $ax[2][0], $ax[2][1], $ax[2][2], (& $rel 0x90), (& $rel 0x48)
  Start-Sleep -Milliseconds $IntervalMs
}

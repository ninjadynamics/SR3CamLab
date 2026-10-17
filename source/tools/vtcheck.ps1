Add-Type @'
using System; using System.Runtime.InteropServices;
public static class VT {
  [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(int a, bool i, int pid);
  [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, IntPtr n, out IntPtr r);
  public static IntPtr H;
  public static void Open(int pid) { H = OpenProcess(0x0410, false, pid); }
  public static byte[] R(long a, int n) { var b = new byte[n]; IntPtr r; ReadProcessMemory(H, (IntPtr)a, b, (IntPtr)n, out r); return b; }
}
'@
[VT]::Open((Get-Process Rally).Id)
$hk = [VT]::R(0x591C4D, 5)
$base = 0x591C52 + [BitConverter]::ToInt32($hk, 1) - 0x1000
'present hook {0}  -> block {1:X8} magic {2}' -f (($hk | ForEach-Object { $_.ToString('x2') }) -join ''), $base, [Text.Encoding]::ASCII.GetString([VT]::R($base, 4))
foreach ($v in 0x6EBB3C, 0x6ECBA4, 0x6ECC94) {
  $t = [BitConverter]::ToUInt32([VT]::R($v, 4), 0)
  'vtable {0:X}: {1:X8}  in current block: {2}' -f $v, $t, (($t -band 0xFFFF0000) -eq $base)
}

param([int]$Set = -1)
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class PV {
  [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(int a, bool i, int pid);
  [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, IntPtr n, out IntPtr r);
  [DllImport("kernel32.dll")] static extern bool WriteProcessMemory(IntPtr h, IntPtr a, byte[] b, IntPtr n, out IntPtr r);
  public static IntPtr H;
  public static void Open(int pid) { H = OpenProcess(0x0438, false, pid); }
  public static byte[] R(long a, int n) { var b = new byte[n]; IntPtr r; ReadProcessMemory(H, (IntPtr)a, b, (IntPtr)n, out r); return b; }
  public static bool W(long a, byte[] b) { IntPtr r; return WriteProcessMemory(H, (IntPtr)a, b, (IntPtr)b.Length, out r); }
}
'@
[PV]::Open((Get-Process Rally).Id)
$i = { param($a) [BitConverter]::ToInt32([PV]::R($a, 4), 0) }
if ($Set -ge 0) { 'write: ' + [PV]::W(0xA65794, [BitConverter]::GetBytes([int]$Set)) }
'PVS off flag [A65794] = {0}   freeze [A65790] = {1}   attract-pass flag [9F0FAC] = {2}   viewport [9F05F0] = {3}   pvs context [9F05F4] = {4}' -f (& $i 0xA65794), (& $i 0xA65790), (& $i 0x9F0FAC), (& $i 0x9F05F0), (& $i 0x9F05F4)
$ctx = 0xA65650 + 20 * (& $i 0x9F05F4)
'context: leaf {0}  previous leaf {1}  nodes {2}' -f [BitConverter]::ToInt32([PV]::R($ctx + 8, 4), 0), [BitConverter]::ToInt32([PV]::R($ctx + 12, 4), 0), [BitConverter]::ToInt32([PV]::R($ctx + 16, 4), 0)
$cam = 0x9EB9A0 + 0x4D0 * (& $i 0x9F05F0); $p = [PV]::R($cam, 12)
'PVS camera position: {0:0.0} {1:0.0} {2:0.0}' -f [BitConverter]::ToSingle($p, 0), [BitConverter]::ToSingle($p, 4), [BitConverter]::ToSingle($p, 8)

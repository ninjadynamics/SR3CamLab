# Finds the live chase camera, then every camera-to-world matrix (right, up, forward rows +
# eye row) whose eye row equals the camera's eye, and prints its forward vector and pitch.
Add-Type @'
using System; using System.Runtime.InteropServices; using System.Collections.Generic;
public static class VM {
  [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(int a, bool i, int pid);
  [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, IntPtr n, out IntPtr r);
  [DllImport("kernel32.dll")] static extern int VirtualQueryEx(IntPtr h, IntPtr a, out MBI m, int l);
  [StructLayout(LayoutKind.Sequential)] public struct MBI { public IntPtr Base, AllocBase; public uint AllocProt; public IntPtr Size; public uint State, Protect, Type; }
  public static IntPtr H;
  public static void Open(int pid) { H = OpenProcess(0x0410, false, pid); }
  public static byte[] Read(long a, int n) { var b = new byte[n]; IntPtr r; return ReadProcessMemory(H, (IntPtr)a, b, (IntPtr)n, out r) ? b : null; }
  static float F(byte[] b, int i) { return BitConverter.ToSingle(b, i); }
  public static List<long> Cams() {
    var res = new List<long>(); long a = 0x10000; MBI m;
    while (a < 0x7FFF0000 && VirtualQueryEx(H, (IntPtr)a, out m, Marshal.SizeOf(typeof(MBI))) != 0) {
      long size = (long)m.Size;
      if (m.State == 0x1000 && (m.Protect & 0xCC) != 0 && (m.Protect & 0x100) == 0 && size < 512L*1024*1024) {
        var b = Read(a, (int)size);
        if (b != null) for (int i = 0; i + 0x3B4 <= b.Length; i += 4)
          if (BitConverter.ToUInt32(b, i) == 0x6EB808 && BitConverter.ToUInt32(b, i + 4) == 1 && Math.Abs(F(b, i + 0x48)) > 0.001f) res.Add(a + i);
      }
      a = (long)m.Base + size;
    }
    return res;
  }
  public static List<string> Mats(float x, float y, float z) {
    var res = new List<string>(); long a = 0x10000; MBI m;
    while (a < 0x7FFF0000 && VirtualQueryEx(H, (IntPtr)a, out m, Marshal.SizeOf(typeof(MBI))) != 0) {
      long size = (long)m.Size;
      if (m.State == 0x1000 && (m.Protect & 0xCC) != 0 && (m.Protect & 0x100) == 0 && size < 512L*1024*1024) {
        var b = Read(a, (int)size);
        if (b != null) for (int i = 48; i + 12 <= b.Length; i += 4) {
          if (!(Math.Abs(F(b, i) - x) <= 0.01f && Math.Abs(F(b, i + 4) - y) <= 0.01f && Math.Abs(F(b, i + 8) - z) <= 0.01f)) continue;
          // rows: right @-48, up @-32, forward @-16 (4 floats each, w = 0)
          float rx = F(b, i-48), ry = F(b, i-44), rz = F(b, i-40), ux = F(b, i-32), uy = F(b, i-28), uz = F(b, i-24), fx = F(b, i-16), fy = F(b, i-12), fz = F(b, i-8);
          double lr = Math.Sqrt(rx*rx+ry*ry+rz*rz), lu = Math.Sqrt(ux*ux+uy*uy+uz*uz), lf = Math.Sqrt(fx*fx+fy*fy+fz*fz);
          if (!(Math.Abs(lr-1) <= 0.01 && Math.Abs(lu-1) <= 0.01 && Math.Abs(lf-1) <= 0.01)) continue;
          if (Math.Abs(rx*fx+ry*fy+rz*fz) > 0.01 || Math.Abs(ux*fx+uy*fy+uz*fz) > 0.01) continue;
          res.Add(string.Format("{0:X8} fwd ({1:F3},{2:F3},{3:F3}) up ({4:F3},{5:F3},{6:F3}) pitch {7:F2} deg", a + i - 48, fx, fy, fz, ux, uy, uz, Math.Asin(fy) * 180 / Math.PI));
        }
      }
      a = (long)m.Base + size;
    }
    return res;
  }
}
'@
[VM]::Open((Get-Process Rally).Id)
foreach ($c in [VM]::Cams()) {
  $b = [VM]::Read($c, 0x3B4)
  $e = @([BitConverter]::ToSingle($b, 0x48), [BitConverter]::ToSingle($b, 0x4C), [BitConverter]::ToSingle($b, 0x50))
  $p = @([BitConverter]::ToSingle($b, 0x90), [BitConverter]::ToSingle($b, 0x94), [BitConverter]::ToSingle($b, 0x98))
  $t = @([BitConverter]::ToSingle($b, 0xCC), [BitConverter]::ToSingle($b, 0xD0), [BitConverter]::ToSingle($b, 0xD4))
  "camera {0:X8}: eye ({1:F3},{2:F3},{3:F3}) point ({4:F3},{5:F3},{6:F3}) look-at ({7:F3},{8:F3},{9:F3}) fov {10}" -f $c, $e[0], $e[1], $e[2], $p[0], $p[1], $p[2], $t[0], $t[1], $t[2], [BitConverter]::ToSingle($b, 0x3B0)
  [VM]::Mats([single]$e[0], [single]$e[1], [single]$e[2]) | ForEach-Object { "   matrix $_" }
}

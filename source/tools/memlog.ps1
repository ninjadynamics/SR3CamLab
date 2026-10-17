# Logs SEGA Rally 3's memory every 2 s: private / virtual MB, free address space and the largest
# free block (a 32-bit game fails allocations when no free block is big enough), plus the PVS flag.
param([string]$Out = "$PSScriptRoot\memlog.csv", [int]$IntervalMs = 2000)
Add-Type @'
using System; using System.Runtime.InteropServices;
public static class ML {
  [StructLayout(LayoutKind.Sequential)] public struct MBI { public IntPtr Base, AllocBase; public uint AllocProtect; public IntPtr Size; public uint State, Protect, Type; }
  [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(int a, bool i, int pid);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
  [DllImport("kernel32.dll")] static extern int VirtualQueryEx(IntPtr h, IntPtr a, out MBI m, int n);
  [DllImport("kernel32.dll")] static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, IntPtr n, out IntPtr r);
  public static IntPtr H;
  public static void Open(int pid) { H = OpenProcess(0x0410, false, pid); }
  public static void Close() { CloseHandle(H); H = IntPtr.Zero; }
  public static long[] Free() {            // total free, largest free block (bytes) in the 4 GB space
    long a = 0x10000, total = 0, big = 0; MBI m;
    while (a < 0xFFFF0000L && VirtualQueryEx(H, (IntPtr)a, out m, Marshal.SizeOf(typeof(MBI))) != 0) {
      long sz = (long)m.Size; if (sz <= 0) break;
      if (m.State == 0x10000) { total += sz; if (sz > big) big = sz; }
      a = (long)m.Base + sz;
    }
    return new long[] { total, big };
  }
  public static int I32(long a) { var b = new byte[4]; IntPtr r; return ReadProcessMemory(H, (IntPtr)a, b, (IntPtr)4, out r) ? BitConverter.ToInt32(b, 0) : -1; }
}
'@
if (-not (Test-Path $Out)) { 'time,pid,privateMB,virtualMB,workingMB,freeMB,largestFreeMB,pvsOff,threads' | Set-Content $Out }
$pid0 = 0
while ($true) {
  $p = Get-Process Rally -ErrorAction SilentlyContinue | Select-Object -First 1
  if (-not $p) { if ($pid0) { "$(Get-Date -Format HH:mm:ss),$pid0,exited" | Add-Content $Out; [ML]::Close(); $pid0 = 0 }; Start-Sleep -Milliseconds 1000; continue }
  if ($p.Id -ne $pid0) { $pid0 = $p.Id; [ML]::Open($pid0) }
  $f = [ML]::Free(); $p.Refresh()
  '{0},{1},{2},{3},{4},{5},{6},{7},{8}' -f (Get-Date -Format HH:mm:ss), $pid0, [int]($p.PrivateMemorySize64 / 1MB), [int]($p.VirtualMemorySize64 / 1MB),
    [int]($p.WorkingSet64 / 1MB), [int]($f[0] / 1MB), [int]($f[1] / 1MB), [ML]::I32(0xA65794), $p.Threads.Count | Add-Content $Out
  Start-Sleep -Milliseconds $IntervalMs
}

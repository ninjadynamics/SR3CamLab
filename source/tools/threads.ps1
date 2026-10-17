# Groups Rally.exe's threads by start address (and module), and lists its top-level windows.
Add-Type @'
using System; using System.Text; using System.Runtime.InteropServices; using System.Collections.Generic;
public static class TH {
  [DllImport("kernel32.dll")] static extern IntPtr OpenThread(int a, bool i, uint id);
  [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr h);
  [DllImport("ntdll.dll")] static extern int NtQueryInformationThread(IntPtr h, int cls, out IntPtr info, int len, IntPtr ret);
  public static long Start(uint tid) {
    IntPtr h = OpenThread(0x0040, false, tid); if (h == IntPtr.Zero) return -1;
    IntPtr a; int st = NtQueryInformationThread(h, 9, out a, IntPtr.Size, IntPtr.Zero); CloseHandle(h);
    return st == 0 ? (long)a : -2;
  }
  public delegate bool P(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] static extern bool EnumWindows(P p, IntPtr l);
  [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern int GetClassName(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] static extern bool EnumChildWindows(IntPtr h, P p, IntPtr l);
  public static List<string> Windows(uint pid) {
    var o = new List<string>();
    EnumWindows((h, l) => { uint p; GetWindowThreadProcessId(h, out p); if (p != pid) return true;
      var t = new StringBuilder(256); var c = new StringBuilder(256); GetWindowText(h, t, 256); GetClassName(h, c, 256);
      o.Add(string.Format("window {0:X} class '{1}' title '{2}' visible {3}", (long)h, c, t, IsWindowVisible(h)));
      EnumChildWindows(h, (ch, l2) => { var t2 = new StringBuilder(256); GetWindowText(ch, t2, 256); if (t2.Length > 0) o.Add("    child: '" + t2 + "'"); return true; }, IntPtr.Zero);
      return true; }, IntPtr.Zero);
    return o;
  }
}
'@
$p = Get-Process Rally
"pid $($p.Id) threads $($p.Threads.Count) responding $($p.Responding)"
[TH]::Windows([uint32]$p.Id)
$mods = $p.Modules | ForEach-Object { [pscustomobject]@{ Name = $_.ModuleName; Base = [int64]$_.BaseAddress; End = [int64]$_.BaseAddress + $_.ModuleMemorySize } }
$p.Threads | ForEach-Object {
  $s = [TH]::Start([uint32]$_.Id)
  $m = $mods | Where-Object { $s -ge $_.Base -and $s -lt $_.End } | Select-Object -First 1
  [pscustomobject]@{ Start = ('{0:X8}' -f $s); Module = $(if ($m) { '{0}+{1:X}' -f $m.Name, ($s - $m.Base) } else { '?' }); State = "$($_.ThreadState)/$($_.WaitReason)" }
} | Group-Object Start, Module | Sort-Object Count -Descending | Select-Object -First 15 | ForEach-Object { '{0,4} x {1}   ({2})' -f $_.Count, $_.Name, (($_.Group | Group-Object State | ForEach-Object { "$($_.Name) $($_.Count)" }) -join ', ') }

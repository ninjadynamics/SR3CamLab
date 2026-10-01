# Run with the 32-bit PowerShell (-STA): plays one of the game's WMVs through a DirectShow graph, like
# the game does, and reports how many threads and how much address space each graph costs.
param([int]$Cores = 0, [int]$Graphs = 3, [Parameter(Mandatory)][string]$File)   # e.g. ...\Rally\frontend\PC\Videos\SUBARU.wmv
Add-Type @'
using System; using System.Runtime.InteropServices;
[ComImport, Guid("56a868a9-0ad4-11ce-b03a-0020af0ba770"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IGraphBuilder {
  void AddFilter(IntPtr f, [MarshalAs(UnmanagedType.LPWStr)] string n); void RemoveFilter(IntPtr f); void EnumFilters(out IntPtr e);
  void FindFilterByName([MarshalAs(UnmanagedType.LPWStr)] string n, out IntPtr f); void ConnectDirect(IntPtr a, IntPtr b, IntPtr mt);
  void Reconnect(IntPtr p); void Disconnect(IntPtr p); void SetDefaultSyncSource();
  void Connect(IntPtr a, IntPtr b); void Render(IntPtr p);
  [PreserveSig] int RenderFile([MarshalAs(UnmanagedType.LPWStr)] string file, [MarshalAs(UnmanagedType.LPWStr)] string pl);
}
[ComImport, Guid("56a868b1-0ad4-11ce-b03a-0020af0ba770"), InterfaceType(ComInterfaceType.InterfaceIsDual)]
public interface IMediaControl { [PreserveSig] int Run(); [PreserveSig] int Pause(); [PreserveSig] int Stop(); }
public static class DS {
  public static object Make() { return Activator.CreateInstance(Type.GetTypeFromCLSID(new Guid("e436ebb3-524f-11ce-9f53-0020af0ba770"))); }
  public static int Render(object g, string f) { return ((IGraphBuilder)g).RenderFile(f, null); }
  public static int Pause(object g) { return ((IMediaControl)g).Pause(); }
  public static int Stop(object g) { return ((IMediaControl)g).Stop(); }
}
'@
$p = [Diagnostics.Process]::GetCurrentProcess()
if ($Cores -gt 0) { $p.ProcessorAffinity = [IntPtr]((1 -shl $Cores) - 1) }
function Stat { $p.Refresh(); [pscustomobject]@{ Threads = $p.Threads.Count; VirtualMB = [int]($p.VirtualMemorySize64 / 1MB); PrivateMB = [int]($p.PrivateMemorySize64 / 1MB) } }
$before = Stat
$keep = @()
for ($i = 0; $i -lt $Graphs; $i++) {
  $g = [DS]::Make()
  $hr = [DS]::Render($g, $File); if ($hr -lt 0) { 'RenderFile failed: 0x{0:X8}' -f $hr; break }
  [void][DS]::Pause($g)                                                     # the decoder spins up when the graph runs
  Start-Sleep -Milliseconds 800
  $keep += $g
}
$after = Stat
'cores allowed: {0} of {1} logical' -f $(if ($Cores) { $Cores } else { 'all' }), [Environment]::ProcessorCount
'per graph: {0:0.#} threads, {1:0} MB virtual, {2:0} MB private' -f (($after.Threads - $before.Threads) / $keep.Count), (($after.VirtualMB - $before.VirtualMB) / $keep.Count), (($after.PrivateMB - $before.PrivateMB) / $keep.Count)
foreach ($g in $keep) { [void][DS]::Stop($g) }


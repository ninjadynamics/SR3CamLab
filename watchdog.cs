// SR3CamLab's crash and freeze watchdog. patches.ps1 (Start-Watchdog) loads it while the game runs; tools\watchdog_test.ps1
// runs it against small stand-in programs. It attaches to the game as a debugger, as the crash logger that used to be
// started by hand did, and only watches: every exception goes back to the game as it would without a debugger
// (DBG_EXCEPTION_NOT_HANDLED; only the break-in of the attach itself is taken), and when this process ends Windows
// detaches it and the game runs on (DebugSetProcessKillOnExit(FALSE)). One log per session in the folder it is given:
//   crash    an exception the game does not handle (second chance): registers, the code bytes, the stack, the calls on the
//            stack, memory at the registers, the other threads, the game's last debug output lines, and a minidump
//   handled  first-chance exceptions the game deals with itself: a line each (the first few per address; the access
//            violations with their registers)
//   freeze   the game's window does not answer for FreezeSeconds (asked once a second with SendMessageTimeout): every
//            thread's registers and stack, three samples a second apart, a minidump, and a line when it answers again
//   message  a message box of the game's ("Out of memory for VB"): its text and the same thread samples (the box keeps
//            the window answering, so it would not count as a freeze)
// Short news for the launcher's window and play.log wait in a queue (NextMessage). C# 5: Windows PowerShell's Add-Type.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.IO;
using System.Runtime.ExceptionServices;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

public static class Sr3Watchdog {
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool DebugActiveProcess(int pid);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool DebugActiveProcessStop(int pid);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool DebugSetProcessKillOnExit(bool kill);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool WaitForDebugEvent(IntPtr ev, uint ms);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool ContinueDebugEvent(int pid, int tid, uint status);
    [DllImport("kernel32.dll", SetLastError = true)] static extern IntPtr OpenProcess(int access, bool inherit, int pid);
    [DllImport("kernel32.dll", SetLastError = true)] static extern IntPtr OpenThread(int access, bool inherit, int tid);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll", SetLastError = true)] static extern uint WaitForSingleObject(IntPtr h, uint ms);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool GetExitCodeProcess(IntPtr h, out uint code);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool ReadProcessMemory(IntPtr h, IntPtr a, byte[] b, IntPtr n, out IntPtr r);
    [DllImport("kernel32.dll", SetLastError = true)] static extern IntPtr VirtualQueryEx(IntPtr h, IntPtr a, out MBI m, IntPtr n);
    [DllImport("kernel32.dll", SetLastError = true)] static extern int SuspendThread(IntPtr t);
    [DllImport("kernel32.dll", SetLastError = true)] static extern int ResumeThread(IntPtr t);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool Wow64GetThreadContext(IntPtr t, IntPtr c);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool GetThreadContext(IntPtr t, IntPtr c);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool IsWow64Process(IntPtr h, out bool w);
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)] static extern bool QueryFullProcessImageName(IntPtr h, int flags, StringBuilder s, ref int n);
    [DllImport("kernel32.dll", SetLastError = true)] static extern IntPtr CreateToolhelp32Snapshot(uint flags, int pid);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool Thread32First(IntPtr s, ref TE t);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool Thread32Next(IntPtr s, ref TE t);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool K32EnumProcessModulesEx(IntPtr h, [Out] IntPtr[] mods, int cb, out int needed, int filter);
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)] static extern int K32GetModuleBaseNameW(IntPtr h, IntPtr mod, StringBuilder name, int n);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool K32GetModuleInformation(IntPtr h, IntPtr mod, out MODINFO mi, int cb);
    [DllImport("ntdll.dll")] static extern int NtQueryInformationThread(IntPtr t, int cls, out IntPtr info, int len, IntPtr ret);
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc cb, IntPtr l);
    [DllImport("user32.dll")] static extern int GetWindowThreadProcessId(IntPtr w, out int pid);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr w);
    [DllImport("user32.dll")] static extern bool IsWindow(IntPtr w);
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr w, out RECT r);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetWindowText(IntPtr w, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetClassName(IntPtr w, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern int GetDlgItemText(IntPtr w, int id, StringBuilder s, int n);
    [DllImport("user32.dll", SetLastError = true)] static extern IntPtr SendMessageTimeout(IntPtr w, uint msg, IntPtr wp, IntPtr lp, uint flags, uint ms, out IntPtr result);
    [DllImport("dbghelp.dll", SetLastError = true)] static extern bool MiniDumpWriteDump(IntPtr h, int pid, IntPtr file, int type, IntPtr exc, IntPtr user, IntPtr cb);
    delegate bool EnumProc(IntPtr w, IntPtr l);
    [StructLayout(LayoutKind.Sequential)] struct MBI { public IntPtr Base, AllocBase; public uint AllocProtect; public IntPtr Size; public uint State, Protect, Type; }
    [StructLayout(LayoutKind.Sequential)] struct TE { public int Size, Usage, Tid, OwnerPid, BasePri, DeltaPri, Flags; }
    [StructLayout(LayoutKind.Sequential)] struct MODINFO { public IntPtr Base; public int Size; public IntPtr Entry; }
    [StructLayout(LayoutKind.Sequential)] struct RECT { public int L, T, R, B; }

    const uint DBG_CONTINUE = 0x00010002, DBG_EXCEPTION_NOT_HANDLED = 0x80010001;
    // minidump: thread info, unloaded modules, the memory the stacks point at, and every module's global data (the game keeps
    // its state in globals: the state machine, the race flags; Rally.exe's .data is about 4.4 MB)
    const int DumpType = 0x1000 | 0x20 | 0x40 | 0x1;
    static readonly int P = IntPtr.Size;                                   // 8 in the 64-bit PowerShell PLAY.bat runs
    const int MaxLines = 20000;                                            // first-chance and debug output lines per session (crash and freeze records always)

    // ---- the session ----
    static int pid, freezeSeconds, lines, firstChance, outputLines; static long windowPtr;
    static IntPtr hProc = IntPtr.Zero; static string folder, logPath, logName;
    static string imagePath = "?"; static ulong imageBase;            // the game's file and where it is loaded (from the attach)
    static volatile bool stop, finished, attached, busy, target32, sawCrash;   // sawCrash: after it Windows' error reporting holds the dying game, which is not a freeze
    static Thread debugThread, freezeThread;
    static StreamWriter log; static readonly object logLock = new object(), dumpLock = new object();
    static readonly ConcurrentQueue<string> news = new ConcurrentQueue<string>();
    static readonly Queue<string> lastOutput = new Queue<string>();       // the game's last OutputDebugString lines
    static Dictionary<string, int> seen = new Dictionary<string, int>();

    // values of the game's written in every record, "name=0xADDRESS" (a dword) or "name=0xADDRESS:1" (a byte), comma-separated
    public static string Values = "";
    public static string LogPath { get { return logPath; } }
    public static bool Attached { get { return attached; } }
    public static bool Finished { get { return finished; } }
    public static string NextMessage() { string m; return news.TryDequeue(out m) ? m : null; }

    // Starts watching the process. The launcher calls this after its own wait (TeknoParrot looks at the game during its
    // first seconds). windowHandleAt: an address in the game that holds its window handle (0 = find the window by process).
    // False when a session is still running.
    public static bool Start(int processId, string logFolder, int freezeAfterSeconds, long windowHandleAt) {
        if (debugThread != null && !finished) return false;
        pid = processId; folder = logFolder; freezeSeconds = Math.Max(2, freezeAfterSeconds); windowPtr = windowHandleAt;
        stop = false; finished = false; attached = false; busy = false; sawCrash = false; lines = 0; firstChance = 0; outputLines = 0;
        seen = new Dictionary<string, int>(); lock (lastOutput) lastOutput.Clear(); string dummy; while (news.TryDequeue(out dummy)) { }
        debugThread = null; freezeThread = null;
        Directory.CreateDirectory(folder);
        logName = "watchdog_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".log"; logPath = Path.Combine(folder, logName);
        var fs = new FileStream(logPath, FileMode.Append, FileAccess.Write, FileShare.ReadWrite | FileShare.Delete);
        log = new StreamWriter(fs, new UTF8Encoding(false)); log.AutoFlush = true;
        hProc = OpenProcess(0x0400 | 0x0010 | 0x00100000, false, pid);   // query, read, synchronize
        if (hProc == IntPtr.Zero) {
            Line("cannot open process " + pid + " (error " + Marshal.GetLastWin32Error() + ")");
            News("could not watch the game (it could not be opened): crashes and freezes are not recorded this time.");
            finished = true; Close(); return true;
        }
        imagePath = ImagePath(); imageBase = 0;
        bool w; target32 = P == 4 || (IsWow64Process(hProc, out w) && w);
        Line("SR3CamLab watchdog, " + DateTime.Now.ToString("yyyy-MM-dd") + ": process " + pid + " " + ImagePath() + (target32 ? " (32-bit)" : " (64-bit: registers are not read)") +
             ", a freeze is " + freezeSeconds + " s without an answer from its window");
        debugThread = new Thread(DebugLoop); debugThread.IsBackground = true; debugThread.Name = "watchdog debugger";
        freezeThread = new Thread(FreezeLoop); freezeThread.IsBackground = true; freezeThread.Name = "watchdog freeze";
        debugThread.Start(); freezeThread.Start();
        return true;
    }
    // Detaches and stops; the game runs on. Waits up to waitMs for the watchdog's threads.
    public static void Stop(int waitMs) {
        stop = true;
        if (debugThread != null) debugThread.Join(waitMs);
        if (freezeThread != null) freezeThread.Join(waitMs);
    }
    // Waits up to waitMs for the session to end by itself (it does when the game exits). True when it has.
    public static bool WaitFinished(int waitMs) { return debugThread == null || debugThread.Join(waitMs); }

    static void News(string m) { news.Enqueue(m); }
    static void Line(string m) {
        lock (logLock) { if (log != null) { try { log.WriteLine(DateTime.Now.ToString("HH:mm:ss.fff") + " " + m); } catch { } } }
    }
    static bool Quota() { return Interlocked.Increment(ref lines) <= MaxLines; }
    static void Close() {
        lock (logLock) { if (log != null) { try { log.Dispose(); } catch { } log = null; } }
        if (hProc != IntPtr.Zero) { CloseHandle(hProc); hProc = IntPtr.Zero; }
    }
    static string Rel(string file) { return Path.GetFileName(folder.TrimEnd('\\', '/')) + "\\" + file; }

    // ---- crashes of a thread hidden from debuggers ----
    // The game's main thread (the window's) is hidden from debuggers (ThreadHideFromDebugger; found 2026-10-14, 1 of 231
    // threads): its exceptions never reach this debugger and go straight to Windows' error reporting, which writes
    // %LOCALAPPDATA%\CrashDumps\Rally.exe.<pid>.dmp when LocalDumps is on (HKLM\SOFTWARE\Microsoft\Windows\Windows Error
    // Reporting\LocalDumps). So when the game ends with an error code and no exception was seen, the record is taken from
    // that dump: the exception, the registers of the thread and the game-code values on its stack.
    [DllImport("ntdll.dll")] static extern int NtQueryInformationThread(IntPtr h, int cls, out byte info, int len, out int ret);
    static void HiddenThreads() {
        var hidden = new List<int>();
        foreach (int t in Threads()) {
            IntPtr ht = OpenThread(0x0040, false, t); if (ht == IntPtr.Zero) continue;
            byte b; int r; if (NtQueryInformationThread(ht, 0x11, out b, 1, out r) == 0 && b != 0) hidden.Add(t);
            CloseHandle(ht);
        }
        if (hidden.Count > 0)
            Line("hidden from debuggers: thread" + (hidden.Count > 1 ? "s " : " ") + string.Join(", ", hidden.ConvertAll(x => x.ToString()).ToArray()) +
                 " (a crash there is not seen here; it is read from Windows' crash dump when the game ends)");
    }
    static string FromWindowsDump(uint exitCode) {
        string dir = Path.Combine(Environment.GetEnvironmentVariable("LOCALAPPDATA") ?? "", "CrashDumps");
        string want = Path.GetFileName(imagePath) + "." + pid + ".dmp", path = Path.Combine(dir, want);
        for (int i = 0; i < 50 && !File.Exists(path); i++) Thread.Sleep(100);
        if (!File.Exists(path)) {
            Line("no Windows crash dump " + path + " (Windows' LocalDumps may be off on this PC)"); return null;
        }
        byte[] d = null;
        for (int i = 0; i < 30 && d == null; i++) { try { d = File.ReadAllBytes(path); } catch (IOException) { Thread.Sleep(200); } }   // Windows may still be writing it
        if (d == null || d.Length < 32 || BitConverter.ToUInt32(d, 0) != 0x504D444D) { Line("Windows crash dump " + path + " could not be read"); return null; }
        try {
            int ns = BitConverter.ToInt32(d, 8), dirRva = BitConverter.ToInt32(d, 12); int exRva = -1;
            var mem = new List<long[]>();                                    // {start, rva, size}
            ulong modBase = 0, modSize = 0;
            for (int i = 0; i < ns; i++) {
                int t = BitConverter.ToInt32(d, dirRva + 12 * i), rva = BitConverter.ToInt32(d, dirRva + 12 * i + 8);
                if (t == 6) exRva = rva;
                else if (t == 4 && BitConverter.ToInt32(d, rva) > 0) { modBase = BitConverter.ToUInt64(d, rva + 4); modSize = BitConverter.ToUInt32(d, rva + 4 + 8); }   // the first module: the exe
                else if (t == 5) { int n = BitConverter.ToInt32(d, rva); for (int k = 0; k < n; k++) mem.Add(new long[] { (long)BitConverter.ToUInt64(d, rva + 4 + 16 * k), BitConverter.ToUInt32(d, rva + 4 + 16 * k + 12), BitConverter.ToUInt32(d, rva + 4 + 16 * k + 8) }); }
                else if (t == 9) { long n = (long)BitConverter.ToUInt64(d, rva), off = (long)BitConverter.ToUInt64(d, rva + 8); for (int k = 0; k < n; k++) { long s = (long)BitConverter.ToUInt64(d, rva + 16 + 16 * k), sz = (long)BitConverter.ToUInt64(d, rva + 24 + 16 * k); mem.Add(new long[] { s, off, sz }); off += sz; } }
            }
            if (exRva < 0) { Line("Windows crash dump " + want + " holds no exception"); return want; }
            int tid = BitConverter.ToInt32(d, exRva); uint ec = BitConverter.ToUInt32(d, exRva + 8); ulong addr = BitConverter.ToUInt64(d, exRva + 8 + 16);
            int np = BitConverter.ToInt32(d, exRva + 8 + 24); var info = new ulong[Math.Min(Math.Max(np, 0), 4)];
            for (int i = 0; i < info.Length; i++) info[i] = BitConverter.ToUInt64(d, exRva + 8 + 32 + 8 * i);
            int csize = BitConverter.ToInt32(d, exRva + 8 + 152), crva = BitConverter.ToInt32(d, exRva + 8 + 156);
            string what = string.Format("{0} 0x{1:X8} at {2}{3}", ExceptionName(ec), ec, GameName(addr), AvText(ec, info));
            Line("==== CRASH (from Windows' crash dump " + want + "): " + what + ", thread " + tid);
            if (csize >= 0xCC) {
                string[] rn = { "edi", "esi", "ebx", "edx", "ecx", "eax", "ebp", "eip" }; var sb = new StringBuilder("  ");
                for (int i = 0; i < 8; i++) sb.AppendFormat("{0} {1:X8}  ", rn[i], BitConverter.ToUInt32(d, crva + 0x9C + 4 * i));
                uint esp = BitConverter.ToUInt32(d, crva + 0xC4); sb.AppendFormat("esp {0:X8}", esp); Line(sb.ToString());
                foreach (long[] m in mem) {
                    if (esp < m[0] || esp >= m[0] + m[2]) continue;
                    int at = (int)(m[1] + (esp - m[0])), n = (int)Math.Min(0x800, m[0] + m[2] - esp) / 4; var st = new StringBuilder(); var calls = new StringBuilder();
                    ulong b0 = modBase != 0 ? modBase : imageBase != 0 ? imageBase : 0x400000, b1 = b0 + (modSize != 0 ? modSize : 0x1000000);
                    for (int k = 0; k < n; k++) { uint w = BitConverter.ToUInt32(d, at + 4 * k); if (k < 32) st.AppendFormat("{0:X8} ", w); if (w > b0 && w < b1) calls.AppendFormat("{0:X8} ", w); }
                    Line("  stack: " + st.ToString().Trim()); Line("  values on the stack inside the exe (its return addresses among them): " + calls.ToString().Trim());
                    break;
                }
            }
            Line("  the whole dump: " + path); Line("==== end of the crash record");
            News("the game crashed: " + what + " (seen in Windows' crash dump; details: " + Rel(logName) + ").");
            return want;
        } catch (Exception x) { Line("Windows crash dump " + want + ": " + x.Message); return want; }
    }
    static string GameName(ulong a) {                                   // the process has ended: only its own exe can still be named (from the attach)
        ulong b = imageBase != 0 ? imageBase : 0x400000;
        return a >= b && a < b + 0x1000000 ? string.Format("{0:X8} ({1}+0x{2:X})", a, Path.GetFileName(imagePath), a - b) : a.ToString("X8");
    }

    // ---- the debugger ----
    static void DebugLoop() {
        IntPtr ev = Marshal.AllocHGlobal(256);
        int off = P == 8 ? 16 : 12;                                         // the union in DEBUG_EVENT
        try {
            if (!DebugActiveProcess(pid)) {
                int e = Marshal.GetLastWin32Error();
                Line("attach failed, error " + e + (e == 5 ? " (access denied)" : e == 87 ? " (another debugger has the game?)" : ""));
                News("could not attach to the game (error " + e + (e == 87 ? ": another debugger has it" : "") + "): crashes are not recorded this time, freezes still are.");
                WatchOnly();
                return;
            }
            if (!DebugSetProcessKillOnExit(false)) {                       // never risk taking the game down with this process
                Line("DebugSetProcessKillOnExit failed (error " + Marshal.GetLastWin32Error() + "): detaching again");
                while (WaitForDebugEvent(ev, 100)) {                        // hand back what Windows queued for the attach
                    int c = Marshal.ReadInt32(ev, 0); uint x = c == 1 ? (uint)Marshal.ReadInt32(ev, off) : 0;
                    if (c == 3 || c == 6) { IntPtr hf = Marshal.ReadIntPtr(ev, off); if (hf != IntPtr.Zero) CloseHandle(hf); }
                    ContinueDebugEvent(Marshal.ReadInt32(ev, 4), Marshal.ReadInt32(ev, 8), c == 1 && x != 0x80000003 && x != 0x4000001F ? DBG_EXCEPTION_NOT_HANDLED : DBG_CONTINUE);
                }
                DebugActiveProcessStop(pid);
                News("could not attach safely: crashes are not recorded this time, freezes still are.");
                WatchOnly();
                return;
            }
            attached = true;
            Line("attached");
            try { HiddenThreads(); } catch (Exception x) { Line("hidden threads: " + x.Message); }
            News("watching the game for crashes and freezes (" + Rel(logName) + ").");
            // a 64-bit debugger attaching to a 32-bit process gets two break-ins of its own making: the native one
            // (0x80000003, in the thread Windows starts for it) and the 32-bit one (0x4000001F, WOW64's, on a thread of the
            // game's, which would otherwise go through the game's own exception handlers): both are taken, once each
            DateTime attachedAt = DateTime.Now; bool sawBreak = false, sawWowBreak = false;
            while (true) {
                if (!WaitForDebugEvent(ev, 200)) {
                    if (stop) { DebugActiveProcessStop(pid); attached = false; Line("detached (the game runs on)"); Summary(); return; }
                    // The end of the process is not always reported to the debugger: when a thread hidden from debuggers
                    // crashes and Windows' error reporting handles it, no EXIT_PROCESS event came here (stand-in test,
                    // 2026-10-14), so the process handle is asked too.
                    if (WaitForSingleObject(hProc, 0) == 0) {
                        uint xc; if (!GetExitCodeProcess(hProc, out xc)) xc = 0;
                        Line(string.Format("the process ended, exit code 0x{0:X8} (no end event from Windows: seen on the process handle)", xc));
                        if ((!sawCrash || !recordDone) && xc >= 0xC0000000 && FromWindowsDump(xc) == null) News(string.Format("the game ended with error code 0x{0:X8} ({1}).", xc, Rel(logName)));
                        Summary(); attached = false; DebugActiveProcessStop(pid);
                        return;
                    }
                    continue;
                }
                int code = Marshal.ReadInt32(ev, 0), epid = Marshal.ReadInt32(ev, 4), tid = Marshal.ReadInt32(ev, 8);
                uint status = DBG_CONTINUE;
                try {
                    if (code == 1) {                                        // EXCEPTION_DEBUG_EVENT
                        uint ec = (uint)Marshal.ReadInt32(ev, off);
                        ulong addr = P == 8 ? (ulong)Marshal.ReadInt64(ev, off + 16) : (uint)Marshal.ReadInt32(ev, off + 12);
                        int np = Marshal.ReadInt32(ev, off + (P == 8 ? 24 : 16));
                        ulong[] info = new ulong[Math.Min(Math.Max(np, 0), 4)];
                        for (int i = 0; i < info.Length; i++) info[i] = P == 8 ? (ulong)Marshal.ReadInt64(ev, off + 32 + 8 * i) : (uint)Marshal.ReadInt32(ev, off + 20 + 4 * i);
                        bool first = Marshal.ReadInt32(ev, off + (P == 8 ? 152 : 80)) != 0;
                        bool early = first && (DateTime.Now - attachedAt).TotalSeconds < 30;
                        if (early && ec == 0x80000003 && !sawBreak) { sawBreak = true; Line("attach break-in taken (thread " + tid + ")"); }
                        else if (early && ec == 0x4000001F && !sawWowBreak) { sawWowBreak = true; Line("32-bit attach break-in taken (thread " + tid + ")"); }
                        else {
                            status = DBG_EXCEPTION_NOT_HANDLED;             // everything else is the game's, as without a debugger
                            if (first) FirstChance(ec, addr, info, tid); else Crash(ec, addr, info, tid);
                        }
                    } else if (code == 3 || code == 6) {                    // process / DLL load: close the file handle we are given
                        if (code == 3) imageBase = (ulong)Marshal.ReadIntPtr(ev, off + 3 * P).ToInt64();   // CREATE_PROCESS_DEBUG_INFO.lpBaseOfImage
                        IntPtr hf = Marshal.ReadIntPtr(ev, off);
                        if (hf != IntPtr.Zero) CloseHandle(hf);
                    } else if (code == 8) {                                 // OutputDebugString
                        Output(Marshal.ReadIntPtr(ev, off), Marshal.ReadInt16(ev, off + P) != 0, Marshal.ReadInt16(ev, off + P + 2) & 0xFFFF);
                    } else if (code == 5) {                                 // the game has ended
                        uint xc = (uint)Marshal.ReadInt32(ev, off);
                        Line(string.Format("the process ended, exit code 0x{0:X8}", xc));
                        if ((!sawCrash || !recordDone) && xc >= 0xC0000000 && FromWindowsDump(xc) == null) News(string.Format("the game ended with error code 0x{0:X8} ({1}).", xc, Rel(logName)));
                        Summary();
                        attached = false;
                        ContinueDebugEvent(epid, tid, DBG_CONTINUE);
                        return;
                    }
                } catch (Exception x) { Line("watchdog error: " + x.Message); }
                ContinueDebugEvent(epid, tid, status);
            }
        } catch (Exception x) { Line("watchdog stopped: " + x.Message); }
        finally {
            Marshal.FreeHGlobal(ev); stop = true;
            if (freezeThread != null) freezeThread.Join(30000);              // it may be writing a freeze record
            finished = true; Close();
        }
    }
    // not attached: the freeze watch goes on until the game ends or Stop()
    static void WatchOnly() {
        while (!stop && WaitForSingleObject(hProc, 500) == 0x102) { }
        if (!stop) Line("the process ended");
    }
    static void Summary() {
        var sb = new StringBuilder();
        foreach (var kv in seen) if (sb.Length < 600) sb.Append(" " + kv.Key + " x" + kv.Value);
        Line("first-chance exceptions this session: " + firstChance + (sb.Length > 0 ? " (" + sb.ToString().Trim() + ")" : "") + "; debug output lines: " + outputLines);
    }

    static string ExceptionName(uint c) {
        switch (c) {
            case 0xC0000005: return "access violation"; case 0xC0000094: return "integer divide by zero"; case 0xC00000FD: return "stack overflow";
            case 0xC000001D: return "illegal instruction"; case 0xC0000096: return "privileged instruction"; case 0xC0000409: return "stack buffer overrun";
            case 0xC0000374: return "heap corruption"; case 0xE06D7363: return "C++ exception"; case 0x80000003: case 0x4000001F: return "breakpoint";
            case 0xC000008E: return "float divide by zero"; case 0xC0000090: return "float invalid"; case 0xC0000017: return "out of memory";
            default: return "exception";
        }
    }
    static string AvText(uint ec, ulong[] info) {
        if (ec != 0xC0000005 || info.Length < 2) return "";
        return string.Format(" ({0} 0x{1:X8})", info[0] == 0 ? "reading" : info[0] == 1 ? "writing" : info[0] == 8 ? "executing" : "touching", info[1]);
    }
    static void FirstChance(uint ec, ulong addr, ulong[] info, int tid) {
        if (ec == 0x406D1388) return;                                       // a thread being given a name
        firstChance++;
        string key = string.Format("{0:X8}@{1:X8}", ec, addr); int n; seen.TryGetValue(key, out n); seen[key] = ++n;
        if (n > 3 || !Quota()) return;
        Line(string.Format("first chance (the game may handle it): {0} 0x{1:X8} at {2}{3}, thread {4}", ExceptionName(ec), ec, Name(addr), AvText(ec, info), tid));
        if (ec == 0xC0000005 && n <= 2) DescribeThread(tid, false, null, 2, "  ", "");
    }
    // The game stands still at its second chance while the record is written; at most 30 s, then it is let go (it ends,
    // and Windows' crash dump is read at the end if the record is not complete).
    static void Crash(uint ec, ulong addr, ulong[] info, int tid) {
        busy = true; sawCrash = true;
        var t = new Thread(() => { try { CrashRecord(ec, addr, info, tid); recordDone = true; } catch (Exception x) { Line("  crash record stopped: " + x.Message); } });
        t.IsBackground = true; recordDone = false; t.Start();
        if (!t.Join(30000)) Line("  (the crash record took more than 30 s; the game is let go)");
        busy = false;
    }
    static volatile bool recordDone = true;
    static void CrashRecord(uint ec, ulong addr, ulong[] info, int tid) {
        try {
            sawCrash = true;
            string what = string.Format("{0} 0x{1:X8} at {2}{3}", ExceptionName(ec), ec, Name(addr), AvText(ec, info));
            Line("==== CRASH: " + what + ", thread " + tid + " (second chance: the game does not handle it)");
            GameValues("  ");
            DescribeThread(tid, false, null, 2, "  ", "");
            Line("  other threads:");
            foreach (int t in Threads()) if (t != tid) DescribeThread(t, false, null, 0, "    ", "");
            Recent();
            string dump = Dump("crash");
            Line("==== end of the crash record");
            News("the game crashed: " + what + ". Details: " + Rel(logName) + (dump != null ? ", minidump " + Rel(dump) : "") + ".");
        } finally { }
    }
    static void Output(IntPtr p, bool uni, int n) {
        if (p == IntPtr.Zero || n <= 0) return;
        byte[] b = ReadUpTo((ulong)p.ToInt64(), Math.Min(uni ? n * 2 : n, 1200));
        if (b == null) return;
        string t = uni ? Encoding.Unicode.GetString(b, 0, b.Length & ~1) : Encoding.GetEncoding(1252).GetString(b);
        int z = t.IndexOf('\0'); if (z >= 0) t = t.Substring(0, z);
        t = t.TrimEnd('\r', '\n').Replace("\r", " ").Replace("\n", " | ");
        if (t.Length == 0) return;
        outputLines++;
        lock (lastOutput) { lastOutput.Enqueue(DateTime.Now.ToString("HH:mm:ss.fff") + " " + t); while (lastOutput.Count > 40) lastOutput.Dequeue(); }
        if (Quota()) Line("game says: " + t);
    }
    static void GameValues(string ind) {
        if (string.IsNullOrEmpty(Values)) return;
        var sb = new StringBuilder();
        foreach (string item in Values.Split(',')) {
            string[] kv = item.Trim().Split('='); if (kv.Length != 2) continue;
            string[] at = kv[1].Trim().Split(':'); long a; int n = at.Length > 1 && at[1] == "1" ? 1 : 4;
            if (!long.TryParse(at[0].Trim().Replace("0x", "").Replace("0X", ""), System.Globalization.NumberStyles.HexNumber, null, out a)) continue;
            byte[] b = Read((ulong)a, n);
            sb.Append(" " + kv[0].Trim() + "=" + (b == null ? "?" : n == 1 ? "0x" + b[0].ToString("X") : "0x" + BitConverter.ToUInt32(b, 0).ToString("X")));
        }
        Line(ind + "game values:" + sb);
    }
    static void Recent() {
        string[] l; lock (lastOutput) l = lastOutput.ToArray();
        if (l.Length == 0) return;
        Line("  the game's last debug output lines:");
        foreach (string s in l) Line("    " + s);
    }

    // ---- freezes and message boxes ----
    static void FreezeLoop() {
        // missSince: when the first question that got no answer was asked (the window may have stopped a little before; a
        // freeze is called only after FreezeSeconds of questions without an answer, never less)
        DateTime missSince = DateTime.MinValue, frozenAt = DateTime.MinValue; bool answered = false, frozen = false;
        var boxes = new HashSet<long>(); IntPtr watched = IntPtr.Zero;
        try {
            while (!stop) {
                if (WaitForSingleObject(hProc, 1000) != 0x102) return;     // the game has ended (or the handle is gone); else the second's wait
                if (stop) return;
                if (busy || sawCrash) { missSince = DateTime.MinValue; continue; }   // the debugger holds the game (writing a crash record), or it has crashed
                int wtid; IntPtr box; IntPtr w = GameWindow(out wtid, out box);
                if (box != IntPtr.Zero && boxes.Add(box.ToInt64())) RecordBox(box);
                if (w == IntPtr.Zero) { missSince = DateTime.MinValue; continue; }
                if (w != watched) {
                    watched = w; var cls = new StringBuilder(64); GetClassName(w, cls, 64); var tt = new StringBuilder(128); GetWindowText(w, tt, 128);
                    Line(string.Format("watching window 0x{0:X} \"{1}\" (class {2}, thread {3}{4})", w.ToInt64(), tt, cls, wtid, IsWindowVisible(w) ? "" : ", hidden"));
                }
                IntPtr r; DateTime asked = DateTime.Now;
                bool ok = SendMessageTimeout(w, 0, IntPtr.Zero, IntPtr.Zero, 0x0002 | 0x0001, 2000, out r) != IntPtr.Zero;   // WM_NULL; abort if hung, block
                if (busy) { missSince = DateTime.MinValue; continue; }
                if (ok) {
                    if (frozen) {
                        double s = (DateTime.Now - frozenAt).TotalSeconds;
                        Line(string.Format("the game's window answers again (about {0:0} s without an answer)", s));      // (counted to the first answer seen)
                        News(string.Format("the game is responding again (it hung for about {0:0} s).", s));
                    }
                    frozen = false; answered = true; missSince = DateTime.MinValue;
                } else if (answered && !frozen) {
                    if (missSince == DateTime.MinValue) missSince = asked;
                    if ((DateTime.Now - missSince).TotalSeconds < freezeSeconds) continue;
                    frozen = true; frozenAt = missSince;
                    string why = string.Format("the game's window has not answered for {0:0} s", (DateTime.Now - missSince).TotalSeconds);
                    string dump = Samples("FREEZE", why, w, wtid, "freeze");
                    News("the game stopped responding at " + frozenAt.ToString("HH:mm:ss") + " (no answer from its window for " + freezeSeconds + " s). Its threads: " +
                         Rel(logName) + (dump != null ? ", minidump " + Rel(dump) : "") + ".");
                }
            }
        } catch (Exception x) { Line("freeze watch stopped: " + x.Message); }
    }
    static void RecordBox(IntPtr box) {
        var title = new StringBuilder(256); GetWindowText(box, title, 256);
        var text = new StringBuilder(1024); GetDlgItemText(box, 0xFFFF, text, 1024);   // a MessageBox's text is its static control 0xFFFF
        string t = text.ToString().Replace("\r", " ").Replace("\n", " | ").Trim();
        int btid, p; btid = GetWindowThreadProcessId(box, out p);
        string dump = Samples("MESSAGE BOX", "the game shows a message box: \"" + title + "\": " + t, box, btid, "msgbox");
        News("the game shows a message box \"" + title + "\": " + (t.Length > 120 ? t.Substring(0, 120) + "..." : t) + " (" + Rel(logName) + (dump != null ? ", minidump " + Rel(dump) : "") + ").");
    }
    // every thread's registers and stack, three samples a second apart (the thread of the window first), then a minidump
    static string Samples(string kind, string why, IntPtr w, int wtid, string dumpKind) {
        var title = new StringBuilder(128); GetWindowText(w, title, 128);
        Line(string.Format("==== {0}: {1} (window 0x{2:X} \"{3}\", its thread {4})", kind, why, w.ToInt64(), title, wtid));
        var before = new Dictionary<int, string>();
        for (int s = 1; s <= 3 && !stop; s++) {
            Line("  -- sample " + s + " of 3");
            GameValues("    ");
            var tids = Threads(); tids.Remove(wtid); tids.Insert(0, wtid);
            foreach (int t in tids) DescribeThread(t, true, before, t == wtid ? 2 : s == 1 ? 1 : 0, "    ", t == wtid ? "[window] " : "");
            if (s < 3) Thread.Sleep(1000);
        }
        Recent();
        string dump = Dump(dumpKind);
        Line("==== end of the " + kind.ToLower() + " record");
        return dump;
    }
    // the game's window: the handle the game keeps at windowPtr when that is one of its windows, else its largest visible
    // one (a hidden one if it has none); box: a message box of the game's, if one is up
    static IntPtr GameWindow(out int wtid, out IntPtr box) {
        wtid = 0; box = IntPtr.Zero; int wp; IntPtr own = IntPtr.Zero;
        if (windowPtr != 0) {
            byte[] b = Read((ulong)windowPtr, 4);
            if (b != null) {
                var h = new IntPtr(BitConverter.ToInt32(b, 0));
                if (h != IntPtr.Zero && IsWindow(h)) { int t = GetWindowThreadProcessId(h, out wp); if (wp == pid) { own = h; wtid = t; } }
            }
        }
        IntPtr best = IntPtr.Zero, hidden = IntPtr.Zero, dlg = IntPtr.Zero; long area = -1;
        EnumProc cb = delegate(IntPtr h, IntPtr l) {
            int p2; GetWindowThreadProcessId(h, out p2);
            if (p2 != pid) return true;
            var cls = new StringBuilder(64); GetClassName(h, cls, 64); string c = cls.ToString();
            if (c == "IME" || c == "MSCTFIME UI" || c == "ConsoleWindowClass") return true;   // the console's window answers for conhost, not for the game
            // Direct3D's proxy window and DirectShow's video windows have threads of their own: they keep answering while the
            // game's main loop hangs (in game 2026-10-14 the fallback took "D3DProxyWindow", listed before the game's window)
            if (c == "D3DProxyWindow" || c == "FilterGraphWindow") return true;
            if (c == "RacingClass" && IsWindowVisible(h)) { area = long.MaxValue; best = h; return true; }      // SEGA Rally 3's own window
            bool vis = IsWindowVisible(h);
            if (c == "#32770") { if (vis && dlg == IntPtr.Zero) dlg = h; return true; }
            if (!vis) { if (hidden == IntPtr.Zero) hidden = h; return true; }
            RECT r; GetWindowRect(h, out r); long a = (long)(r.R - r.L) * (r.B - r.T);
            if (a > area) { area = a; best = h; }
            return true;
        };
        EnumWindows(cb, IntPtr.Zero); GC.KeepAlive(cb);
        box = dlg;
        if (own != IntPtr.Zero) return own;
        if (best == IntPtr.Zero) best = hidden;
        if (best != IntPtr.Zero) wtid = GetWindowThreadProcessId(best, out wp);
        return best;
    }

    // ---- threads, registers, stacks ----
    static List<int> Threads() {
        var l = new List<int>();
        IntPtr s = CreateToolhelp32Snapshot(0x4, 0);                       // TH32CS_SNAPTHREAD
        if (s == new IntPtr(-1)) return l;
        try {
            var te = new TE(); te.Size = Marshal.SizeOf(typeof(TE));
            if (Thread32First(s, ref te)) do { if (te.OwnerPid == pid) l.Add(te.Tid); te.Size = Marshal.SizeOf(typeof(TE)); } while (Thread32Next(s, ref te));
        } finally { CloseHandle(s); }
        return l;
    }
    // One thread: its registers and the calls on its stack. suspend: the game is running (freeze); before: the last
    // sample's eip/esp per thread, for "unchanged" instead of the same lines again; detail 1 adds 16 stack words, 2 adds
    // 48 stack words, the code at eip and the memory the registers point at.
    static void DescribeThread(int tid, bool suspend, Dictionary<int, string> before, int detail, string ind, string tag) {
        IntPtr ht = OpenThread(0x0002 | 0x0008 | 0x0040, false, tid);       // suspend/resume, get context, query
        if (ht == IntPtr.Zero) { Line(ind + tag + "thread " + tid + ": cannot be opened (error " + Marshal.GetLastWin32Error() + ")"); return; }
        IntPtr ctx = Marshal.AllocHGlobal(0x2CC);
        try {
            IntPtr start; string from = NtQueryInformationThread(ht, 9, out start, P, IntPtr.Zero) == 0 && start != IntPtr.Zero ? " (from " + Name((ulong)start.ToInt64()) + ")" : "";
            if (!target32) { Line(ind + tag + "thread " + tid + from); return; }
            bool held = suspend && SuspendThread(ht) != -1; byte[] stack = null; uint[] r = null; int err = 0;
            try {
                for (int i = 0; i < 0x2CC; i += 4) Marshal.WriteInt32(ctx, i, 0);
                Marshal.WriteInt32(ctx, 0, 0x10007);                         // CONTEXT_i386: control, integer, segments
                if (P == 8 ? Wow64GetThreadContext(ht, ctx) : GetThreadContext(ht, ctx)) {
                    r = new uint[13]; for (int i = 0; i < 13; i++) r[i] = (uint)Marshal.ReadInt32(ctx, 0x9C + 4 * i);   // edi esi ebx edx ecx eax ebp eip cs eflags esp ss
                    stack = ReadUpTo(r[10], 0x400, true);
                } else err = Marshal.GetLastWin32Error();
            } finally { if (held) ResumeThread(ht); }
            if (r == null) { Line(ind + tag + "thread " + tid + from + ": registers not readable (error " + err + ")"); return; }
            uint eip = r[7], esp = r[10], ebp = r[6];
            string sig = eip.ToString("X8") + "/" + esp.ToString("X8"), was = null;
            bool same = before != null && before.TryGetValue(tid, out was) && was == sig;
            if (same && detail < 2) { Line(ind + tag + "thread " + tid + ": unchanged (eip " + Name(eip) + ")"); return; }
            if (before != null) before[tid] = sig;
            Line(string.Format("{0}{1}thread {2}{3}: eip {4}  esp {5:X8} ebp {6:X8}  eax {7:X8} ebx {8:X8} ecx {9:X8} edx {10:X8} esi {11:X8} edi {12:X8}{13}",
                ind, tag, tid, from, Name(eip), esp, ebp, r[5], r[2], r[4], r[3], r[1], r[0], same ? "  (unchanged)" : ""));
            uint[] words = new uint[stack == null ? 0 : stack.Length / 4]; for (int i = 0; i < words.Length; i++) words[i] = BitConverter.ToUInt32(stack, 4 * i);
            var calls = new StringBuilder(); int nc = 0;
            foreach (uint v in words) if (nc < (detail == 2 ? 24 : 12) && AfterCall(v)) { calls.Append(nc > 0 ? ", " : " ").Append(Name(v)); nc++; }
            Line(ind + "  calls on the stack:" + (nc > 0 ? calls.ToString() : " (none found)"));
            if (detail == 0) return;
            var sw = new StringBuilder(); for (int i = 0; i < Math.Min(words.Length, detail == 2 ? 48 : 16); i++) sw.Append(words[i].ToString("x8")).Append(i % 16 == 15 ? " | " : " ");
            Line(ind + "  stack: " + (words.Length > 0 ? sw.ToString().TrimEnd(' ', '|') : "(not readable)"));
            if (detail < 2) return;
            byte[] code = eip >= 16 ? Read(eip - 16, 48) : null;
            if (code != null) Line(ind + "  code at eip-16: " + Hex(code));
            string[] rn = { "eax", "ebx", "ecx", "edx", "esi", "edi", "ebp" }; uint[] rv = { r[5], r[2], r[4], r[3], r[1], r[0], ebp };
            for (int i = 0; i < rn.Length; i++) { byte[] m = rv[i] >= 0x10000 ? Read(rv[i], 32) : null; if (m != null) Line(ind + "  [" + rn[i] + "] " + Hex(m)); }
        } finally { Marshal.FreeHGlobal(ctx); CloseHandle(ht); }
    }
    // a stack word that is a return address: inside a module, right after a call instruction
    static bool AfterCall(uint a) {
        if (a < 0x10007 || ModuleOf(a) == null) return false;
        byte[] b = Read(a - 7, 7); if (b == null) return false;
        return b[2] == 0xE8 ||                                               // call rel32
               (b[1] == 0xFF && (b[2] == 0x15 || (b[2] & 0xF8) == 0x90)) ||  // call [abs] / [reg+disp32]
               (b[5] == 0xFF && ((b[6] & 0xF8) == 0xD0 || ((b[6] & 0xF8) == 0x10 && b[6] != 0x14 && b[6] != 0x15))) ||   // call reg / [reg]
               (b[4] == 0xFF && ((b[5] & 0xF8) == 0x50 || b[5] == 0x14)) ||  // call [reg+disp8] / [sib]
               (b[3] == 0xFF && b[4] == 0x54) || (b[0] == 0xFF && b[1] == 0x94);   // call [sib+disp8] / [sib+disp32]
    }

    // ---- memory and modules ----
    static byte[] Read(ulong a, int n) {
        if (hProc == IntPtr.Zero || n <= 0) return null;
        var b = new byte[n]; IntPtr got;
        if (!ReadProcessMemory(hProc, new IntPtr((long)a), b, new IntPtr(n), out got) || got.ToInt64() != n) return null;
        return b;
    }
    // up to n bytes, stopping at the end of the memory region (a stack near its top cannot be read 1 KB at a time);
    // words: a whole number of 4-byte words
    static byte[] ReadUpTo(ulong a, int n, bool words = false) {
        MBI m; if (hProc == IntPtr.Zero || VirtualQueryEx(hProc, new IntPtr((long)a), out m, new IntPtr(Marshal.SizeOf(typeof(MBI)))) == IntPtr.Zero) return null;
        long end = m.Base.ToInt64() + m.Size.ToInt64(); int k = (int)Math.Min(n, end - (long)a); if (words) k &= ~3;
        return k > 0 ? Read(a, k) : null;
    }
    static string Hex(byte[] b) { var s = new StringBuilder(); foreach (byte x in b) s.Append(x.ToString("x2")); return s.ToString(); }

    class Mod { public ulong Base, End; public string Name; }
    static List<Mod> mods = new List<Mod>(); static DateTime modsAt = DateTime.MinValue; static readonly object modLock = new object();
    static Mod ModuleOf(ulong a) {
        lock (modLock) {
            if ((DateTime.Now - modsAt).TotalSeconds > 2) {
                modsAt = DateTime.Now; var l = new List<Mod>();
                var hm = new IntPtr[1024]; int need;
                if (hProc != IntPtr.Zero && K32EnumProcessModulesEx(hProc, hm, hm.Length * P, out need, 3)) {   // 32- and 64-bit modules
                    for (int i = 0; i < Math.Min(need / P, hm.Length); i++) {
                        MODINFO mi; var nm = new StringBuilder(260);
                        if (!K32GetModuleInformation(hProc, hm[i], out mi, Marshal.SizeOf(typeof(MODINFO)))) continue;
                        K32GetModuleBaseNameW(hProc, hm[i], nm, 260);
                        l.Add(new Mod { Base = (ulong)mi.Base.ToInt64(), End = (ulong)mi.Base.ToInt64() + (ulong)mi.Size, Name = nm.ToString() });
                    }
                }
                if (l.Count > 0) mods = l;
            }
            foreach (var m in mods) if (a >= m.Base && a < m.End) return m;
            return null;
        }
    }
    static string Name(ulong a) { var m = ModuleOf(a); return m == null ? a.ToString("X8") : string.Format("{0:X8} ({1}+0x{2:X})", a, m.Name, a - m.Base); }
    static string ImagePath() { var s = new StringBuilder(1024); int n = s.Capacity; return QueryFullProcessImageName(hProc, 0, s, ref n) ? s.ToString() : "?"; }

    // MiniDumpWriteDump can itself crash on a badly damaged game (2026-10-14: after a graphics driver crash in the game,
    // dbgcore.dll raised an access violation and took PowerShell, the launcher, down with it): such an exception is
    // caught here (HandleProcessCorruptedStateExceptions) and the dump is skipped.
    [HandleProcessCorruptedStateExceptions, System.Security.SecurityCritical]
    static string Dump(string kind) {
        if (!Monitor.TryEnter(dumpLock, 20000)) { Line("  minidump skipped (another one is still being written)"); return null; }
        try {
            string name = kind + "_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".dmp", path = Path.Combine(folder, name);
            try {
                bool ok; int err = 0;
                using (var fs = new FileStream(path, FileMode.Create, FileAccess.ReadWrite, FileShare.Read)) {
                    ok = MiniDumpWriteDump(hProc, pid, fs.SafeFileHandle.DangerousGetHandle(), DumpType, IntPtr.Zero, IntPtr.Zero, IntPtr.Zero);
                    if (!ok) err = Marshal.GetLastWin32Error();
                }
                if (!ok) { Line("  minidump failed (error 0x" + err.ToString("X") + ")"); try { File.Delete(path); } catch { } return null; }
                Line("  minidump: " + name + " (" + (new FileInfo(path).Length / 1024) + " KB)");
                return name;
            } catch (AccessViolationException) { Line("  minidump failed: Windows' dump code crashed on the damaged game; no minidump"); try { File.Delete(path); } catch { } return null; }
            catch (Exception x) { Line("  minidump failed: " + x.Message); return null; }
        } finally { Monitor.Exit(dumpLock); }
    }
}

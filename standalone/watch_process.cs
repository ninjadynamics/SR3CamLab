// Launch-only support for watch.ps1. The recorder itself remains watchdog.cs.
using System;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Text;
public sealed class Sr3WatchProcess : IDisposable {
    [StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)] struct Startup {
        public int cb; public string reserved, desktop, title;
        public int x,y,cx,cy,xchars,ychars,fill,flags;
        public short show,reserved2; public IntPtr bytes,input,output,error;
    }
    [StructLayout(LayoutKind.Sequential)] struct Info { public IntPtr process,thread; public int pid,tid; }
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool CreateProcess(
        string app,StringBuilder command,IntPtr pa,IntPtr ta,bool inherit,int flags,IntPtr env,string cwd,ref Startup startup,out Info info);
    [DllImport("kernel32.dll",SetLastError=true)] static extern uint ResumeThread(IntPtr thread);
    [DllImport("kernel32.dll",SetLastError=true)] static extern bool GetProcessTimes(IntPtr process,out long created,out long exited,out long kernel,out long user);
    [DllImport("kernel32.dll",CharSet=CharSet.Unicode,SetLastError=true)] static extern bool QueryFullProcessImageName(IntPtr process,int flags,StringBuilder path,ref int size);
    [DllImport("kernel32.dll")] static extern bool TerminateProcess(IntPtr process,uint code);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    Info info; bool resumed;
    public int Id { get { return info.pid; } }
    public long CreationTime { get; private set; }
    public static bool Matches(IntPtr process,string expected,long creation) {
        long created,exited,kernel,user; int size=32768; StringBuilder path=new StringBuilder(size);
        if (!GetProcessTimes(process,out created,out exited,out kernel,out user) ||
            !QueryFullProcessImageName(process,0,path,ref size)) throw new Win32Exception();
        return created==creation && String.Equals(path.ToString(),expected,StringComparison.OrdinalIgnoreCase);
    }
    public Sr3WatchProcess(string exe) {
        Startup startup = new Startup(); startup.cb = Marshal.SizeOf(typeof(Startup));
        if (!CreateProcess(exe,new StringBuilder("\""+exe+"\""),IntPtr.Zero,IntPtr.Zero,false,4,IntPtr.Zero,
                           System.IO.Path.GetDirectoryName(exe),ref startup,out info)) throw new Win32Exception();
        long created,exited,kernel,user;
        if (!GetProcessTimes(info.process,out created,out exited,out kernel,out user)) { Dispose(); throw new Win32Exception(); }
        CreationTime=created;
    }
    public void Resume() {
        if (resumed) return;
        if (ResumeThread(info.thread)==0xffffffff) throw new Win32Exception();
        resumed=true;
    }
    public void Dispose() {
        // Only our never-resumed child is terminated on setup failure. Once it
        // runs, stopping the recorder must leave the game alive.
        if (info.process!=IntPtr.Zero) {
            if (!resumed) TerminateProcess(info.process,125);
            CloseHandle(info.process); info.process=IntPtr.Zero;
        }
        if (info.thread!=IntPtr.Zero) { CloseHandle(info.thread); info.thread=IntPtr.Zero; }
    }
}

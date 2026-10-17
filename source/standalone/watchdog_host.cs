// The same watchdog.ps1 runs inside this x64 process, using Windows PowerShell's
// installed engine. No PowerShell child and no duplicate recorder. MIT.
using System;
using System.IO;
using System.Collections.Generic;
using System.Management.Automation;
using System.Management.Automation.Runspaces;
using System.Text;

static class WatchdogHost {
    static int Main(string[] args) {
        Console.OutputEncoding = new UTF8Encoding(false);
        try {
            if (IntPtr.Size != 8) throw new Exception("The watchdog host must be 64-bit.");
            string script = Path.Combine(AppDomain.CurrentDomain.BaseDirectory,"watchdog.ps1");
            var parameters = new Dictionary<string,object>(StringComparer.OrdinalIgnoreCase);
            for (int i=0; i<args.Length; ++i) {
                if (args[i]=="--help" || args[i]=="-Help") {
                    Console.WriteLine("watchdog.exe -LaunchExe <exe> [-SettingsPath <yaml>] -CrashDirectory <folder>\n"+
                        "watchdog.exe -ProcessId <pid> -ExpectedExePath <exe> -ExpectedStartFileTime <FILETIME> -CrashDirectory <folder>");
                    return 0;
                }
                string key=args[i];
                if (++i==args.Length) throw new Exception("Missing value for "+key);
                if (key=="--script") { script=Path.GetFullPath(args[i]); continue; }
                if (!key.StartsWith("-") || key.Length<2) throw new Exception("Expected a named argument: "+key);
                key=key.Substring(1);
                if (parameters.ContainsKey(key)) throw new Exception("Duplicate argument: "+key);
                parameters.Add(key,args[i]);
            }
            if (!File.Exists(script)) throw new Exception("Cannot find "+script);
            var initial=InitialSessionState.CreateDefault();
            initial.ExecutionPolicy=Microsoft.PowerShell.ExecutionPolicy.Bypass;
            using (var runspace=RunspaceFactory.CreateRunspace(initial)) {
                runspace.Open();
                using (var ps=PowerShell.Create()) {
                    ps.Runspace=runspace;
                    ps.AddCommand(script);
                    foreach(var pair in parameters) ps.AddParameter(pair.Key,pair.Value);
                    var output=new PSDataCollection<PSObject>();
                    output.DataAdded += delegate(object sender,DataAddedEventArgs e) {
                        Console.WriteLine(output[e.Index]);
                    };
                    ps.Streams.Error.DataAdded += delegate(object sender,DataAddedEventArgs e) {
                        Console.Error.WriteLine(ps.Streams.Error[e.Index]);
                    };
                    var pending=ps.BeginInvoke<PSObject,PSObject>(null,output);
                    ps.EndInvoke(pending);
                    return ps.HadErrors?1:0;
                }
            }
        } catch(Exception e) { Console.Error.WriteLine(e.Message); return 1; }
    }
}

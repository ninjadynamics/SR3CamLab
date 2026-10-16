"""Regression: Hornet video acknowledgment delayed five seconds; C/PS parity.
Run with --out pointing to a completed tools/sr3mods/build.py output.
Only fake game memory is used. No real game process or desktop access.
"""
import pathlib, subprocess, sys, tempfile
import build as b
import live_lockstep as live
src=pathlib.Path(__file__).resolve().parent; repo=src.parents[1]
out=pathlib.Path(sys.argv[sys.argv.index('--out')+1]).resolve()
flags=b.X86+['-I',str(out),'-I',str(repo/'standalone'),'-I',str(src)]
shared=['patchcore.o','pc_live.o','pc_json.o','pc_host.o','watch_launcher.o','settings.o','ucrt_stdio.o','builtins.o']
libs=[str(p) for p in sorted((out/'imp').glob('lib*.a'))]
link=[b.GCC,'-m32','-nostdlib','-nostartfiles','-s','-Wl,--no-insert-timestamp,--gc-sections']
mock=(src/'livetest.c').read_text()
mock=mock.replace('static int t_write(', 'static int video_delay_ms=5000;\nstatic int t_write(')
mock=mock.replace('va == BASE + 0x2270 && I(va) != 0)', 'va == BASE + 0x2270 && I(va) != 0 && !(I(va)==20 && video_delay_ms>0))')
sleep='static void t_sleep(GameMem *m, int ms) { (void)m; (void)ms; }'
assert sleep in mock
mock=mock.replace(sleep, '''static void t_sleep(GameMem *m, int ms) {
    (void)m;
    if(BASE && I(BASE+0x2270)==20 && video_delay_ms>0) {
        video_delay_ms-=ms;
        if(video_delay_ms<=0) {
            char path[300]; S((unsigned)I(BASE+0x2274),path,sizeof path);
            PutS(0xAD2F90u+19*0x16C+0xC,path);
            PutI(0xAD2F90u+19*0x16C+4,1);PutI(BASE+0x2270,0);
        }
    }
}''')
(out/'delayed_livetest.c').write_text(mock)
b.run([b.GCC]+flags+['-c',str(out/'delayed_livetest.c'),'-o',str(out/'delayed.o')])

exe=out/'delayed_livetest.exe'
b.run(link+['-Wl,-e,_entry@0',str(out/'delayed.o')]+[str(out/n) for n in shared]+libs+['-o',str(exe)])
ps=(src/'live_ps1.ps1').read_text(encoding='utf-8-sig')
ps=ps.replace("$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\\..')).Path", "$repo = '" + str(repo) + "'")
ps=ps.replace('public static class MockGame {','''public static class MockGame {
    static int VideoDelay = 5000;
    public static void Sleep(int ms) {
        if (Base != 0 && I(Base + 0x2270) == 20 && VideoDelay > 0) {
            VideoDelay -= ms;
            if (VideoDelay <= 0) {
                PutS(0xAD2F90 + 19 * 0x16C + 0xC, S(I(Base + 0x2274)));
                PutI(0xAD2F90 + 19 * 0x16C + 4, 1); PutI(Base + 0x2270, 0);
            }
        }
    }''')
ps=ps.replace('va == Base + 0x2270 && I(va) != 0)', 'va == Base + 0x2270 && I(va) != 0 && !(I(va) == 20 && VideoDelay > 0))')
ps=ps.replace('function Skip-Sleep($ms) { }','function Skip-Sleep($ms) { [MockGame]::Sleep($ms) }')
script=out/'delayed_ps1.ps1';script.write_text(ps,encoding='utf-8-sig')

traces=[]
with tempfile.TemporaryDirectory(prefix='sr3_delayed_card_') as tmp:
    for label in ('c','ps'):
        root=str(pathlib.Path(tmp)/label)
        g=live.SCENARIOS[0](); g.file('frontend/PC/Videos/HORNET.wmv')
        sc,game,mod=live.lay_out(g,root); trace=str(pathlib.Path(root)/'trace.txt')
        args=([str(exe),sc,game,mod,str(repo/'profiles.yaml'),trace] if label=='c' else
              ['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),
               '-Scenario',sc,'-GameExe',game,'-ModDir',mod,'-Out',trace])
        subprocess.run(args,check=True,capture_output=True)
        lines=live.norm(trace,root)
        assert any('CARSLIDE_HORNET_GRAVEL_1 plays' in s for s in lines), label
        traces.append(lines)
    assert traces[0]==traces[1], 'Delayed Hornet C/PowerShell traces differ'
print('Delayed Hornet: five-second acknowledgment binds video; C/PS traces match.')

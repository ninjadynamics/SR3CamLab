"""Replay timing table reloads between races in both patcher implementations.
No game launch. Assert writes and restoration, not just C/PowerShell agreement.
"""
from pathlib import Path
import argparse, json, subprocess, sys, tempfile
R=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(R/'source/tools/sr3mods'))
import live_lockstep as live
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--prove-old',action='store_true');a=p.parse_args()
TABLE=0x33000000;NEW=0x93000000;OFF=4+0xc60*4
want=bytes(range(256))*12+bytes(0xc60-3072)
g=live.base_game(live.Game('checkpoint_reload'))
g.file('Main_release/tracks/_SR3Extras/classic_mode.txt','2')
g.file('Main_release/tracks/_SR3Extras/switch.json',live.switch_json({'Desert4':dict(title='Desert',tracks=[dict(title='Mountain',dir='1')])}))
g.file('Main_release/track1/Desert4/keep');g.file('Main_release/track1/Desert4/arcade_times.bin',want)
g.put(NEW,bytes(4+0xc60*6))
F=g.frame
F(1,3,'Desert4',mode_val=2)
F(1,3,'Desert4',view=1,mode_val=2) # select, table ready
F(1,3,'Desert4',view=0,mode_val=2)
F(0,0,'Desert4',set=[(TABLE+OFF,bytes(0xc60))]) # load resets same address
F(0,0,'Desert4',dt=500,set=[(TABLE+OFF,bytes(0xc60))]) # reset after loading
F(0,0,'Desert4') # periodic repair
F(1,3,'Desert4',mode_val=2) # restore when leaving alternative
F(1,3,'Desert4',view=1,mode_val=2,set=[(0x3100000c,live.i32(0))]) # second selection before DB ready
F(1,3,'Desert4',mode_val=2,set=[(0x3100000c,live.i32(NEW))]) # arrives without track change, high-bit pointer
F(0,0,'Desert4',set=[(NEW+OFF,bytes(0xc60))]) # second load
F(1,3,'Desert4',mode_val=2) # restore current table only
expected={1:(TABLE+OFF,want),3:(TABLE+OFF,want),5:(TABLE+OFF,want),6:(TABLE+OFF,bytes(0xc60)),8:(NEW+OFF,want),9:(NEW+OFF,want),10:(NEW+OFF,bytes(0xc60))}
expected={f+1:v for f,v in expected.items()}
results={};traces=[]
with tempfile.TemporaryDirectory(prefix='sr3_checkpoint_') as tmp:
 for label in ['c','ps']:
  root=str(Path(tmp)/label);sc,game,mod=live.lay_out(g,root);trace=str(Path(root)/'trace.txt')
  args=([str(a.out/'livetest.exe'),sc,game,mod,str(R/'source/profiles.yaml'),trace] if label=='c' else ['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(R/'source/tools/sr3mods/live_ps1.ps1'),'-Scenario',sc,'-GameExe',game,'-ModDir',mod,'-Out',trace])
  q=subprocess.run(args,capture_output=True,text=True);lines=live.norm(trace,root);assert lines,(label,q.stdout,q.stderr)
  frames={};fr=-1
  for line in lines:
   if line.startswith('F '):fr=int(line.split()[1])
   if line.startswith('W '):
    _,va,keep,b=line.split()
    if int(va,16) in [TABLE+OFF,NEW+OFF]:frames[fr]=(int(va,16),bytes.fromhex(b))
  results[label]={'frames':sorted(frames),'expected':sorted(expected),'passed':frames==expected}
  if not a.prove_old:assert frames==expected,(label,results[label])
  traces.append(lines)
 if not a.prove_old:assert traces[0]==traces[1],'C/PS differ'
print(json.dumps(results,indent=2))
if a.prove_old:assert all(not x['passed'] for x in results.values()),'old build unexpectedly passed'

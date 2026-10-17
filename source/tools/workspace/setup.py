"""Offline workspace setup. Builds from source; preserves user content and settings."""
import argparse, hashlib, importlib.util, json, os, shutil, subprocess, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
DIRS = ('apps/camlab','apps/runtime','work/blender','content/classic/courses','content/audio','content/frontend',
        'content/handling','config','game','scratchpad/build','scratchpad/import','scratchpad/runs/steering',
        'work','screenshots','toolchain/deps')

def digest(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def dump(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf-8')
def module(p):
    spec=importlib.util.spec_from_file_location(p.stem,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def scalar(text,section,key,value):
    lines=text.splitlines();start=next((i for i,l in enumerate(lines) if l==section+':'),None)
    if start is None: lines += [section+':'];start=len(lines)-1
    end=next((i for i in range(start+1,len(lines)) if lines[i] and not lines[i][0].isspace() and not lines[i].startswith('#')),len(lines))
    line='  '+key+': '+value
    for i in range(start+1,end):
        if lines[i].lstrip().startswith(key+':'):lines[i]=line;break
    else:lines.insert(end,line)
    return '\n'.join(lines)+'\n'
def quote(p):return "'"+str(p).replace("'","''")+"'"
def initialize(root,python):
    root=root.resolve();src=root/'source'
    for name in DIRS:(root/name).mkdir(parents=True,exist_ok=True)
    for name in ('profiles.yaml','defaults.yaml'):
        dst=root/'apps/camlab'/name
        if not dst.exists():shutil.copy2(src/name,dst)
    dst=root/'config/handling.json'
    if not dst.exists():shutil.copy2(src/'handling.example.json',dst)
    p=root/'settings.yaml'
    text=p.read_text(encoding='utf-8-sig') if p.exists() else (src/'standalone/settings.yaml').read_text()
    text=scalar(text,'launch','game_path',quote('game/Rally/Rally.exe'))
    text=scalar(text,'patches','mod_folder',quote(root/'config'))
    text=scalar(text,'patches','profiles_file',quote(root/'apps/camlab/profiles.yaml'))
    text=scalar(text,'patches','watchdog','off')
    p.write_text(text,encoding='utf-8')
    p=root/'config/workspace.json';cfg=json.loads(p.read_text()) if p.exists() else {}
    cfg.update(version=2,python=str(python),game='game/Rally',settings='settings.yaml',
               baseline='config/accepted-baseline.json',runs='scratchpad/runs/steering',screenshots='screenshots')
    # Never enable an unverified generated physics payload merely because it exists.
    cfg.setdefault('candidate','');dump(p,cfg)
    p=root/'config/import.json';imp=json.loads(p.read_text()) if p.exists() else {}
    imp.update(data_root=str(root/'content'),classic_root=str(root/'content/classic'),
               work_root=str(root/'scratchpad/import'),sr3_game=str(root/'game/Rally'))
    imp.setdefault('threads',2);dump(p,imp)
    for name in ('PLAY.bat',):shutil.copy2(src/'tools/workspace/templates'/name,root/name)
    for source,dest in [('CAMLAB-PLAY.bat','PLAY.bat'),('CAMLAB-patch.ps1','patch.ps1')]:
        shutil.copy2(src/'tools/workspace/templates'/source,root/'apps/camlab'/dest)
    return cfg

def copy_game(root,source,build):
    source=source.resolve()
    if source.is_file():source=source.parent
    target=(root/'game/Rally').resolve()
    if target.exists():raise ValueError('The local game already exists; setup never replaces its assets.')
    if source==target or source in target.parents or target in source.parents:raise ValueError('Game source and destination must be separate.')
    for name in ('Shell','ShellData'):
        sibling=source.parent/name
        if sibling.is_dir():
            for base,dirs,files in os.walk(sibling,followlinks=False):
                for n in dirs+files:
                    if (Path(base)/n).lstat().st_file_attributes & 0x400:raise ValueError('Game source contains a directory link.')
    module(root/'source/standalone/overlay.py').create(source,target,'copy',build/'dinput8.dll')
    for name in ('Shell','ShellData'):
        sibling=source.parent/name;dst=root/'game'/name
        if sibling.is_dir() and not dst.exists():shutil.copytree(sibling,dst)

def install(root,build,mods):
    pairs=[(build/'launch.exe',root/'apps/runtime/launch.exe'),(build/'settings.exe',root/'settings.exe'),
           (build/'watchdog.exe',root/'source/standalone/watchdog.exe')]
    if (root/'game/Rally/Rally.exe').is_file():
        pairs += [(build/'dinput8.dll',root/'game/Rally/dinput8.dll'),(mods/'sr3mods.dll',root/'game/Rally/sr3mods.dll')]
        for name in ('SDL-LICENSE.txt','raylib-LICENSE.txt'):pairs.append((build/name,root/'game/Rally'/name))
    backup=root/'work'/('setup-'+time.strftime('%Y%m%d-%H%M%S'))
    for src,dst in pairs:
        if dst.exists() and digest(src)==digest(dst):continue
        if dst.exists():
            old=backup/dst.relative_to(root);old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dst,old)
        dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
    p=root/'config/accepted-baseline.json'
    baseline=json.loads(p.read_text()) if p.exists() else {'files':{},'candidate_sha256':''}
    for name in ('Rally.exe','dinput8.dll','sr3mods.dll'):
        f=root/'game/Rally'/name
        if f.exists():baseline['files'][name]=digest(f)
    dump(p,baseline)
    if (root/'game/Rally').exists():
        (root/'game/Rally/PLAY-STANDALONE.bat').write_text('@echo off\r\ncall "%~dp0..\\..\\PLAY.bat" %*\r\n')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=ROOT);p.add_argument('--game-source',type=Path)
    p.add_argument('--jobs',type=int,default=2);p.add_argument('--check',action='store_true')
    p.add_argument('--configure-only',action='store_true');p.add_argument('--build-only',action='store_true')
    a=p.parse_args();root=a.root.resolve();src=root/'source'
    if a.jobs<1:p.error('--jobs must be positive')
    # Check reads only, including on an extracted release before initialization.
    cb=module(src/'tools/import/core/cbuild.py');gcc=cb.find_gcc()
    native=module(src/'standalone/native_build.py')
    sdl=root/'toolchain/deps/SDL';raylib=root/'toolchain/deps/raylib'
    if not a.configure_only:
        if not Path(gcc).is_file():raise FileNotFoundError('Compiler missing. Bundle toolchain/mingw or configure gcc in config/import.json.')
        native.vendor('sdl',sdl);native.vendor('raylib',raylib)
    if a.check:
        print('PASS: compiler and pinned SDL/raylib sources available; no build or game launched.');return
    if not a.build_only and not a.configure_only:
        busy=subprocess.run(['powershell','-NoProfile','-Command',"if (Get-Process Rally,emulator,emulator_multicpu -ErrorAction SilentlyContinue) { exit 1 }"],capture_output=True)
        if busy.returncode:raise RuntimeError('Close Rally and Model 2 before setup installs binaries.')
    initialize(root,Path(sys.executable))
    if a.configure_only:print('Local layout and configuration ready; existing content preserved.');return
    build=root/'scratchpad/build/standalone/native';mods=root/'scratchpad/build/sr3mods'
    env=dict(os.environ,SR3_GCC=str(gcc),SR3_SETTINGS=str(root/'config/import.json'))
    def run(*args):subprocess.run([sys.executable,*map(str,args)],check=True,cwd=src,env=env)
    run(src/'standalone/build.py','--gcc',gcc,'--jobs',a.jobs,'--out',build,'--sdl-source',sdl,'--raylib-source',raylib)
    run(src/'tools/sr3mods/build.py','--out',mods)
    run(src/'tools/import/core/cbuild.py')
    if a.build_only:print('Build and required checks passed; installed game binaries unchanged.');return
    if not (root/'game/Rally/Rally.exe').is_file():
        if not a.game_source:raise ValueError('Supply --game-source with your own unmodified SR3 Rally folder. Build is cached.')
        copy_game(root,a.game_source,build)
    install(root,build,mods)
    if not (root/'apps/camlab/camlab.exe').exists():print('CamLab binary missing: include the existing CamLab release under apps/camlab; its source build remains TODO.')
    print('Setup complete. Open settings.exe or PLAY.bat. Watchdog OFF. Imported content stays local.')
if __name__=='__main__':
    try:main()
    except Exception as e:print('SETUP failed:',e,file=sys.stderr);sys.exit(1)

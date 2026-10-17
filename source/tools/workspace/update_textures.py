"""Refresh local HD textures with the existing fast lane; retain launcher file checks."""
import argparse,hashlib,json,sys
from pathlib import Path
repo=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(repo/'tools/import/core'))
import texfast

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--workspace',type=Path,default=repo.parent)
    ap.add_argument('--check',action='store_true')
    a=ap.parse_args();root=a.workspace.resolve()
    cfg=json.loads((root/'config/workspace.json').read_text())
    game=root/cfg['game'];manifest=root/cfg['baseline']
    baseline=json.loads(manifest.read_text())
    slots=sorted((game/'Main_release').glob('track*/Desert4/texmap.json'))
    for slot in slots:
        m=json.loads(slot.read_text())
        if not Path(m['extra_tex']).is_dir():raise FileNotFoundError(m['extra_tex'])
    if a.check:
        print('PASS:',len(slots),'installed texture maps resolve to local source folders; no files changed.');return
    if texfast.game_running():raise RuntimeError('Close Rally before updating textures.')
    # Do not bless unrelated changes to the accepted setup.
    for name,expected in baseline['files'].items():
        if hashlib.sha256((game/name).read_bytes()).hexdigest()!=expected:raise RuntimeError('Unexpected existing change: '+name)
    for slot in slots:
        count=texfast.refresh(str(slot.parent))
        print(slot.parent,':',count or 0,'textures updated')
        if count:
            for name in baseline['files']:
                if (game/name).parent==slot.parent:
                    baseline['files'][name]=hashlib.sha256((game/name).read_bytes()).hexdigest()
            manifest.write_text(json.dumps(baseline,indent=2)+'\n')
if __name__=='__main__':main()

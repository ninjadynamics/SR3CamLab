"""Run with Blender -b --factory-startup -t 2 --python this.py -- MAP.json SCENE.blend [...]. No rendering."""
import bpy,sys,json,os,shutil,hashlib
from pathlib import Path
args=sys.argv[sys.argv.index('--')+1:];mapping=json.loads(Path(args[0]).read_text())
root=Path(__file__).resolve().parents[3];backup=root/'work/blender-path-migration';backup.mkdir(parents=True,exist_ok=True)
report=[]
def translated(path):
 for old,new in sorted(mapping,key=lambda pair:len(pair[0]),reverse=True):
  if path.lower()==old.lower() or path.lower().startswith(old.lower()+os.sep):return new+path[len(old):]
 return path
for filename in args[1:]:
 path=Path(filename).resolve()
 if not (path.is_relative_to(root/'content') or path.is_relative_to(root/'work/blender')):raise ValueError('Only local content scenes may be updated.')
 bpy.ops.wm.open_mainfile(filepath=str(path))
 changes=[];missing=[]
 for img in bpy.data.images:
  if img.packed_file or not img.filepath:continue
  original=bpy.path.abspath(img.filepath);target=translated(os.path.normpath(original))
  if Path(target).is_file():
   relative=os.path.relpath(target,path.parent)
   new='//'+relative.replace('\\','/')
   if new!=img.filepath:changes.append([img.name,img.filepath,new]);img.filepath=new
  elif img.source=='FILE':missing.append([img.name,original])
 if missing:raise RuntimeError('Missing image sources; scene NOT saved: '+str(missing[:8]))
 if changes:
  dest=backup/path.name
  if not dest.exists():shutil.copy2(path,dest)
  bpy.context.preferences.filepaths.save_version=0
  bpy.ops.wm.save_as_mainfile(filepath=str(path))
 report.append({'scene':str(path),'changed_images':len(changes),'missing':missing,'changes':changes})
(backup/'report.json').write_text(json.dumps(report,indent=2))
print('Image paths updated; no geometry or light baking:',[(x['scene'],x['changed_images']) for x in report])

"""20 s fly-through MP4 (1280x720, 30 fps, one lap) of a course's all-SR3 variant: frames by bl_fly.py (resumable, in
batches so a stop loses little), assembled with ffmpeg libx264, kept under 28 MB.
    python fly_all.py [course ...]        -> ../previews/fly_<name>_allsr3.mp4"""
import os, sys, subprocess, json
from common import *
import course
BL = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"; N = 600

def main(c):
    cfg = course.use('src', c); import build_classic as BC
    name = 'step%02d_%s_allsr3_desert4' % (cfg['steps']['allsr3'], cfg['name']); obj = os.path.join(WORK, 'previews', 'sr3_decoded', name + '.obj')
    if not os.path.exists(obj):
        import preview_obj; preview_obj.main(name)
    fr = os.path.join(TMP, 'fly', cfg['name'])
    for a in range(0, N, 150):
        if all(os.path.exists(os.path.join(fr, 'f%05d.jpg' % k)) for k in range(a, min(N, a + 150))): continue
        subprocess.run([BL, '-b', '--factory-startup', '--python', os.path.join(HERE, 'bl_fly.py'), '--', obj, fr, BC.CSV, str(N), str(a), str(min(N, a + 150))], capture_output=True, text=True, timeout=3000)
    out = os.path.join(WORK, 'previews', 'fly_%s_allsr3.mp4' % cfg['name'])
    for crf in (21, 24, 27, 30):
        subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-framerate', '30', '-i', os.path.join(fr, 'f%05d.jpg'), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', str(crf), '-preset', 'slow', '-movflags', '+faststart', out], check=True)
        mb = os.path.getsize(out) / 1e6
        if mb < 28: break
    print('%s: %d frames, crf %d, %.1f MB' % (out, len(os.listdir(fr)), crf, mb))

if __name__ == '__main__':
    for c in sys.argv[1:] or ['1', '2', '3', '4']: main(c)

"""Top-down plot of an OBJ (x vs z), road objects highlighted. usage: plot_obj.py in.obj out.png [roadprefix]"""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection, PolyCollection
src, dst = sys.argv[1], sys.argv[2]
roadp = sys.argv[3] if len(sys.argv) > 3 else "road"
V = []; faces_r = []; faces_s = []; cur = ""
for line in open(src):
    if line.startswith("v "):
        V.append([float(t) for t in line.split()[1:4]])
    elif line.startswith("o "): cur = line[2:].strip()
    elif line.startswith("f "):
        idx = [int(t.split("/")[0]) - 1 for t in line.split()[1:]]
        (faces_r if cur.startswith(roadp) else faces_s).append(idx)
V = np.array(V)
fig, ax = plt.subplots(figsize=(11, 11), dpi=100)
def polys(fs): return [V[f][:, [0, 2]] for f in fs]
if faces_s: ax.add_collection(PolyCollection(polys(faces_s), facecolors=(0.3, 0.6, 0.3, 0.25), edgecolors=(0.2, 0.4, 0.2, 0.3), linewidths=0.2))
if faces_r: ax.add_collection(PolyCollection(polys(faces_r), facecolors=(0.8, 0.2, 0.1, 0.9), edgecolors="none"))
if len(sys.argv) > 4:
    V2 = []; F2 = []
    for line in open(sys.argv[4]):
        if line.startswith("v "): V2.append([float(t) for t in line.split()[1:4]])
        elif line.startswith("f "): F2.append([int(t.split("/")[0]) - 1 for t in line.split()[1:]])
    V2 = np.array(V2)
    ax.add_collection(PolyCollection([V2[f][:, [0, 2]] for f in F2], facecolors=(0.9, 0.1, 0.1, 0.35), edgecolors=(0.6, 0, 0, 0.6), linewidths=0.3))
ax.set_xlim(V[:, 0].min() - 20, V[:, 0].max() + 20); ax.set_ylim(V[:, 2].min() - 20, V[:, 2].max() + 20)
ax.set_aspect("equal"); ax.grid(True, alpha=0.3); ax.set_title(src.replace("\\", "/").split("/")[-1] + "  (metres)")
fig.savefig(dst, bbox_inches="tight")

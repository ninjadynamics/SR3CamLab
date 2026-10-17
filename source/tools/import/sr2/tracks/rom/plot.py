"""Plan-view gameplay plots: ../course<N>/gameplay_plot.png (game +X right, game +Z up; not mirrored)."""
import sys, os, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from matplotlib.patches import Patch
from sr2course import *
from extract import MAIN_STAGE, SURF_COL, OUT

def plot(k):
    J = json.load(open(OUT + 'course%d/gameplay.json' % k)); S = sections(MAIN_STAGE[k]); Pf = S['Pf']; Pu = S['Pu']
    T = Pf[:, 4:13].reshape(-1, 3, 3)[:, :, [0, 2]].astype(float); a = (Pu[:, 74].astype(np.int64) & 0xFFFF)
    fig, ax = plt.subplots(figsize=(22, 22), dpi=100); ax.set_facecolor('#f4f3ee')
    wall = (a & 0x8000) != 0
    ax.add_collection(PolyCollection(T[wall], facecolors='#dddad0', edgecolors='none'))
    used = sorted(set(int(x) & 0xF for x in a[~wall]))
    for t in used:
        m = (~wall) & ((a & 0xF) == t)
        ax.add_collection(PolyCollection(T[m], facecolors=[SURF_COL[t]], edgecolors='none'))
    sl = J['section_list']; P = np.array([[s['road_centre'][0] if s['road_centre'] else s['centre'][0], -(s['road_centre'][2] if s['road_centre'] else s['centre'][2])] for s in sl])
    Pc = np.vstack([P, P[:1]]); ax.plot(Pc[:, 0], Pc[:, 1], '-', color='k', lw=0.8, alpha=0.6)
    for i in range(0, 256, 8):
        ax.text(P[i, 0], P[i, 1], str(i), fontsize=6.5, color='#333', ha='center', va='center', bbox=dict(boxstyle='round,pad=0.12', fc='white', ec='none', alpha=0.7))
    RL = np.array([[nd['position'][0], -nd['position'][2]] for nd in J['rival_line']['nodes']]); ax.plot(RL[:, 0], RL[:, 1], '-', color='#e000a0', lw=1.0, alpha=0.9, zorder=4)
    ext = max(np.ptp(T[:, :, 0]), np.ptp(T[:, :, 1]))
    # splits
    for s in J['split_points']['list']:
        e = sl[s['section'] % 256]; ax.plot([e['entry_left'][0], e['entry_right'][0]], [-e['entry_left'][1], -e['entry_right'][1]], '-', color='#008a2e', lw=1.2, alpha=0.8)
    # checkpoints
    for c in J['checkpoints']['list']:
        gl, gr = c['gate_left'], c['gate_right']; ax.plot([gl[0], gr[0]], [-gl[1], -gr[1]], '-', color='red', lw=3.5)
        ax.annotate('LAP / FINISH LINE (sec 0)' if c['is_lap_line'] else 'CHECKPOINT %d (sec %d, %.0f m)' % (c['index'] + 1, c['section'], c['distance_m']), (gl[0], -gl[1]), xytext=(18, 18), textcoords='offset points', color='red', fontsize=11, weight='bold',
                    arrowprops=dict(arrowstyle='-', color='red'))
    # start
    sx, sz = J['start']['position'][0], -J['start']['position'][2]; hx, hz = J['start']['heading'][0], -J['start']['heading'][2]
    ax.plot([sx], [sz], marker='*', ms=22, color='magenta', mec='k', zorder=5)
    ax.annotate('', xy=(sx + 60 * hx, sz + 60 * hz), xytext=(sx, sz), arrowprops=dict(arrowstyle='-|>', color='magenta', lw=3), zorder=5)
    ax.annotate('START (%.1f, %.1f) section %s' % (sx, sz, J['start']['section']), (sx, sz), xytext=(-170, -28), textcoords='offset points', color='magenta', fontsize=11, weight='bold')
    # pace notes
    cen = P.mean(axis=0)
    for i, nt in enumerate(J['pace_notes']['list']):
        x, z = nt['position'][0], -nt['position'][2]; d = np.array([x, z]) - cen; d = d / (np.linalg.norm(d) + 1e-9)
        ax.plot([x], [z], 'o', ms=7, color='#1040d0', mec='white', zorder=6)
        if nt['target_position']:
            tx, tz = nt['target_position'][0], -nt['target_position'][2]; ax.plot([tx], [tz], 'x', ms=6, color='#1040d0', zorder=6)
        lab = '%d: %s' % (nt['section'], nt['spoken']) + ('' if nt['condition_code'] == -1 else '\n[%s]' % nt['condition'])
        off = d * (70 + 28 * (i % 3))
        ax.annotate(lab, (x, z), xytext=(off[0], off[1]), textcoords='offset points', fontsize=9, color='#0a2a90', ha='center', va='center',
                    bbox=dict(boxstyle='round,pad=0.2', fc='white', ec='#1040d0', alpha=0.9), arrowprops=dict(arrowstyle='-', color='#1040d0', lw=0.8), zorder=7)
    for ev in J['crowd_and_praise_points']['list']:
        x, z = ev['position'][0], -ev['position'][2]; ax.plot([x], [z], 's', ms=6, color='#d08010', mec='k', zorder=6)
        ax.annotate('%d: %s' % (ev['section'], ev['condition'].split(':')[0].split('(')[0]), (x, z), xytext=(8, -12), textcoords='offset points', fontsize=7, color='#805000')
    ax.set_aspect('equal'); ax.autoscale_view(); ax.margins(0.08)
    hs = [Patch(fc=SURF_COL[t], label='%s (%d)' % (SURF[t], t)) for t in used] + [Patch(fc='#dddad0', label='blocked zone / wall (bit 15)')]
    ax.legend(handles=hs, loc='upper right', fontsize=11, title='collision surface type')
    tsum = J['checkpoints']['times_s']['championship (game type 0)']['difficulty_0']
    ax.set_title('SEGA Rally 2 - course table index %d: %s (stage %d, course id %d) - lap %.0f m, 256 sections\nplan view, game +X right / game +Z up. red = checkpoints (time: start %s s, +%s s), green = split points, blue dots = pace-note trigger (x = where the announced distance lands), small numbers = section index, thin magenta = rival (computer car) line'
                 % (k, J['course'].split(' (')[0], J['stage'], J['course_id'], J['lap_length_m'], tsum['initial_s'], tsum['added_at_each_checkpoint_passage_s']), fontsize=12)
    ax.set_xlabel('game X (m)'); ax.set_ylabel('game Z (m)')
    fig.tight_layout(); fig.savefig(OUT + 'course%d/gameplay_plot.png' % k); plt.close(fig); print('plot', k)

if __name__ == '__main__':
    for k in ([int(a) for a in sys.argv[1:]] or range(5)): plot(k)

"""rtg4.c = rtg2.c with its last line replaced by rtg4_tail.c (lm4_light), and a header that says why."""
import os
H = os.path.dirname(os.path.abspath(__file__)); s = open(os.path.join(H, 'rtg2.c')).read(); tail = 'EXPORT int lm2_threads(void) { return omp_get_max_threads(); }'
assert s.count(tail) == 1 and s.startswith('/* rtg2.c')
head = """/* rtg4.c = rtg2.c + lm4_light (rt_bake_game4.py, 2026-10-13): WHERE on its polygon a texel is lit from.
   lm2_light took the texel's own point, 2 cm off the surface. Three things came of that (owner's screenshots, 2026-10-13):
     - a texel on a polygon's EDGE lies exactly in the plane of the wall that stands on that edge; 2 cm up it was behind any wall that leans
       over the road at all, in full sun: a lit strip along the foot of such a wall, inside the wall's own shadow ;
     - where the ground goes on behind a wall, the texel behind it is in the sun and the game blends it into the one in front ;
     - one point per texel is 0 or 1: blended by the game, a slanted shadow edge came out in steps.
   lm4_light: the point is kept a few centimetres inside its polygon's edges ; short feelers along the surface (one texel) find what crosses
   it, and a point that stands BEHIND something whose back the road never sees is moved in front of it ; the sun is asked from points spread
   over the texel's own square (those cut off from the texel's point by something are not used).
   (made by mk_rtg4.py from rtg2.c and rtg4_tail.c)
   ----- the text of rtg2.c:
"""
open(os.path.join(H, 'rtg4.c'), 'w', newline='\n').write(head + s[2:].replace(tail, open(os.path.join(H, 'rtg4_tail.c')).read()))
print('rtg4.c written')

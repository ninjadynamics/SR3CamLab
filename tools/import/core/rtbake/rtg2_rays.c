/* rtg2_rays.c - the ray walks for rt_bake_game2_fast.py: rays.c + fastlm_rays.c (unchanged copies of the importer's, included here) and
   one more walk.  Compiled with the flags rays.py gives rays.c (-O3 -march=native), so a ray against a box / a triangle is computed
   exactly as in rays.dll.

     rx_any_from   is a triangle hit at tmin or FARTHER (and nearer than tlim)?  Stops at the first one.  As rx_any of fastlm_rays.c
                   (its point 2: exact, whatever the tree and the order), with the one extra condition t >= tmin.  */
#include "fastlm_rays.c"

EXPORT int rx_any_from(void *h, const double *o, const double *d, double tmin, double tlim) {
    const RX *X = (const RX *)h; const Scene *s = X->s; if (s->ntri == 0) return 0;
    RX_INV
    int stack[RX_STACK], sp = 0; double se[RX_STACK]; stack[sp] = 0; se[sp++] = 0.0;
    while (sp) {
        int r = stack[--sp];
        if (r < 0) {
            const Node *n = &X->x[~r];
            for (int i = n->first; i < n->first + n->count; i++) {
                RX_TRI(i)
                if (t <= 1e-9 || t >= tlim || t < tmin) continue;
                if (s->tmat && through_hole(s, s->orig[i], b1, b2)) continue;
                return 1;
            }
        } else { double e[4]; const QNode *Q = &X->q[r]; int m = box4(Q, o, inv, tlim, e); RX_PUSH(Q, m, e) }
    }
    return 0;
}

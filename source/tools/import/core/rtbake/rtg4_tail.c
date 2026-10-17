
/* ------------------------------------------------------------------ lm4_light */
typedef struct { const double *Q; double n1[3], n2[3]; int tri; double ma, mb; } poly_t;

static inline void poly_make(const double *Q, int tri, double ma, double mb, double side, poly_t *p)
{
    double e1[3], e2[3], e3[3];
    for (int a = 0; a < 3; a++) { e1[a] = Q[3 + a] - Q[a]; e2[a] = Q[6 + a] - Q[a]; e3[a] = Q[9 + a] - Q[a]; }
    cross3(e1, e2, p->n1); cross3(e2, e3, p->n2); double l1 = NORM3(p->n1), l2 = NORM3(p->n2);
    if (l1 > 1e-9) { for (int a = 0; a < 3; a++) p->n1[a] *= side / l1; }
    else if (l2 > 1e-9) { for (int a = 0; a < 3; a++) p->n1[a] = p->n2[a] * side / l2; }
    else { p->n1[0] = 0.0; p->n1[1] = side; p->n1[2] = 0.0; }
    if (l2 > 1e-9 && !tri) { for (int a = 0; a < 3; a++) p->n2[a] *= side / l2; } else { for (int a = 0; a < 3; a++) p->n2[a] = p->n1[a]; }
    p->Q = Q; p->tri = tri; p->ma = ma; p->mb = mb;
}
/* the place of grid point (a, b) on the two triangles the game draws (corners 1 0 2 and 0 2 3) and the normal of the one it lies on */
static inline void poly_pos(const poly_t *p, double a, double b, double *x, const double **n)
{
    const double *Q = p->Q;
    if (b <= a) { for (int k = 0; k < 3; k++) x[k] = Q[k] + (a - b) * (Q[3 + k] - Q[k]) + b * (Q[6 + k] - Q[k]); *n = p->n1; }
    else        { for (int k = 0; k < 3; k++) x[k] = Q[k] + a * (Q[6 + k] - Q[k]) + (b - a) * (Q[9 + k] - Q[k]); *n = p->n2; }
}
/* into the polygon: mirrored at its edges, kept the margin away from them ; a three-corner polygon is the half b <= a */
static inline void poly_clamp(const poly_t *p, double *a, double *b)
{
    double A = *a, B = *b;
    if (A < 0.0) A = -A;
    if (A > 1.0) A = 2.0 - A;
    if (B < 0.0) B = -B;
    if (B > 1.0) B = 2.0 - B;
    if (p->tri && B > A) { double t = A; A = B; B = t; }
    if (A < p->ma) A = p->ma;
    if (A > 1.0 - p->ma) A = 1.0 - p->ma;
    if (B < p->mb) B = p->mb;
    if (B > 1.0 - p->mb) B = 1.0 - p->mb;
    if (p->tri) {
        double md = 0.5 * (p->ma + p->mb);
        if (A - B < md) {
            double e = 0.5 * (md - (A - B)); A += e; B -= e;
            if (A > 1.0 - p->ma) A = 1.0 - p->ma;
            if (B < p->mb) B = p->mb;
        }
    }
    *a = A; *b = B;
}
/* what stands between two points just off the surface: the nearest triangle that is not a layer lying along the surface (-1: nothing).
   -> *t its distance, d[3] the unit direction, *L the whole length */
static inline int between(const ctx *c, const double *o, const double *e, const double *nsrc, double *t, double *d, double *L, cnt_t *k)
{
    double v[3] = { e[0] - o[0], e[1] - o[1], e[2] - o[2] }, len = NORM3(v); *L = len; *t = len;
    if (!(len > 1e-6)) return -1;
    d[0] = v[0] / len; d[1] = v[1] / len; d[2] = v[2] / len;
    double tt; int h = near1(c, o, d, len, &tt, k);
    if (h >= 0 && !(tt < len)) h = -1;
    for (int rnd = 0; rnd < 3 && h >= 0; rnd++) {
        const double *tn = c->TN + 3 * (size_t)h;
        if (!(fabs(DOT3(tn, nsrc)) > 0.9)) break;
        double s = tt + 0.003;
        if (!(s < len)) { h = -1; break; }
        double o2[3] = { o[0] + d[0] * s, o[1] + d[1] * s, o[2] + d[2] * s }, t2; int h2 = near1(c, o2, d, len - s, &t2, k);
        if (h2 >= 0 && !(t2 < len - s)) h2 = -1;
        h = h2; tt = s + t2;
    }
    if (h >= 0) *t = tt;
    return h;
}

/* n texels: pidx[n] their polygon, iu / iv[n] their place in its grid ; per polygon PQ[12] corners, PNU / PNV grid size, PTRI (corners 2 and 3
   are one place), PM[2] margins in grid units ; side +1 = the winding side, -1 the other ; TONE[nt] = 1: the back of that scene triangle is
   never looked at ; FOOT[nsd * 2] where in the texel's square (-0.5 .. 0.5) each sun ray starts ; inreach = the feelers' length in texels.
   -> V, sky, back[n * 3] as lm2_light, NOUT[n * 3] the normal at the point used ; stats[5] = rays, handed to cast_one, quick sun answers,
      texels moved in front of something, texels with something crossing their square */
EXPORT void lm4_light(void *sc, int mode, i64 n, const int *pidx, const int *iu, const int *iv,
                      const double *PQ, const int *PNU, const int *PNV, const unsigned char *PTRI, const double *PM, double side,
                      const double *CA, const double *SA, int turns,
                      const double *TN, const double *TNS, const double *TND, const int *TMA, const unsigned char *TONE, const double *alb,
                      const double *SUN, const double *SD, int nsd, const double *FOOT, const double *HEMI, int ks, double lift, double inreach,
                      double *V, double *sky, double *back, double *NOUT, i64 *stats)
{
    ctx c = { sc, mode, TN, TNS, TND, TMA, alb, SUN, SD, HEMI, nsd, ks, turns, lift }; i64 nray = 0, nfell = 0, nquick = 0, nmoved = 0, ncross = 0;
    static const double PR[8][2] = { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 }, { 0.7, 0.7 }, { -0.7, 0.7 }, { 0.7, -0.7 }, { -0.7, -0.7 } };
    #pragma omp parallel for schedule(dynamic, 64) reduction(+: nray, nfell, nquick, nmoved, ncross)
    for (i64 i = 0; i < n; i++) {
        cnt_t k = { 0, 0, 0 }; size_t pi = (size_t)pidx[i]; poly_t p; poly_make(PQ + 12 * pi, PTRI[pi], PM[2 * pi], PM[2 * pi + 1], side, &p);
        double da = 1.0 / (double)(PNU[pi] - 1), db = 1.0 / (double)(PNV[pi] - 1), a0 = iu[i] * da, b0 = iv[i] * db, ar = a0, br = b0;
        poly_clamp(&p, &ar, &br);
        double xr[3], orr[3]; const double *nr; poly_pos(&p, ar, br, xr, &nr);
        for (int a = 0; a < 3; a++) orr[a] = xr[a] + nr[a] * lift;
        /* feelers: one texel along the surface in eight directions */
        int crossed = 0, moved = 0; double best = 1e30, am = ar, bm = br;
        for (int q = 0; q < 8; q++) {
            double at = ar + PR[q][0] * da * inreach, bt = br + PR[q][1] * db * inreach, xt[3], ot[3], t, d[3], L; const double *nt;
            poly_clamp(&p, &at, &bt); poly_pos(&p, at, bt, xt, &nt);
            for (int a = 0; a < 3; a++) ot[a] = xt[a] + nt[a] * lift;
            int h = between(&c, orr, ot, nr, &t, d, &L, &k);
            if (h < 0) continue;
            crossed = 1;
            if (TONE[h] && DOT3(d, TN + 3 * (size_t)h) > 0.0 && t < best) {
                double s = (t + 0.05) / L;
                if (s > 1.0) s = 1.0;
                best = t; am = ar + (at - ar) * s; bm = br + (bt - br) * s; moved = 1;
            }
        }
        if (moved) {
            ar = am; br = bm; poly_clamp(&p, &ar, &br); poly_pos(&p, ar, br, xr, &nr);
            for (int a = 0; a < 3; a++) orr[a] = xr[a] + nr[a] * lift;
            a0 = ar; b0 = br; nmoved++;
        }
        ncross += crossed;
        NOUT[3 * i] = nr[0]; NOUT[3 * i + 1] = nr[1]; NOUT[3 * i + 2] = nr[2];
        /* the sun, from points spread over the texel's square */
        int open = 0;
        for (int j = 0; j < nsd; j++) {
            double aj = a0 + FOOT[2 * j] * da, bj = b0 + FOOT[2 * j + 1] * db, xj[3], oj[3]; const double *nj;
            poly_clamp(&p, &aj, &bj); poly_pos(&p, aj, bj, xj, &nj);
            for (int a = 0; a < 3; a++) oj[a] = xj[a] + nj[a] * lift;
            if (crossed && j) {
                double t, d[3], L;
                if (between(&c, orr, oj, nr, &t, d, &L, &k) >= 0) { for (int a = 0; a < 3; a++) oj[a] = orr[a]; nj = nr; }
            }
            if (!(DOT3(nj, SUN) > 0.02)) continue;
            const double *dd = SD + 3 * j; double oo[3] = { oj[0] + dd[0] * lift, oj[1] + dd[1] * lift, oj[2] + dd[2] * lift };
            open += !hidden(&c, oo, dd, nj, &k);
        }
        V[i] = (double)open / (double)nsd;
        /* the sky and what comes back, from the texel's point (as lm2_light) */
        const double *nn = nr; const double *o = orr;
        double ax[3] = { 0.0, 1.0, 0.0 };
        if (!(fabs(nn[1]) < 0.9)) { ax[0] = 1.0; ax[1] = 0.0; }
        double t[3], b[3]; cross3(nn, ax, t); double l = NORM3(t);
        if (!(l > 1e-12)) l = 1e-12;
        t[0] /= l; t[1] /= l; t[2] /= l; cross3(nn, t, b);
        double skyacc = 0.0, bacc[3] = { 0.0, 0.0, 0.0 };
        for (int turn = 0; turn < turns; turn++) {
            double ca = CA[i * turns + turn], sa = SA[i * turns + turn], acc[3] = { 0.0, 0.0, 0.0 }; int opn = 0;
            for (int j = 0; j < ks; j++) {
                const double *H = HEMI + 3 * j; double hx = H[0] * ca - H[1] * sa, hy = H[0] * sa + H[1] * ca, d[3], oo[3], dist;
                for (int a = 0; a < 3; a++) { d[a] = (t[a] * hx + b[a] * hy) + nn[a] * H[2]; oo[a] = o[a] + d[a] * lift; }
                int hit = chain(&c, oo, d, nn, 1e9, &dist, &k);
                if (hit < 0) { opn++; continue; }
                const double *tn = TN + 3 * (size_t)hit; int keep = DOT3(tn, d) < 0; double sg = keep ? 1.0 : -1.0, hn[3] = { keep ? tn[0] : -tn[0], keep ? tn[1] : -tn[1], keep ? tn[2] : -tn[2] };
                double litv = 0.34 * (0.5 + 0.5 * clip01(hn[1]));
                if (sg * TNS[hit] > 0.05) {
                    double o2[3];
                    for (int a = 0; a < 3; a++) { double loc = oo[a] + d[a] * dist; o2[a] = (loc + hn[a] * lift) + SUN[a] * lift; }
                    if (!hidden(&c, o2, SUN, hn, &k)) litv += 0.66 * clip01((sg * TND[hit] + 0.2) / 0.907);
                }
                if (!(litv < 1.0)) litv = 1.0;
                const double *al = alb + 3 * (size_t)TMA[hit]; acc[0] += al[0] * litv; acc[1] += al[1] * litv; acc[2] += al[2] * litv;
            }
            skyacc += (double)opn / (double)ks; bacc[0] += acc[0] / ks; bacc[1] += acc[1] / ks; bacc[2] += acc[2] / ks;
        }
        sky[i] = skyacc / turns; back[3 * i] = bacc[0] / turns; back[3 * i + 1] = bacc[1] / turns; back[3 * i + 2] = bacc[2] / turns;
        nray += k.rays; nfell += k.fell; nquick += k.quick;
    }
    if (stats) { stats[0] = nray; stats[1] = nfell; stats[2] = nquick; stats[3] = nmoved; stats[4] = ncross; }
}

EXPORT int lm2_threads(void) { return omp_get_max_threads(); }

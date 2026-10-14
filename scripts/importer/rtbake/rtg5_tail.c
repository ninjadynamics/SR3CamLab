
/* ------------------------------------------------------------------ lm5_light = lm4_light for rectangles that hold SEVERAL polygons
   (2026-10-13, rounding with baked light: the pieces a rounded polygon is cut into share its light-map rectangle - round1995.PATCH).
   A rectangle is either one polygon, lit exactly as lm4_light lights it, or a lattice of pn x pn cells of the square 0..1 x 0..1, each cell
   one four-corner piece or two three-corner pieces (cut along the cell's diagonal from its low corner), every piece with its own corners in
   space and its own places AB in the square. A point (a, b) of the rectangle lies on the piece of its cell; the piece's two drawn triangles
   (corners 1 0 2 and 0 2 3 of the PIECE, in the order it is written) give the place and the normal. */
typedef struct {
    const double *Q; double n1[3], n2[3]; int tri; double ma, mb, side;
    int pn, first; const int *cell; const double *PQ, *PAB; const unsigned char *PT;
} rect_t;

static inline void unit3(double *n, double side)
{
    double l = NORM3(n);
    if (l > 1e-12) { n[0] *= side / l; n[1] *= side / l; n[2] *= side / l; } else { n[0] = 0.0; n[1] = side; n[2] = 0.0; }
}
static inline void rect_make(const double *PQ, const double *PAB, const unsigned char *PT, int first, int pn, const int *cell, int tri, double ma, double mb, double side, rect_t *p)
{
    const double *Q = PQ + 12 * (size_t)first; double e1[3], e2[3], e3[3];
    for (int a = 0; a < 3; a++) { e1[a] = Q[3 + a] - Q[a]; e2[a] = Q[6 + a] - Q[a]; e3[a] = Q[9 + a] - Q[a]; }
    cross3(e1, e2, p->n1); cross3(e2, e3, p->n2); double l1 = NORM3(p->n1), l2 = NORM3(p->n2);
    if (l1 > 1e-9) { for (int a = 0; a < 3; a++) p->n1[a] *= side / l1; }
    else if (l2 > 1e-9) { for (int a = 0; a < 3; a++) p->n1[a] = p->n2[a] * side / l2; }
    else { p->n1[0] = 0.0; p->n1[1] = side; p->n1[2] = 0.0; }
    if (l2 > 1e-9 && !tri) { for (int a = 0; a < 3; a++) p->n2[a] *= side / l2; } else { for (int a = 0; a < 3; a++) p->n2[a] = p->n1[a]; }
    p->Q = Q; p->tri = tri; p->ma = ma; p->mb = mb; p->side = side; p->pn = pn; p->first = first; p->cell = cell; p->PQ = PQ; p->PAB = PAB; p->PT = PT;
}
/* the place of (a, b) and the normal there (written into n[3]) ; *piece = the polygon it lies on */
static inline void rect_pos(const rect_t *p, double a, double b, double *x, double *n, int *piece)
{
    if (!p->pn) {
        const double *Q = p->Q, *m;
        if (b <= a) { for (int k = 0; k < 3; k++) x[k] = Q[k] + (a - b) * (Q[3 + k] - Q[k]) + b * (Q[6 + k] - Q[k]); m = p->n1; }
        else        { for (int k = 0; k < 3; k++) x[k] = Q[k] + a * (Q[6 + k] - Q[k]) + (b - a) * (Q[9 + k] - Q[k]); m = p->n2; }
        n[0] = m[0]; n[1] = m[1]; n[2] = m[2]; *piece = p->first; return;
    }
    int pn = p->pn, i = (int)(a * pn), j = (int)(b * pn);
    if (i < 0) i = 0;
    if (i > pn - 1) i = pn - 1;
    if (j < 0) j = 0;
    if (j > pn - 1) j = pn - 1;
    int half = (b * pn - j) <= (a * pn - i) ? 0 : 1, pc = p->cell[(j * pn + i) * 2 + half];
    if (pc < 0) pc = p->cell[(j * pn + i) * 2 + 1 - half];
    if (pc < 0) pc = p->first;
    const double *Q = p->PQ + 12 * (size_t)pc, *A = p->PAB + 8 * (size_t)pc; double da = a - A[0], db = b - A[1], e1[3], e2[3];
    *piece = pc;
    if (p->PT[pc]) {                                                    /* three corners: 0 1 2 */
        double e1a = A[2] - A[0], e1b = A[3] - A[1], e2a = A[4] - A[0], e2b = A[5] - A[1], det = e1a * e2b - e1b * e2a, u = 0.0, w = 0.0;
        if (fabs(det) > 1e-14) { u = (da * e2b - db * e2a) / det; w = (e1a * db - e1b * da) / det; }
        if (u < 0.0) u = 0.0;
        if (w < 0.0) w = 0.0;
        if (u + w > 1.0) { double k = u + w; u /= k; w /= k; }
        for (int k = 0; k < 3; k++) { e1[k] = Q[3 + k] - Q[k]; e2[k] = Q[6 + k] - Q[k]; x[k] = Q[k] + u * e1[k] + w * e2[k]; }
        cross3(e1, e2, n); unit3(n, p->side); return;
    }
    double e1a = A[2] - A[0], e1b = A[3] - A[1], e3a = A[6] - A[0], e3b = A[7] - A[1], l1 = e1a * e1a + e1b * e1b, l3 = e3a * e3a + e3b * e3b;
    double s = l1 > 1e-18 ? (da * e1a + db * e1b) / l1 : 0.0, t = l3 > 1e-18 ? (da * e3a + db * e3b) / l3 : 0.0;
    if (s < 0.0) s = 0.0;
    if (s > 1.0) s = 1.0;
    if (t < 0.0) t = 0.0;
    if (t > 1.0) t = 1.0;
    if (t <= s) {
        for (int k = 0; k < 3; k++) { e1[k] = Q[3 + k] - Q[k]; e2[k] = Q[6 + k] - Q[k]; x[k] = Q[k] + (s - t) * e1[k] + t * e2[k]; }
        cross3(e1, e2, n);
        if (!(NORM3(n) > 1e-12)) { for (int k = 0; k < 3; k++) e1[k] = Q[9 + k] - Q[k]; cross3(e2, e1, n); }
    } else {
        for (int k = 0; k < 3; k++) { e1[k] = Q[6 + k] - Q[k]; e2[k] = Q[9 + k] - Q[k]; x[k] = Q[k] + s * e1[k] + (t - s) * e2[k]; }
        cross3(e1, e2, n);
        if (!(NORM3(n) > 1e-12)) { for (int k = 0; k < 3; k++) e2[k] = Q[3 + k] - Q[k]; cross3(e2, e1, n); }
    }
    unit3(n, p->side);
}
static inline void rect_clamp(const rect_t *p, double *a, double *b)
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

/* n texels: ridx[n] their rectangle, iu / iv[n] their place in its grid.
   Per rectangle: RNU / RNV grid size, RTRI (only the half b <= a is drawn), RM[2] margins, RPN lattice size (0 = one polygon), ROFF where its
   cells start in CELL (2 numbers a cell: the piece of the half b' <= a', the piece of the other), RFIRST its first piece.
   Per piece: PQ[12] corners, PAB[8] their places in the rectangle's square, PT (corners 2 and 3 are one place).
   -> as lm4_light, and POUT[n] the piece each texel's point lies on. stats[5] as lm4_light. */
EXPORT void lm5_light(void *sc, int mode, i64 n, const int *ridx, const int *iu, const int *iv,
                      const int *RNU, const int *RNV, const unsigned char *RTRI, const double *RM, const int *RPN, const i64 *ROFF, const int *RFIRST, const int *CELL,
                      const double *PQ, const double *PAB, const unsigned char *PT, double side,
                      const double *CA, const double *SA, int turns,
                      const double *TN, const double *TNS, const double *TND, const int *TMA, const unsigned char *TONE, const double *alb,
                      const double *SUN, const double *SD, int nsd, const double *FOOT, const double *HEMI, int ks, double lift, double inreach,
                      double *V, double *sky, double *back, double *NOUT, int *POUT, i64 *stats)
{
    ctx c = { sc, mode, TN, TNS, TND, TMA, alb, SUN, SD, HEMI, nsd, ks, turns, lift }; i64 nray = 0, nfell = 0, nquick = 0, nmoved = 0, ncross = 0;
    static const double PR[8][2] = { { 1, 0 }, { -1, 0 }, { 0, 1 }, { 0, -1 }, { 0.7, 0.7 }, { -0.7, 0.7 }, { 0.7, -0.7 }, { -0.7, -0.7 } };
    #pragma omp parallel for schedule(dynamic, 64) reduction(+: nray, nfell, nquick, nmoved, ncross)
    for (i64 i = 0; i < n; i++) {
        cnt_t k = { 0, 0, 0 }; size_t ri = (size_t)ridx[i]; rect_t p;
        rect_make(PQ, PAB, PT, RFIRST[ri], RPN[ri], CELL + ROFF[ri], RTRI[ri], RM[2 * ri], RM[2 * ri + 1], side, &p);
        double da = 1.0 / (double)(RNU[ri] - 1), db = 1.0 / (double)(RNV[ri] - 1), a0 = iu[i] * da, b0 = iv[i] * db, ar = a0, br = b0;
        rect_clamp(&p, &ar, &br);
        double xr[3], orr[3], nr[3]; int pcr, pcx; rect_pos(&p, ar, br, xr, nr, &pcr);
        for (int a = 0; a < 3; a++) orr[a] = xr[a] + nr[a] * lift;
        /* feelers: one texel along the surface in eight directions */
        int crossed = 0, moved = 0; double best = 1e30, am = ar, bm = br;
        for (int q = 0; q < 8; q++) {
            double at = ar + PR[q][0] * da * inreach, bt = br + PR[q][1] * db * inreach, xt[3], ot[3], nt[3], t, d[3], L;
            rect_clamp(&p, &at, &bt); rect_pos(&p, at, bt, xt, nt, &pcx);
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
            ar = am; br = bm; rect_clamp(&p, &ar, &br); rect_pos(&p, ar, br, xr, nr, &pcr);
            for (int a = 0; a < 3; a++) orr[a] = xr[a] + nr[a] * lift;
            a0 = ar; b0 = br; nmoved++;
        }
        ncross += crossed;
        NOUT[3 * i] = nr[0]; NOUT[3 * i + 1] = nr[1]; NOUT[3 * i + 2] = nr[2]; POUT[i] = pcr;
        /* the sun, from points spread over the texel's square */
        int open = 0;
        for (int j = 0; j < nsd; j++) {
            double aj = a0 + FOOT[2 * j] * da, bj = b0 + FOOT[2 * j + 1] * db, xj[3], oj[3], nj[3];
            rect_clamp(&p, &aj, &bj); rect_pos(&p, aj, bj, xj, nj, &pcx);
            for (int a = 0; a < 3; a++) oj[a] = xj[a] + nj[a] * lift;
            if (crossed && j) {
                double t, d[3], L;
                if (between(&c, orr, oj, nr, &t, d, &L, &k) >= 0) { for (int a = 0; a < 3; a++) { oj[a] = orr[a]; nj[a] = nr[a]; } }
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

/* ------------------------------------------------------------------ the cars' pages (2026-10-13: was a numpy loop per page, 20 s of a 131 s bake)
   n plan points XZ[n * 2] ; C3[m * 3] the road's middle near the page. The nearest of them (the first of equals, as numpy's argmin) gives the
   height; a point nearer than `reach` asks the sun (nsd directions SD) and the sky (nh directions HC) from `up` above the road there, every ray
   starting `off` along its own direction. A ray counts as free when rx_any finds nothing (the same test as "rx_near found no hit").
   -> G[n] the share of sun rays that are free (1 where not asked), R[n] the share of sky rays that are stopped (0 where not asked), ASK[n] ;
      returns how many points were asked. The arithmetic is the numpy code's, in its order. */
extern int rx_any(void *h, const double *o, const double *d, double tlim);
EXPORT i64 lm5_cars(void *sc, i64 n, const double *XZ, const double *C3, int m, double reach, double up, const double *SD, int nsd, const double *HC, int nh, double off,
                    double *G, double *R, unsigned char *ASK)
{
    i64 asked = 0;
    #pragma omp parallel for schedule(dynamic, 256) reduction(+: asked)
    for (i64 i = 0; i < n; i++) {
        double x = XZ[2 * i], z = XZ[2 * i + 1], best = 0.0; int j = -1;
        for (int k = 0; k < m; k++) {
            double dx = x - C3[3 * k], dz = z - C3[3 * k + 2], d2 = dx * dx + dz * dz;
            if (j < 0 || d2 < best) { best = d2; j = k; }
        }
        G[i] = 1.0; R[i] = 0.0; ASK[i] = 0;
        if (j < 0 || !(sqrt(best) < reach)) continue;
        double P[3] = { x, C3[3 * j + 1] + up, z }; int opn = 0, sky = 0;
        for (int k = 0; k < nsd; k++) { const double *d = SD + 3 * k; double o[3] = { P[0] + d[0] * off, P[1] + d[1] * off, P[2] + d[2] * off }; opn += !rx_any(sc, o, d, 1e9); }
        for (int k = 0; k < nh; k++) { const double *d = HC + 3 * k; double o[3] = { P[0] + d[0] * off, P[1] + d[1] * off, P[2] + d[2] * off }; sky += !rx_any(sc, o, d, 1e9); }
        G[i] = (double)opn / (double)nsd; R[i] = 1.0 - (double)sky / (double)nh; ASK[i] = 1; asked++;
    }
    return asked;
}

/* ------------------------------------------------------------------ how far a point is from the road's middle, in plan (2026-10-13)
   X[n * 3] points (x at 0, z at 2) ; C[m * 2] the middle's points (x, z). out[i] = min(out[i], sqrt(the smallest dx^2 + dz^2)): what
   np.minimum(out, np.sqrt(((X[:, None, [0, 2]] - C[None]) ** 2).sum(2).min(1))) gives - one sum of two squares per pair, the smallest, its root. */
EXPORT void lm5_mind(const double *X, i64 n, const double *C, i64 m, double *out)
{
    #pragma omp parallel for schedule(static)
    for (i64 i = 0; i < n; i++) {
        double x = X[3 * i], z = X[3 * i + 2], best = INFINITY;
        for (i64 k = 0; k < m; k++) { double dx = x - C[2 * k], dz = z - C[2 * k + 1], d2 = dx * dx + dz * dz; if (d2 < best) best = d2; }
        double d = sqrt(best);
        if (d < out[i]) out[i] = d;
    }
}


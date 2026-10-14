/* fastseal.c - which corners MAY lie on the inside of which edge, for seal1995.py, on every core (fastseal.py loads it; gcc on first use).
   seal1995 walked every edge of the built meshes in Python and measured, with numpy, every corner whose x lies within the edge's x range: 390 000
   edges, 6 s of an R1 build. Nearly none of those corners is anywhere near the edge. This file only THROWS AWAY the ones that are clearly not on
   it; what is left (a few thousand corners) is measured by seal1995's own lines as before, so every joint and every place along an edge is
   decided by the same expressions.
   A corner c is kept for edge (a, b) when it is neither end, its place along the edge t = (c - a) . (b - a) / |b - a|^2 lies between 0.99 e and
   1 - 0.99 e (e = tol / |b - a| ; seal1995 asks e < t < 1 - e) and its distance from the line is under 1.01 tol (seal1995: under tol). The
   margins of 1 % are a million times any rounding of these numbers.
     U[nu * 3] the places ; E[ne * 2] the edges ; xo[nx] corners in the order of their x ; i0 / i1[ne] the part of xo to look at per edge
     (seal1995's own searchsorted) ; an edge with i1 - i0 <= 2 or shorter than 2 tol x 0.999 has none.
   seal_count -> cnt[ne] ; seal_fill writes them at off[e] (the running sum of cnt), in the order of xo. */
#include <math.h>
#include <omp.h>
#define EXPORT __declspec(dllexport)
typedef long long i64;

static inline i64 scan(const double *U, const i64 *E, const i64 *xo, const i64 *i0, const i64 *i1, i64 e, double tol, i64 *out)
{
    i64 a = E[2 * e], b = E[2 * e + 1], n = 0;
    if (i1[e] - i0[e] <= 2) return 0;
    const double *A = U + 3 * a, *B = U + 3 * b; double ab[3] = { B[0] - A[0], B[1] - A[1], B[2] - A[2] }, L2 = ab[0] * ab[0] + ab[1] * ab[1] + ab[2] * ab[2];
    if (L2 < 4.0 * tol * tol * 0.999) return 0;
    double ee = 0.99 * tol / sqrt(L2), lim = 1.01 * tol * 1.01 * tol;
    for (i64 k = i0[e]; k < i1[e]; k++) {
        i64 c = xo[k]; if (c == a || c == b) continue;
        const double *C = U + 3 * c; double q[3] = { C[0] - A[0], C[1] - A[1], C[2] - A[2] }, t = (q[0] * ab[0] + q[1] * ab[1] + q[2] * ab[2]) / L2;
        if (!(t > ee && t < 1.0 - ee)) continue;
        double r[3] = { q[0] - t * ab[0], q[1] - t * ab[1], q[2] - t * ab[2] };
        if (!(r[0] * r[0] + r[1] * r[1] + r[2] * r[2] < lim)) continue;
        if (out) out[n] = c;
        n++;
    }
    return n;
}
EXPORT void seal_count(const double *U, const i64 *E, i64 ne, const i64 *xo, const i64 *i0, const i64 *i1, double tol, i64 *cnt)
{
    #pragma omp parallel for schedule(dynamic, 1024)
    for (i64 e = 0; e < ne; e++) cnt[e] = scan(U, E, xo, i0, i1, e, tol, 0);
}
EXPORT void seal_fill(const double *U, const i64 *E, i64 ne, const i64 *xo, const i64 *i0, const i64 *i1, double tol, const i64 *cnt, const i64 *off, i64 *out)
{
    #pragma omp parallel for schedule(dynamic, 1024)
    for (i64 e = 0; e < ne; e++) if (cnt[e]) scan(U, E, xo, i0, i1, e, tol, out + off[e]);
}

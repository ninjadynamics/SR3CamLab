"""numpy's float arithmetic, step for step, for the code that no longer imports numpy (kb 31): the same bits as numpy 1.24.3 with the
OpenBLAS 0.3.21 it ships, on the author's PC.

    pwsum(v)          np.add.reduce of a 1-D float64 array (np.sum, the sum in np.mean of a contiguous or strided 1-D array)
    ddot(x, y, yoff)  np.dot of two float64 vectors; yoff = y's place in memory is 8 bytes off 16 (else 0)

OpenBLAS picks its kernels by CPU. It does not know the author's CPU and runs its PRESCOTT (SSE2) kernels (openblas_get_corename64_ in
numpy's libopenblas64_ DLL says so; MAX_THREADS 24). Its ddot, fitted on 9,600 random cases (n 1 .. 40, every alignment of x and y) and
800 long ones (n up to 2,000), 100%: four 2-lane accumulators, no fused multiply-add;
  - y 8 bytes off 16: the first product goes into the low lane of accumulator 0 (y is aligned from there on)
  - then 4 elements a round: two pairs, round robin over the four accumulators (pair k into accumulator k mod 4)
  - a pair left over goes into accumulator 0, a single product left over into its low lane
  - each lane (a0 + a1) + (a2 + a3), then low + high; numpy adds the result to 0.
np.convolve(a, k, 'valid') is that ddot per output (numpy's correlate with a fresh, aligned copy of k[::-1]): 4,982 of 4,982.
On a PC whose CPU OpenBLAS knows (other kernels, fused multiply-adds) numpy itself gives other last bits; this module keeps the author's
numbers, which are the ones the shipped builds were checked against."""

def pwsum(v):
    """numpy's pairwise sum: below 8 one after the other; up to 128 eight running sums added ((r0 + r1) + (r2 + r3)) + ((r4 + r5) + (r6 + r7)),
    then the rest one by one; above that the two halves, cut at a multiple of 8; the result added to 0"""
    def pw(v):
        n = len(v)
        if n < 8:
            s = 0.0
            for x in v: s += x
            return s
        if n <= 128:
            r = list(v[:8]); e = n - n % 8
            for i in range(8, e, 8):
                for j in range(8): r[j] += v[i + j]
            s = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]))
            for x in v[e:]: s += x
            return s
        h = n // 2; h -= h % 8
        return pw(v[:h]) + pw(v[h:])
    return 0.0 + pw(v)

def ddot(x, y, yoff=0):
    """np.dot(x, y) of float64 vectors (OpenBLAS Prescott ddot, see above); yoff: 1 when y lies 8 bytes off a 16-byte boundary"""
    acc = [[0.0, 0.0] for _ in range(4)]; i = 0; n = len(x)
    if yoff and n: acc[0][0] += x[0] * y[0]; i = 1
    npm = ((n - i) // 4) * 2; j = 0
    while j < npm: a = acc[j % 4]; a[0] += x[i] * y[i]; a[1] += x[i + 1] * y[i + 1]; i += 2; j += 1
    if n - i >= 2: a = acc[0]; a[0] += x[i] * y[i]; a[1] += x[i + 1] * y[i + 1]; i += 2
    if i < n: acc[0][0] += x[i] * y[i]
    lo = (acc[0][0] + acc[1][0]) + (acc[2][0] + acc[3][0]); hi = (acc[0][1] + acc[1][1]) + (acc[2][1] + acc[3][1])
    return 0.0 + (lo + hi)

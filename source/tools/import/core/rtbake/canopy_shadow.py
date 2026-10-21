"""Deterministic, clustered openings through ray-only tree canopy shells.

UVs project onto a plane perpendicular to the baked sun. The near and far
intersections of one sunlight ray therefore share the same opening, instead
of two independent alpha tests closing nearly all gaps. These masks and UVs
are bake inputs only; no render mesh or game-time shader work is added.
"""
import hashlib
import math
import random
import struct

SPAN = 8.0                         # metres per repeat
SIZE = 256


def perforation_mask(size=SIZE, span=SPAN, seed=7121):
    """Return (height, width, hole bytes); True means light can pass.

    Overlapping, rotated ellipses form irregular branch-sized gaps. The
    openings span several 1/6-m lightmap texels, rather than sub-texel noise.
    Drawing wraps at the borders, making the world-scale pattern seamless.
    """
    rng = random.Random(seed)
    bits = bytearray(size * size)
    for _ in range(165):
        x, y = rng.random() * size, rng.random() * size
        rx = rng.uniform(0.14, 0.40) * size / span
        ry = rx * rng.uniform(0.50, 1.05)
        angle = rng.random() * math.tau
        co, si = math.cos(angle), math.sin(angle)
        reach = math.ceil(max(rx, ry)) + 1
        for iy in range(math.floor(y) - reach, math.floor(y) + reach + 1):
            for ix in range(math.floor(x) - reach, math.floor(x) + reach + 1):
                dx, dy = ix + 0.5 - x, iy + 0.5 - y
                a, b = co * dx + si * dy, -si * dx + co * dy
                if (a / rx) ** 2 + (b / ry) ** 2 <= 1:
                    bits[(iy % size) * size + ix % size] = 1
    return size, size, bytes(bits)


def project_uv(triangles, centre, sun, span=SPAN):
    """Flat UV list for triangles; stable per-tree phase and rotation."""
    norm = math.sqrt(sum(s * s for s in sun))
    s = tuple(x / norm for x in sun)
    cross = lambda a, b: (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
    axis = (0., 1., 0.) if abs(s[1]) < .9 else (1., 0., 0.)
    t = cross(s, axis); norm = math.sqrt(sum(x*x for x in t)); t = tuple(x/norm for x in t)
    b = cross(s, t)
    seed = int.from_bytes(hashlib.sha256(struct.pack('<3q', *(round(x*100) for x in centre))).digest()[:8], 'little')
    rng = random.Random(seed); angle = rng.random()*math.tau
    co, si = math.cos(angle), math.sin(angle)
    uaxis = tuple(co*t[k]+si*b[k] for k in range(3))
    vaxis = tuple(-si*t[k]+co*b[k] for k in range(3))
    phase = (rng.random(), rng.random())
    return [phase[j] + sum((p[k]-centre[k])*ax[k] for k in range(3))/span
            for tri in triangles for p in tri for j, ax in enumerate((uaxis,vaxis))]

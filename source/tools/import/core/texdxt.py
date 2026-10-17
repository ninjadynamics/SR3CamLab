"""DXT1 / DXT5 encode and decode (numpy) and SR3 texture chunks (kind 4) with a full mip chain, header from a template.

    blocks = dxt1(rgb) ; blocks = dxt5(rgba) ; rgba = undxt(blocks, w, h, 'DXT1' | 'DXT5')
    data = texture_data(template_chunk_data, rgba, fourcc)      # same sampler words and DDS header as the template
Endpoints: the brightest and darkest texel of a block (as build_classic._dxt1_rgb_np); alpha: min / max, 8 levels.
"""
import struct
import numpy as np


def _blocks(img):
    h, w = img.shape[:2]
    c = img.shape[2] if img.ndim == 3 else 1
    return img.reshape(h // 4, 4, w // 4, 4, c).transpose(0, 2, 1, 3, 4).reshape(-1, 16, c).astype(np.int32)


def _c565(c): return ((c[:, 0] >> 3) << 11) | ((c[:, 1] >> 2) << 5) | (c[:, 2] >> 3)


def _un565(v):
    v = v.astype(np.int32)
    return np.stack([((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31], -1)


def dxt1(rgb, four_colour=True):
    b = _blocks(rgb[..., :3]); n = len(b); ar = np.arange(n)
    lum = b.sum(2)
    hi = b[ar, lum.argmax(1)]; lo = b[ar, lum.argmin(1)]
    c0 = _c565(hi); c1 = _c565(lo)
    c0, c1 = np.maximum(c0, c1), np.minimum(c0, c1)
    same = c0 == c1
    c0 = np.where(same & (c0 < 0xFFFF), c0 + 1, c0); c1 = np.where(same & (c0 == 0xFFFF), np.maximum(c1 - 1, 0), c1)
    p0 = _un565(c0); p1 = _un565(c1)
    pal = np.stack([p0, p1, (2 * p0 + p1) // 3, (p0 + 2 * p1) // 3], 1)
    ix = ((b[:, :, None, :] - pal[:, None, :, :]) ** 2).sum(3).argmin(2)
    bits = (ix.astype(np.uint64) << (2 * np.arange(16, dtype=np.uint64))).sum(1).astype(np.uint32)
    out = np.zeros(n, np.dtype([("c0", "<u2"), ("c1", "<u2"), ("ix", "<u4")]))
    out["c0"] = c0; out["c1"] = c1; out["ix"] = bits
    return out.tobytes()


def _alpha_blocks(a):
    b = _blocks(a[..., None])[:, :, 0]; n = len(b)
    a0 = b.max(1); a1 = b.min(1)
    a0 = np.where(a0 == a1, np.minimum(a0 + 1, 255), a0); a1 = np.where(a0 == a1, a0 - 1, a1)
    lv = np.stack([a0, a1] + [((8 - k) * a0 + (k - 1) * a1) // 7 for k in range(2, 8)], 1)      # a0 > a1: 8 levels
    ix = np.abs(b[:, :, None] - lv[:, None, :]).argmin(2).astype(np.uint64)
    bits = (ix << (3 * np.arange(16, dtype=np.uint64))).sum(1)
    out = np.zeros((n, 8), np.uint8); out[:, 0] = a0; out[:, 1] = a1
    for k in range(6): out[:, 2 + k] = ((bits >> np.uint64(8 * k)) & np.uint64(255)).astype(np.uint8)
    return out


def dxt5(rgba):
    col = np.frombuffer(dxt1(rgba[..., :3]), np.uint8).reshape(-1, 8)
    return np.concatenate([_alpha_blocks(rgba[..., 3]), col], 1).tobytes()


def undxt(blob, w, h, fourcc):
    bw, bh = max(1, w // 4), max(1, h // 4); n = bw * bh
    step = 8 if fourcc == "DXT1" else 16
    a = np.frombuffer(blob[:n * step], np.uint8).reshape(n, step)
    col = a[:, -8:]
    c0 = col[:, 0].astype(np.int32) | (col[:, 1].astype(np.int32) << 8); c1 = col[:, 2].astype(np.int32) | (col[:, 3].astype(np.int32) << 8)
    p0 = _un565(c0); p1 = _un565(c1)
    four = (c0 > c1) | (fourcc != "DXT1")
    p2 = np.where(four[:, None], (2 * p0 + p1) // 3, (p0 + p1) // 2); p3 = np.where(four[:, None], (p0 + 2 * p1) // 3, 0)
    pal = np.stack([p0, p1, p2, p3], 1)
    bits = col[:, 4].astype(np.uint32) | (col[:, 5].astype(np.uint32) << 8) | (col[:, 6].astype(np.uint32) << 16) | (col[:, 7].astype(np.uint32) << 24)
    ix = (bits[:, None] >> (2 * np.arange(16, dtype=np.uint32))) & 3
    rgb = pal[np.arange(n)[:, None], ix]
    alpha = np.full((n, 16), 255, np.int32)
    if fourcc == "DXT1": alpha = np.where(((~four)[:, None]) & (ix == 3), 0, 255)
    else:
        a0 = a[:, 0].astype(np.int32); a1 = a[:, 1].astype(np.int32)
        lv8 = np.stack([a0, a1] + [((8 - k) * a0 + (k - 1) * a1) // 7 for k in range(2, 8)], 1)
        lv6 = np.stack([a0, a1] + [((6 - k) * a0 + (k - 1) * a1) // 5 for k in range(2, 6)] + [np.zeros_like(a0), np.full_like(a0, 255)], 1)
        lv = np.where((a0 > a1)[:, None], lv8, lv6)
        ab = np.zeros(n, np.uint64)
        for k in range(6): ab |= a[:, 2 + k].astype(np.uint64) << np.uint64(8 * k)
        aix = (ab[:, None] >> (3 * np.arange(16, dtype=np.uint64))) & np.uint64(7)
        alpha = lv[np.arange(n)[:, None], aix.astype(np.int64)]
    img = np.concatenate([rgb, alpha[:, :, None]], 2).reshape(bh, bw, 4, 4, 4).transpose(0, 2, 1, 3, 4).reshape(bh * 4, bw * 4, 4)
    return img[:h, :w].astype(np.uint8)


def texture_info(data):
    w = struct.unpack_from("<11I", data, 0)
    return w[2], w[3], data[48 + 80:48 + 84].decode("latin1")


def decode_texture(data):
    w, h, fc = texture_info(data)
    return undxt(data[48 + 124:], w, h, fc)


def texture_data(template, rgba, fourcc=None):
    """kind 4 data: the template's 11 words and DDS header (sizes rewritten), rgba (h, w, 4 uint8) with a full mip chain"""
    tw, th, tfc = texture_info(template)
    fourcc = fourcc or tfc
    d = bytearray(template[:48 + 124]); mips = []
    img = rgba.astype(np.float32); h, w = img.shape[:2]
    while True:
        hh, ww = img.shape[:2]
        pad = np.zeros((max(4, hh), max(4, ww), 4), np.float32); pad[:hh, :ww] = img
        if hh < 4: pad[hh:] = pad[hh - 1:hh]
        if ww < 4: pad[:, ww:] = pad[:, ww - 1:ww]
        u8 = np.clip(pad + 0.5, 0, 255).astype(np.uint8)
        mips.append(dxt1(u8) if fourcc == "DXT1" else dxt5(u8))
        if hh == 1 and ww == 1: break
        if hh > 1: img = (img[0:hh // 2 * 2:2] + img[1:hh // 2 * 2:2]) / 2
        if ww > 1: img = (img[:, 0:ww // 2 * 2:2] + img[:, 1:ww // 2 * 2:2]) / 2
    struct.pack_into("<II", d, 8, w, h)
    struct.pack_into("<III", d, 48 + 8, h, w, len(mips[0])); struct.pack_into("<I", d, 48 + 24, len(mips))
    d[48 + 80:48 + 84] = fourcc.encode()
    return bytes(d) + b"".join(mips)


def fit_texture_mips(data, maximum=2048):
    """Fit a power-of-two DXT texture by dropping oversized top mips, without reencoding.
    SR3 clamps DDS dimensions to its runtime cap without removing excess levels.
    A 4096 full chain therefore becomes an invalid 2048/13-level D3D request.
    """
    w,h,fc=texture_info(data)
    if fc not in ('DXT1','DXT5') or maximum<4:raise ValueError('Expected DXT1/DXT5 and a cap >= 4')
    if any(v<1 or v&(v-1) for v in (w,h)):raise ValueError('Expected power-of-two dimensions')
    levels=struct.unpack_from('<I',data,72)[0]
    if levels!=max(w,h).bit_length():raise ValueError('Expected a full mip chain')
    block=8 if fc=='DXT1' else 16
    def size(x,y):return max(1,(x+3)//4)*max(1,(y+3)//4)*block
    expected=172;ww,hh=w,h
    for _ in range(levels):expected+=size(ww,hh);ww=max(1,ww//2);hh=max(1,hh//2)
    if len(data)!=expected:raise ValueError('Incorrect mip payload size')
    offset=172
    while max(w,h)>maximum:
        offset+=size(w,h);w=max(1,w//2);h=max(1,h//2);levels-=1
    header=bytearray(data[:172])
    struct.pack_into('<II',header,8,w,h)
    struct.pack_into('<III',header,56,h,w,size(w,h))
    struct.pack_into('<I',header,72,levels)
    return bytes(header)+data[offset:]

"""SEGA Rally Championship (Model 2A) texel decoding from the main data ROM. See docs/kb/12_classic_textures.md
Without numpy since 2026-10-15 (kb 31): a page is bytes, one texel (0..15) a byte, row after row."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
M2 = os.path.join(__import__('common').TMP, 'm2')        # the region images of the ROM set (<work>/tmp/m2)
_HI = bytes(v >> 4 for v in range(256)); _LO = bytes(v & 15 for v in range(256))     # bytes.translate tables: a byte's upper / lower nibble
def main_data(): return open(os.path.join(M2, 'main_data.bin'), 'rb').read()
def decode(b, width_words=512):
    """u16 words (each = 2x2 texels, 4 bits) laid out width_words per double row -> (rows*2) x (width_words*2) texels as bytes, row after row.
    MAME get_texel: y even -> bits 8..15, x even -> upper nibble of the byte. With numpy (the earlier code):
        w = w16.reshape(rows, width_words); img[0::2, 0::2] = (w >> 12) & 15; img[0::2, 1::2] = (w >> 8) & 15; img[1::2, 0::2] = (w >> 4) & 15; img[1::2, 1::2] = w & 15
    here the high byte of each word gives the even row, the low byte the odd one, split into nibbles by bytes.translate (no loop per texel)."""
    n = len(b) // 2 // width_words * width_words; lo = b[0:2 * n:2]; hi = b[1:2 * n:2]; W = 2 * width_words
    ev = bytearray(2 * n); ev[0::2] = hi.translate(_HI); ev[1::2] = hi.translate(_LO)
    od = bytearray(2 * n); od[0::2] = lo.translate(_HI); od[1::2] = lo.translate(_LO)
    out = bytearray(4 * n)
    for r in range(n // width_words):
        out[2 * r * W:(2 * r + 1) * W] = ev[r * W:(r + 1) * W]; out[(2 * r + 1) * W:(2 * r + 2) * W] = od[r * W:(r + 1) * W]
    return bytes(out)
if __name__ == '__main__':
    from PIL import Image
    d = main_data(); out = os.path.join(M2, '..', 'texscan'); os.makedirs(out, exist_ok=True); x17 = bytes(min(v * 17, 255) for v in range(256))
    for off in range(0, 0x900000, 0x100000):
        img = decode(d[off:off + 0x100000])
        Image.frombytes('L', (1024, len(img) // 1024), img.translate(x17)).resize((512, 1024), Image.BILINEAR).save(os.path.join(out, 'raw_%07x.png' % off))
    print('ok')

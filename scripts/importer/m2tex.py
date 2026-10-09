"""SEGA Rally Championship (Model 2A) texel decoding from the main data ROM. See ../../12_classic_textures.md"""
import os, numpy as np
M2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tmp', 'm2')
def main_data(): return np.fromfile(os.path.join(M2, 'main_data.bin'), np.uint8)
def decode_words(w16, width_words=512):
    """u16 words (each = 2x2 texels, 4 bits) laid out width_words per double row -> uint8 image (rows*2, width_words*2)
    MAME get_texel: y even -> bits 8..15, x even -> upper nibble of the byte"""
    rows = len(w16) // width_words; w = w16[:rows * width_words].reshape(rows, width_words).astype(np.uint16)
    img = np.zeros((rows * 2, width_words * 2), np.uint8)
    img[0::2, 0::2] = (w >> 12) & 15; img[0::2, 1::2] = (w >> 8) & 15
    img[1::2, 0::2] = (w >> 4) & 15;  img[1::2, 1::2] = w & 15
    return img
if __name__ == '__main__':
    from PIL import Image
    import sys
    d = main_data(); out = os.path.join(M2, '..', 'texscan'); os.makedirs(out, exist_ok=True)
    for off in range(0, 0x900000, 0x100000):
        img = decode_words(d[off:off + 0x100000].view('<u2'))
        Image.fromarray((img * 17).astype(np.uint8)).resize((512, 1024), Image.BILINEAR).save(os.path.join(out, 'raw_%07x.png' % off))
    print('ok')

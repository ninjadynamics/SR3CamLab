"""NumPy-free image decoding for fill geometry's texture samplers."""
from PIL import Image
from npyio import Arr


def load_rgba(path):
    """Decode through Pillow to an owned writable u1(height,width,4) buffer."""
    with Image.open(path) as source:
        rgba=source.convert('RGBA')
        try:
            width,height=rgba.size
            return Arr('|u1',(height,width,4),bytearray(rgba.tobytes()))
        finally:rgba.close()


def load_alpha(path):
    """Decode the legacy opaque mask: True exactly when converted alpha >127."""
    rgba=load_rgba(path);height,width,_=rgba.shape
    return Arr('|b1',(height,width),bytearray(a>127 for a in rgba.view()[3::4]))

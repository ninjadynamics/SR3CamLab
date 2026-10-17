"""NumPy-free audio regression checks against saved NumPy 1.24.3 results.
Run: python tools/audio/test_audio_dsp.py
The hashes cover quantized PCM output, including short FIR, long FFT, stereo,
upsampling, limiting and trimming. Real-ROM comparisons are documented beside it.
"""
import array
import hashlib
import importlib.abc
import json
from pathlib import Path
import sys

class NoNumpy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'numpy' or fullname.startswith('numpy.'):
            raise RuntimeError('Audio must not import NumPy: ' + fullname)

def raw(frames, channels):
    values=array.array('h', ((i*97)%40001-20000 for i in range(frames*channels)))
    if sys.byteorder!='little':values.byteswap()
    return values.tobytes()

CASES = [
    ('short-mono', 1001, 1, 44100, 32000, 64, False),
    ('short-stereo-up', 713, 2, 11025, 44100, 32, False),
    ('same-rate', 1001, 2, 32000, 32000, 64, False),
    ('fft-mono', 3001, 1, 44100, 32000, 64, True),
    ('fft-stereo-up', 3103, 2, 32000, 44100, 64, True),
]

def main():
    sys.meta_path.insert(0,NoNumpy())
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    import audio_dsp as d
    import src_audio as sa
    import src_music as sm
    gold=json.loads(Path(__file__).with_name('audio_golden.json').read_text())
    count=0
    for name,n,ch,src,dst,taps,long in CASES:
        x=d.from_pcm(raw(n,ch),16,ch)
        y=d.resample_long(x,src,dst) if long else d.resample(x,src,dst,taps)
        assert len(y)==gold[name]['frames'],name
        assert hashlib.sha256(d.wav_bytes(y)).hexdigest()==gold[name]['sha256'],name
        count+=1
    x=d.from_pcm(raw(10001,1))
    for name,y in [('limited',sa.match_level(x,22000.,32000)[0]), ('trimmed',sa.trim(x,32000))]:
        assert hashlib.sha256(d.wav_bytes(y)).hexdigest()==gold[name]['sha256'],name
        count+=1
    for n in (1,7,8,127,128,129,4096):
        x=d.from_pcm(raw(n,1)); got=sa.loud_half_rms(x,32000)
        assert abs(got-gold['loud'][str(n)])<1e-10, ('loud',n,got)
        count+=1
    x=d.from_values([-32768.9,-2.5,-1.5,-.5,.5,1.5,2.5,32767.9])
    assert d.wav_bytes(x)==bytes.fromhex(gold['rounding'])
    for flag,want in ((False,0.),(True,0.),(2,3.)):
        x=d.from_values([3.]);d.ramp(x,flag);assert x[0]==want
    a=d.from_values([1.,2.,3.]);v=a[1:];v.owner[v.offset]=7.;assert a[1]==7.
    c=v.copy();c.owner[0]=9.;assert a[1]==7.
    assert len(d.resample(d.PCM(0),44100,32000))==0
    assert len(sa.trim(d.PCM(100),32000))==0
    for bad in (lambda:d.PCM(-1),lambda:d.PCM(1,0),lambda:d.from_pcm(b'\0'),
                lambda:d.resample(a,0,32000),lambda:d.loud(a,1,.01)):
        try:bad()
        except ValueError:pass
        else:raise AssertionError('Invalid audio parameters accepted')
    assert 'numpy' not in sys.modules
    print('%d golden audio cases + PCM bounds, views, rounding and empty-input checks PASS; NumPy absent.' % count)

if __name__=='__main__':main()

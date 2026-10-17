# Audio without NumPy

`src_audio.py` and `src_music.py` use plain Python for the ROM tables and small
lists, and `audio_dsp.c` for PCM processing. `PCM` holds interleaved doubles;
frame slices are views and operations that change samples explicitly copy.
There is no NumPy import, array ABI, or dependency on an installed NumPy binary.

The shared `tools/import/core/cbuild.py` table registers `audio_dsp`. It builds
with GCC `-O3 -fopenmp -ffp-contract=off` and the configured target (normally
`x86-64-v3`). `python tools/import/core/cbuild.py` prebuilds it with the other
helpers; otherwise the first audio operation builds it once. The source-hashed
DLL is about 184 KiB on the tested Windows toolchain. OpenMP splits independent
frames or channels, keeping each sample's arithmetic order unchanged.

The Fourier kernel in `pocketfft.h` is from NumPy 1.24.3's
`numpy/fft/_pocketfft.c`, commit `14bb214bca49b167abc375fa873466a811e62102`.
Only its Python/NumPy binding and includes were removed. Its BSD notices and
the scalar i0 coefficient attribution are in `AUDIO-LICENSE.txt` and must
accompany redistribution. This is the small standalone FFT algorithm, not the
NumPy package. Pairwise sums use 128-value blocks; short FIR convolution keeps
NumPy 1.24's baseline SSE2 einsum reduction order. The latter matters at PCM
half-integer rounding boundaries, even when the doubles differ by only 1e-11.

## Checked on 2026-10-15

Both versions processed the same local `srallyc.zip`, the same SR3 original
stream bank, and the existing `music/src/raw/src_tunes.wav` and recording log.
The recording was reused as identical input; MAME was not rerun. This change
does not alter the emulator launch or recording script. Output went into
separate ignored investigation folders, never into the game or installed audio.

| Conversion | NumPy 1.24.3 | C/Python, helper built | File comparison |
| --- | ---: | ---: | --- |
| Co-driver | 4.27 s | 0.49 s | 151 WAVs and mapping.csv identical |
| Raw voice dump | 0.10 s | 0.086 s | 63 WAVs identical |
| Music build/check | 57.16 s | 35.37 s | 4 WAVs, tunes.json, mapping.csv identical |

Times measure conversion after module imports, including ROM loading and output
writes. First-use C compilation took approximately five additional seconds;
it is excluded from the warm figures above. A preceding warm music run was
34.76 s. All recording checks passed; `info` and `plan` text matched too.

Evidence and the saved original scripts are in
`SR3-investigation/audio-numpy-baseline/` beside the repository. The manifests
contain SHA256 for all 221 output files. The comparison runner installs an
import finder that rejects any NumPy import and also verifies `sys.modules`.

Run `python -I tools/audio/test_audio_dsp.py` for the portable checks: 14 saved
NumPy golden cases cover mono/stereo, FIR/FFT, up/down sampling, limiting,
trimming and RMS block boundaries. Additional checks cover ties-to-even PCM
rounding, one-sample ramps, slice ownership, silence, empty audio and invalid
buffer/rate arguments. The fixtures contain hashes of synthetic samples only.
These checks establish identical output files for the tested inputs; intermediate
floating-point diagnostic values are not promised bit-for-bit across all CPUs.

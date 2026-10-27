"""Optional lighting-only colour; albedo and the neutral bake remain unchanged."""
import math

def rgb(value, name):
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(name + ' must contain three RGB multipliers')
    result = [float(v) for v in value]
    if any(not math.isfinite(v) or not 0.05 <= v <= 2.0 for v in result):
        raise ValueError(name + ' values must be finite and in [0.05, 2]')
    return result

def colors(tone):
    return rgb(tone.get('sun', [1, 1, 1]), 'sun'), rgb(tone.get('sky', [1, 1, 1]), 'sky')

def apply_native(floats, tone):
    """Run after light_split, on both native light sets; change only colour."""
    sun, sky = colors(tone)
    for c in range(3):
        floats[4+c] *= sky[c]
        floats[7+c] *= sun[c]

def reference(floats, direction, split, tone):
    """The baked map divides by native ground tint so colour is applied once."""
    sun, sky = colors(tone)
    length = math.sqrt(sum(v*v for v in direction))
    nl = max(-direction[1] / max(length, 1e-9), 0.05)
    result = []
    for c in range(3):
        ambient = float(floats[4+c]); direct = float(floats[7+c]) * float(floats[23+c]) * nl
        a = ambient * split; d = direct + ambient * (1-split)
        result.append((a*sky[c]+d*sun[c]) / max(a+d, 1e-9))
    return result

def bake_parameters(cfg):
    tone = cfg.get('lighting_tone')
    if not tone: return None
    # Same donor and lighting set used by the importer's brightness rule.
    from import_classic import donor_light
    sets = donor_light(cfg)
    if not sets: raise ValueError('lighting_tone requires a lighting_from donor')
    fl = sets[min(1, len(sets)-1)]
    sun, sky = colors(tone)
    return dict(sun=sun, sky=sky, reference=reference(fl, cfg.get('light_dir', fl[1:4]), float(cfg.get('light_split', 1.0)), tone))

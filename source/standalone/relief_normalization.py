"""Common review depth calibration. Does not modify installed assets or diffuse pixels."""
import numpy as np
import cv2
VERSION = "common-depth-v1"
BASE_DEPTH = .018
TARGET_SPAN = .60

def normalize(height, coverage, kind, old_depth):
    h = np.asarray(height, np.float32)
    mask = coverage >= 128
    if not mask.any():
        raise ValueError("No opaque pixels in relief head")
    values = h[mask]
    low, high = np.percentile(values, [1, 99])
    span = float(high-low)
    # One shared affine transform for all architectural maps retains the authored
    # depth hierarchy between windows, closed doors, frames and trim across heads.
    reference_span = .702 if kind == "facade" else span
    flat = span < 1e-6
    target_span = .04 if kind == 'asphalt' else TARGET_SPAN
    scale = 1. if flat else target_span / max(reference_span, 1e-6)
    peak = 1. if not mask.all() else float(values.max())
    full_recess = float(peak-values.min())
    # No clipping: preserve every relative depth, leave outlier headroom.
    if full_recess > 0:
        scale = min(scale, .95/full_recess)
    result = 1. - (peak-h)*scale
    if not mask.all():
        # Extend opaque surface height into invisible space. Raising alpha rims
        # creates concave fence posts and false normals at every cutout edge.
        _, labels = cv2.distanceTransformWithLabels((~mask).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
        result[~mask] = result[mask][labels[~mask]-1]
    if flat:
        result.fill(1.)
    assert np.isfinite(result).all() and result.min() >= -.00001 and result.max() <= 1.00001
    return np.clip(result,0,1).astype(np.float32), dict(
        version=VERSION, old_base_depth=float(old_depth), base_depth=BASE_DEPTH,
        old_percentile_span=span, target_span=target_span, height_scale=float(scale),
        old_gain_to_new_gain=float(old_depth/(BASE_DEPTH*scale)),
        normalized_percentile_span=float(np.diff(np.percentile(result[mask],[1,99]))[0]),
        shared_facade_calibration=kind=="facade", flat=flat)

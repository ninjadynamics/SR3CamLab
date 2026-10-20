# Mapping and validation

## Coordinate space and reference density

Inspect object transforms before measuring distances or choosing projection axes. Imported game meshes may use local Y as height. Measure in world space, or a documented equivalent space with known uniform scale.

Use the mesh's actual tessellation (`mesh.calc_loop_triangles()` and `mesh.loop_triangles`) and retain each triangle's polygon and loop correspondence. A triangle fan is not a valid substitute for concave polygons and can produce false extreme distortion.

For a nondegenerate triangle:

1. Express its geometric edges in an orthonormal 2D basis on its surface, forming matrix P.
2. Form UV edge matrix U using the same corner order.
3. The Jacobian is J = U × inverse(P).
4. Singular values s1 >= s2 measure directional scale. Anisotropy is s1/s2; area density is sqrt(abs(det(J))).

Reject numerically degenerate geometry/UV triangles from ratios and report them separately. Examine real slivers independently rather than silently dropping visible problems.

For a square full-tile texture, density is repeats per world unit; tile span is its reciprocal. For nonsquare textures, use pixel-scaled coordinates `(u * width, v * height)` to measure texel density, or explicitly preserve different intended directional repeat scales. Atlas subregions require their own interpretation.

Estimate the intended density with a surface-area-weighted median from healthy reference faces. Set area and anisotropy thresholds relative to the asset. Do not learn the target density from the damaged stretched faces or change scale merely to make the texture sharper.

## Temporary unwrap mesh

Build a separate mesh from the target faces with explicit source face/corner mappings. Preserve face winding and material identities. Coordinate welding can reconnect duplicated imported UV seams, but only in the temporary mesh and only where surface identity supports it. Positional coincidence can also mean two intentionally separate surfaces.

Angle-based unwrap worked for the Mountain tunnel shell. Its effective operator settings were:

```python
bpy.ops.uv.unwrap(method='ANGLE_BASED',
                  fill_holes=True,
                  correct_aspect=False,
                  margin=0.001)
```

These settings describe that square-texture case, not all assets. Confirm operator context and supported API values in the running Blender. For other shapes, choose controlled seams or separate charts rather than forcing a single unwrap.

Keep geometric connected components distinct from UV charts: one continuous shell can contain multiple charts, while a material/location selection can include detached rocks that must be excluded.

## Align and normalize charts

For each chart:

- Estimate a coherent orientation from healthy original faces. A surface-area-weighted Procrustes fit of face-centered UVs can remove translation from the orientation estimate.
- Preserve meaningful direction: rock strata, masonry courses, and authored text may constrain rotation or mirroring. Reflections acceptable for some natural materials are not acceptable for signage.
- Scale the entire chart isotropically. For square full-tile UVs, use:
  `factor = target_density / sqrt(total_uv_area / total_surface_area)`.
- Anchor translation to a healthy reference location to preserve approximate texture phase. Inspect the anchor and neighboring boundaries visually.

Global chart normalization preserves average density, not exact density at every point. If a chart retains visible distortion, revise its seams or parameterization. Per-face normalization hides local metrics at the expense of new discontinuities.

## Validate and apply

Before applying, verify the source has not changed since capture. Abort stale mappings and resnapshot rather than guessing updated indices.

Apply UV coordinates through explicit source loops only. Check:

- Vertex positions and transforms unchanged.
- Polygon connectivity and winding unchanged.
- Material assignments unchanged.
- All out-of-scope UV loops exactly unchanged at the stored precision.
- Protected object data unchanged.
- No temporary duplicate surface remains visible or saved.

Measure distortion against actual Blender triangles. Report area-weighted distributions and significant outliers; huge ratios on near-zero-area triangles must not be presented as broad texture damage.

Review texture flow overhead and from both sides, including seams, crown, portals, and boundary transitions. Use the existing material/texture shading; a solid untextured preview cannot validate UV quality.

Restore overlays and selection usability after screenshots. Save a review version and state whether it has been installed.

## Live-tool reliability

A timed-out Blender call may have completed its mutation. Inspect live state and output files before retrying. Keep calls small and avoid rerunning saves or UV writes blindly.

For data exchange with a separate Python runtime, use portable primitive numbers and documented arrays. Pickled NumPy scalar objects can fail across NumPy versions; do not make a reusable workflow depend on a session-specific pickle.

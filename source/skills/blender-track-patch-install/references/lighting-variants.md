# Lighting alternatives and sunset colour

Use this for a lighting-only rebake of an accepted track. The main pipeline reference covers geometry, packing and installation.

## Direction and placement

Read the original course configuration rather than rounding the owner's remembered elevation. Mountain's original ROM light-travel vector is `[0,-9.4,3.4]`, elevation **70.114834886 degrees**. Keep it exact for a default-sun rebuild. The native lighting sets store travel direction; the collected RT scene stores the opposite, toward the sun. Verify both native sets and the collected vector.

SR3 coordinates are Y-up. Determine driver-left from the road's direction/lateral basis, not screen-left in an overhead image. For the Mountain village, positive game X is driver-left. At elevation 35 degrees, travel direction `[-8.191520442889917,-5.7357643635104605,0]` makes the left-hand houses cast shadows into the road. A house-only ray scan found 561 of 1,240 sampled village-road points shadowed by left houses, none by right houses. This is a direction-selection measurement, not a whole-stage shadow percentage. Inspect final encoded lightmaps in a representative view as well; terrain, trees and filtering also affect the result.

Keep authored material labels, perforated canopy masks and transparent grass receiving. Changing direction requires a fresh collect, RT bake, composition and encoding. Retain the current protected gameplay road and collision boundary settings.

## Lighting colour without changing artwork

The optional `common.lighting_tone` recipe field accepts RGB multipliers, for example:

```json
"lighting_tone": {
  "sun": [1.08, 0.78, 0.72],
  "sky": [0.88, 0.92, 1.02]
}
```

This example gives peach/rose direct light with cooler sky fill. Omit the field for the original colour path. Do not recolour albedo, painted markings, sky images or relief maps to simulate the requested sun colour.

`core/rtbake/lighting_tone.py` validates finite positive multipliers and derives the native flat-ground reference tint. `import_classic.py` applies the colour to ambient/direct fields **after** the existing `light_split`, on both native lighting sets. `stack.py` passes the matching configuration to the RT composer via `RTG_LIGHTING_TONE`.

`rtcompose.c:rtc_pages_toned` colours direct and sky contributions separately. Road bounce stays achromatic, but sunlight and sky tint must remain coloured: applying the old road greyscale operation to the entire result would erase the sunset from the asphalt. Divide the lightmap by the native reference tint so native lighting does not apply the same warmth twice. Keep the no-tone `rtc_pages` arithmetic untouched; the compiled regression compares it byte-for-byte to the retained earlier helper when available.

Run `python source/tools/import/core/rtbake/test_lighting_tone.py` after changing this path. It checks warm direct light and cool road shadows, native-reference compensation, unchanged non-colour light fields and invalid inputs. Inspect representative encoded views; numeric checks do not establish artistic approval. Offline previews omit the game's final camera/exposure/relief behaviour and are not gameplay tests.

## Installation and retirement

**Current owner decision, 2026-10-21:** the sunset was rejected artistically and its recipe, installed track and generated files were deleted. Keep only original-sun Mountain R4 in track1/Desert4. The 35-degree direction and optional colour procedure above are historical technical findings, not an approved look or an instruction to restore sunset. Current geometry source is `work/blender/mountain.patch3.v20.blend`; roof edits continue as v21. Retirement evidence: `work/research/mountain-sunset-retired-20261021/`.

### Historical two-variant build

Before the owner rejected sunset on 2026-10-21, **Mountain R4** was the original-sun main slot `track1/Desert4`; **Mountain R4 Sunset** was the warm 35-degree alternative in `track2/Desert4`. Daytona remains in slot 5. Each has 22 newly extracted lightmaps and uses 325.269 MiB across seven unpacked SBFs. All 575 encoded shape chunks retain positions, UV0, topology and bounds. Sun-dependent normals and tangents change intentionally. R4B, albedo/alpha, gameplay files, runtime and native relief shader remain unchanged.

The main relief page rebuilds track1 only. Keep its clean RT/review pins, reviewed manifest, native receipt and accepted hashes aligned with the daylight slot. The sunset is a separate family-map snapshot with the same installed YAML gains/exclusions and shared global +/- controls; do not imply that a later family-gain Apply automatically updates both alternatives.

The owner explicitly retired the 45-degree bake. Its build directories, extracted maps, superseded low recipe and verified staged/backup copies were removed after replacement validation. Retain the accepted `.blend`, patch chain, canonical textures, semantic maps and new final maps. Do not leave stale intermediate cache markers after pruning their arrays. The exact deletion inventory and preservation hashes are under `work/research/mountain-lighting-pair-20261021/`.

That folder retains daylight recipes, build logs, final hashes, extracted maps, its offline village preview and the staged-only relief-page test. Sunset artifacts were subsequently removed; the pair install report records historical hashes only. The old 45-degree rollback was intentionally retired; historical notes about that rollback are not current availability promises. No game was launched for this rebuild.

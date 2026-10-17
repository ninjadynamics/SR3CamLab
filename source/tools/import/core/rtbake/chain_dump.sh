#!/bin/bash
# The importer's polygons as the rounding gets them (ROUND_IN), for one chain of patches: to prove two chains give the same build.
#   chain_dump.sh <out.pkl> old|new [tag]
#     old: the course patches 1 2 3 + board_moves + patch_files (game_<tag>, the way fast_all.sh built v11 - v15)
#     new: the course patches only (patch 3 staged: the v11 chain in one file, 2026-10-15)
. "$(dirname "${BASH_SOURCE[0]}")/paths.sh"
OUT="$1"; MODE="$2"; TAG="${3:-v15}"; G1="$SP/game_$TAG"
cd "$IMP" || exit 1; export PYTHONPATH="$(cygpath -w "$PWD")"
args=(); while IFS= read -r kv; do [ -n "$kv" ] && args+=(--set "$kv"); done < "$IMP/rtbake/raw_recipe.txt"
C=("${args[@]}" --set light_contrast=0.01 --set lit_sides=false --set seen_sides=true --set stitch=true --set lm_cutouts=[\"tex_s1_x0960_y0576_64x128_c10D_t\",\"tex_s1_x0960_y0576_64x128_c10F_t\"] --set patch=true --set patch_clean=true --set round=4 --set round_slide=false)
[ "$MODE" = old ] && C+=(--set "board_moves=\"$G1/board_moves.json\"" --set "patch_files=[\"$G1/src.mountain.patch.4d.json\"]")
t0=$(date +%s); ROUND_IN="$(cygpath -w "$OUT")" ROUND_IN_STOP=1 python import_classic.py src 1 classic --norender --name step99_mountain_chaindump_desert4 "${C[@]}" > "$OUT.log" 2>&1; e=$?
echo "$MODE: exit $e, $(( $(date +%s) - t0 )) s"; grep -E "patch .*faces added|stage|boards moved|REFUSED|Traceback|Error" "$OUT.log" | sed -E 's/^ +//' | cut -c1-200

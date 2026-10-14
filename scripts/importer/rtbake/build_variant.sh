#!/bin/bash
# One more game build of a level from the light already baked, with extra course settings.   build_variant.sh <tag> <level> <suffix> [key=value ...]
#   e.g.  build_variant.sh v11 4 d light_split=0.72     -> work\out\step99_mountain_r4nv11_d_desert4   (the folders and the baked light of fast_all.sh <scene> v11)
SP="C:/Users/bruno/AppData/Local/Temp/claude/F--Jogos-SEGA-Rally-3/7efd0921-014b-4b6a-8439-6ea64a2cda95/scratchpad"
W="F:/Jogos/SEGA Rally 3/SR3 track format/work"; IMP="F:/Jogos/SEGA Rally 3/SR3CamLab/scripts/importer"; TAG="$1"; L="$2"; V="$3"; shift 3
G1="$SP/game_$TAG"; BASE="$W/out/step99_mountain_p3_desert4/Desert4"; cd "$IMP" || exit 1; export PYTHONPATH="$(cygpath -w "$PWD")"
if [ "$L" = 1 ]; then G="$G1"; n="step99_mountain_${TAG}_${V}_desert4"; else G="$SP/game_r${L}n$TAG"; n="step99_mountain_r${L}n${TAG}_${V}_desert4"; fi
args=(); while IFS= read -r kv; do [ -n "$kv" ] && args+=(--set "$kv"); done < "$SP/raw_recipe.txt"
COMMON=("${args[@]}" --set light_contrast=0.01 --set lit_sides=false --set seen_sides=true --set stitch=true --set lm_cutouts=[\"tex_s1_x0960_y0576_64x128_c10D_t\",\"tex_s1_x0960_y0576_64x128_c10F_t\"] --set patch=true --set patch_clean=true --set "board_moves=\"$G1/board_moves.json\"" --set "patch_files=[\"$G1/src.mountain.patch.4d.json\"]")
[ "$L" != 1 ] && COMMON+=(--set round=$L --set round_slide=false)
for kv in "$@"; do COMMON+=(--set "$kv"); done
t0=$(date +%s); python import_classic.py src 1 classic --norender --name $n "${COMMON[@]}" --set "car_shade=\"$G/lm.carshade.npz\"" --set "seen_sides_file=\"$G/lm.sides.npz\"" --set "lm_table=\"$G/lmA\"" > "$G/build_$V.log" 2>&1; e=$?
cp "$BASE/arcade_times.bin" "$BASE/road.txt" "$W/out/$n/Desert4/"
echo "$n: exit $e, $(( $(date +%s) - t0 )) s"; grep -E "lighting sets overridden|light maps: [0-9]+ pages|gaps sealed.*no triangle|Traceback|Error|STOPPED" "$G/build_$V.log" | sed -E 's/^ +//' | cut -c1-330

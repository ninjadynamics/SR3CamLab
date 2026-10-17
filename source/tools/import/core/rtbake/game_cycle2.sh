#!/bin/bash
# Blender scene -> game builds with baked light.   game_cycle.sh <scene.blend> <stage>
#   stage "collect" : scene -> patch -> a build that collects the polygons to light (and its dump)
#   stage "bake"    : the light (rt_bake_game3.py, slow quality) and the two looks A (normal) and B (25% softer)
#   stage "build"   : the two game builds (not installed)
. "$(dirname "${BASH_SOURCE[0]}")/paths.sh"
G="$SP/game"
SCENE="$1"; STAGE="$2"; set -o pipefail
cd "$IMP" || exit 1; export PYTHONPATH="$(cygpath -w "$PWD")"
args=(); while IFS= read -r kv; do [ -n "$kv" ] && args+=(--set "$kv"); done < "$SP/raw_recipe.txt"
common=("${args[@]}" --set light_contrast=0.01 --set lit_sides=false --set seen_sides=true --set stitch=true --set lm_cutouts=[\"tex_s1_x0960_y0576_64x128_c10D_t\",\"tex_s1_x0960_y0576_64x128_c10F_t\"] --set patch=true --set patch_clean=true --set "board_moves=\"$G/board_moves.json\"" --set "patch_files=[\"$G/src.mountain.patch.4d.json\"]")
if [ "$STAGE" = "collect" ]; then
  "$BL" -b "$SCENE" --python "$IMP/blendpatch/bl_dump.py" -- "$G/scene.pkl" > "$G/dump.log" 2>&1 || { echo "dump failed"; exit 2; }
  python - "$G" <<'E' || exit 3
import pickle, re, sys
D = pickle.load(open(sys.argv[1] + '/scene.pkl', 'rb')); d = next(o for o in D['objects'] if o['name'].startswith('1995 course')); d['mats'] = [re.sub(r'^shade\d+_', '', m) for m in d['mats']]; pickle.dump(D, open(sys.argv[1] + '/scene_m.pkl', 'wb'))
E
  python "$G/scene_diff_local.py" "$W/previews/sr3_decoded/step99_mountain_p3_desert4.obj" "$W/out/step99_mountain_p3_desert4/Desert4/texmap.json" "$G/scene_m.pkl" "$W/out/step99_mountain_p3_desert4/Desert4/texmap.json" "$G/src.mountain.patch.4.json" 4 1,2,3 "bake=$G/facade_recipes.json" 'sea={"clip": false}' 2>&1 | grep -E "^patch 4|base .* faces|Traceback|Error" | cut -c1-260 || exit 4
  python "$SP/tree_moves.py" "$G/src.mountain.patch.4.json" "$G/src.mountain.patch.4d.json" "$G/board_moves.json" || exit 5
  GAPFILL_DUMP="$G/faces.pkl" python import_classic.py src 1 classic --norender --name step99_mountain_rtc_desert4 "${common[@]}" --set "gate_dump=\"$G/gate.json\"" --set "lm_collect=\"$G/lm\"" --set "car_shade_dump=\"$G/lm.carpages.json\"" > "$G/build_collect.log" 2>&1; echo "collect build exit $?"
  grep -E "boards moved|4d.json.*(NOT FOUND|faces added)|patch boards|patch clean-up|z-fight gate|light maps:|consistency|gates:|which side the road|gaps sealed|Traceback|Error|REFUSED|STOPPED" "$G/build_collect.log" | cut -c1-520
elif [ "$STAGE" = "bake" ]; then
  OMP_NUM_THREADS=$NT python -u "$SP/rtbake/rt_bake_game4.py" "$G/lm" "$G/faces.pkl" ${3:-slow} > "$G/bake4.log" 2>&1; echo "bake exit $?"; grep -E "RTG4|solids|skirts|texels|lit side|cars:|Traceback|Error" "$G/bake4.log" | cut -c1-300
  python "$SP/rt_compose_game.py" "$G/lm" "$G/lmA" 0.34 | cut -c1-200; python "$SP/rt_compose_game.py" "$G/lm" "$G/lmB" 0.505 | cut -c1-200
elif [ "$STAGE" = "build" ]; then
  for v in a b c; do V=$(echo $v | tr abc ABC); n=step99_mountain_rt_${v}_desert4; LMV=$V; cars=(--set "car_shade=\"$G/lm.carshade.npz\"")
    if [ $v = c ]; then LMV=A; cars=(); fi                        # c = a without the cars' pages (the fall-back if the game does not take them)
    python import_classic.py src 1 classic --norender --name $n "${common[@]}" "${cars[@]}" --set "lm_table=\"$G/lm$LMV\"" > "$G/build_$V.log" 2>&1; echo "$V build exit $?"
    grep -E "z-fight gate|consistency|light maps: [0-9]|gates:|gaps sealed|cars in baked|scenery \(classic\)|Traceback|Error|STOPPED" "$G/build_$V.log" | cut -c1-330
    cp "$W/out/step99_mountain_p3_desert4/Desert4/arcade_times.bin" "$W/out/step99_mountain_p3_desert4/Desert4/road.txt" "$W/out/$n/Desert4/"
  done
fi

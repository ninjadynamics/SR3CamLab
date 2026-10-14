#!/bin/bash
# Blender scene -> the RT build, with the work laid side by side.   fast_all.sh <scene.blend> <tag> ["4"]
#   The third argument names the rounding levels to build. R4 alone is the default: the owner drove R1, R2 and R4 with baked light on 2026-10-13
#   and chose it ("R4 is the way to go!!! make it the default step"). "1 2 4" builds all three for a comparison.
#   1. the scene's patch, once (dump, diff against the base build, tree moves) - the same for every rounding level
#   2. the collecting importer passes of all levels at the same time (each is one thread of Python)
#   3. the bakes one after the other (each takes every core) ; a level's game builds start when its bake ends and run beside the next bake
#   SKIP_SCENE=1   the patch files in game_<tag> are used as they are
#   ONLY_BUILD=1   only the game builds, from what is collected and baked already
# Folders and names as game_cycle3.sh / game_cycle_r.sh had them: R1 in game_<tag> -> step99_mountain_<tag>_a / _c ; Rn in game_r<n>n<tag> -> step99_mountain_r<n>n<tag>_a
SP="C:/Users/bruno/AppData/Local/Temp/claude/F--Jogos-SEGA-Rally-3/7efd0921-014b-4b6a-8439-6ea64a2cda95/scratchpad"
W="F:/Jogos/SEGA Rally 3/SR3 track format/work"; IMP="F:/Jogos/SEGA Rally 3/SR3CamLab/scripts/importer"; BL="C:/Program Files/Blender Foundation/Blender 5.1/blender.exe"
SCENE="$1"; TAG="$2"; LEVELS="${3:-4}"; G1="$SP/game_$TAG"; LOG="$SP/run_$TAG.log"; BASE="$W/out/step99_mountain_p3_desert4/Desert4"; mkdir -p "$G1"; cp -n "$SP/game/facade_recipes.json" "$SP/game/scene_diff_local.py" "$G1/" 2>/dev/null
cd "$IMP" || exit 1; export PYTHONPATH="$(cygpath -w "$PWD")"; T00=$(date +%s.%N)
now() { date +%s.%N; }; since() { python -c "import sys; print('%.1f' % (float(sys.argv[2]) - float(sys.argv[1])))" "$1" "$(now)"; }
say() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }
gdir() { if [ "$1" = 1 ]; then echo "$G1"; else echo "$SP/game_r${1}n$TAG"; fi; }
bname() { if [ "$1" = 1 ]; then echo "step99_mountain_${TAG}"; else echo "step99_mountain_r${1}n${TAG}"; fi; }
args=(); while IFS= read -r kv; do [ -n "$kv" ] && args+=(--set "$kv"); done < "$SP/raw_recipe.txt"
common() {      # $1 = level -> the array COMMON
  COMMON=("${args[@]}" --set light_contrast=0.01 --set lit_sides=false --set seen_sides=true --set stitch=true --set lm_cutouts=[\"tex_s1_x0960_y0576_64x128_c10D_t\",\"tex_s1_x0960_y0576_64x128_c10F_t\"] --set patch=true --set patch_clean=true --set "board_moves=\"$G1/board_moves.json\"" --set "patch_files=[\"$G1/src.mountain.patch.4d.json\"]")
  [ "$1" != 1 ] && COMMON+=(--set round=$1 --set round_slide=false)
}
scene() {
  local t=$(now)
  "$BL" -b "$SCENE" --python "$IMP/blendpatch/bl_dump.py" -- "$G1/scene.pkl" > "$G1/dump.log" 2>&1 || { say "dump failed"; return 2; }
  python - "$G1" <<'E' || return 3
import pickle, re, sys
D = pickle.load(open(sys.argv[1] + '/scene.pkl', 'rb')); d = next(o for o in D['objects'] if o['name'].startswith('1995 course')); d['mats'] = [re.sub(r'^shade\d+_', '', m) for m in d['mats']]; pickle.dump(D, open(sys.argv[1] + '/scene_m.pkl', 'wb'))
E
  python "$G1/scene_diff_local.py" "$W/previews/sr3_decoded/step99_mountain_p3_desert4.obj" "$BASE/texmap.json" "$G1/scene_m.pkl" "$BASE/texmap.json" "$G1/src.mountain.patch.4.json" 4 1,2,3 "bake=$G1/facade_recipes.json" 'sea={"clip": false}' 2>&1 | grep -E "^patch 4|base .* faces|Traceback|Error" | cut -c1-260 >> "$LOG" || return 4
  python "$SP/tree_moves.py" "$G1/src.mountain.patch.4.json" "$G1/src.mountain.patch.4d.json" "$G1/board_moves.json" >> "$LOG" 2>&1 || return 5
  say "scene -> patch: $(since $t) s"
}
collect() {     # $1 = level
  local L=$1 G=$(gdir $1) t=$(now); mkdir -p "$G"; common $L
  ROUND_STRETCH="$G/stretch.json" GAPFILL_DUMP="$G/faces.pkl" python import_classic.py src 1 classic --norender --name "$(bname $L)c_desert4" "${COMMON[@]}" --set "seen_sides_file=\"$G/lm.sides.npz\"" --set "gate_dump=\"$G/gate.json\"" --set "lm_collect=\"$G/lm\"" --set "car_shade_dump=\"$G/lm.carpages.json\"" > "$G/build_collect.log" 2>&1
  say "R$L collect: exit $?, $(since $t) s ; $(grep -E 'light maps: [0-9]+ polygons' "$G/build_collect.log" | sed -E 's/ -> .*//; s/^ +//' | cut -c1-110)"
  grep -E "ROUNDED|Traceback|Error|REFUSED|STOPPED" "$G/build_collect.log" | cut -c1-1500 >> "$LOG"
}
bake() {        # $1 = level
  local L=$1 G=$(gdir $1) t=$(now) py=rt_bake_game5.py      # (every level: its rays are rt_bake_game4.py's, compared on a whole R1 bake)
  OMP_NUM_THREADS=31 python -u "$SP/rtbake/$py" "$G/lm" "$G/faces.pkl" slow > "$G/bake4.log" 2>&1; local e=$?
  python "$SP/rt_compose_game.py" "$G/lm" "$G/lmA" 0.34 > "$G/compose.log" 2>&1
  say "R$L bake: exit $e, $(since $t) s ; $(grep -E '^RTG[45] ' "$G/bake4.log" | cut -c1-150)"
  grep -E "Traceback|Error" "$G/bake4.log" "$G/compose.log" | cut -c1-300 >> "$LOG"
}
build() {       # $1 = level, $2 = a (with the cars' pages) or c (without)
  local L=$1 v=$2 G=$(gdir $1) t=$(now) n="$(bname $1)_$2_desert4" cars=(); common $L
  [ "$v" = a ] && cars=(--set "car_shade=\"$G/lm.carshade.npz\"")
  python import_classic.py src 1 classic --norender --name $n "${COMMON[@]}" "${cars[@]}" --set "seen_sides_file=\"$G/lm.sides.npz\"" --set "lm_table=\"$G/lmA\"" > "$G/build_$v.log" 2>&1; local e=$?
  cp "$BASE/arcade_times.bin" "$BASE/road.txt" "$W/out/$n/Desert4/"
  say "R$L build $v: exit $e, $(since $t) s ; $(grep -E 'light maps: [0-9]+ pages' "$G/build_$v.log" | sed -E 's/^ +//' | cut -c1-140) ; $(grep -E 'scenery \(classic\)' "$G/build_$v.log" | sed -E 's/^ +//; s/, [0-9]+ faces with.*//' | cut -c1-90)"
  grep -E "meshes left uncut|Traceback|Error|STOPPED" "$G/build_$v.log" | cut -c1-300 >> "$LOG"
}
: > "$LOG"; say "fast_all: scene $(basename "$SCENE"), tag $TAG, levels $LEVELS"
if [ -n "$ONLY_BUILD" ]; then      # ONLY_BUILD=1: the game builds again from the light already baked (all levels side by side)
  for L in $LEVELS; do build $L a & [ "$L" = 1 ] && build $L c & done; wait; say "builds done: $(since $T00) s"; exit 0
fi
if [ -z "$SKIP_SCENE" ]; then scene || exit $?; fi
for L in $LEVELS; do collect $L & done; wait
for L in $LEVELS; do
  bake $L
  build $L a &
  [ "$L" = 1 ] && build $L c &
done
wait; say "all done: $(since $T00) s"

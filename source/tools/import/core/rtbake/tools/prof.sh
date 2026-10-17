#!/bin/bash
# The importer's two passes again on the inputs of a finished run, writing only under opt/: to time them (PROF=1: under cProfile) and to compare
# what they write with that run, byte for byte.   prof.sh <1|4> <collect|build> [tag]        PTAG = the finished run's tag (default t1)
. "$(dirname "${BASH_SOURCE[0]}")/../paths.sh"
R="$1"; STAGE="$2"; TAG="${3:-p}"; PTAG="${PTAG:-t1}"; O="$SP/opt/r$R$TAG"; mkdir -p "$O"; G1="$SP/game_$PTAG"
if [ "$R" = 1 ]; then G="$G1"; rnd=(); else G="$SP/game_r${R}n$PTAG"; rnd=(--set round=$R --set round_slide=false); fi
cd "$IMP" || exit 1; export PYTHONPATH="$(cygpath -w "$PWD")"
args=(); while IFS= read -r kv; do [ -n "$kv" ] && args+=(--set "$kv"); done < "$SP/raw_recipe.txt"
common=("${args[@]}" --set light_contrast=0.01 --set lit_sides=false --set seen_sides=true --set stitch=true "${rnd[@]}" --set lm_cutouts=[\"tex_s1_x0960_y0576_64x128_c10D_t\",\"tex_s1_x0960_y0576_64x128_c10F_t\"] --set patch=true --set patch_clean=true --set "board_moves=\"$G1/board_moves.json\"" --set "patch_files=[\"$G1/src.mountain.patch.4d.json\"]" --set "seen_sides_file=\"$O/lm.sides.npz\"")
PY=(python); [ -n "$PROF" ] && PY=(python -m cProfile -o "$O/$STAGE.prof")
t0=$(date +%s.%N)
if [ "$STAGE" = collect ]; then
  GAPFILL_DUMP="$O/faces.pkl" "${PY[@]}" import_classic.py src 1 classic --norender --name step99_mountain_opt${R}${TAG}c_desert4 "${common[@]}" --set "gate_dump=\"$O/gate.json\"" --set "lm_collect=\"$O/lm\"" --set "car_shade_dump=\"$O/lm.carpages.json\"" > "$O/collect.log" 2>&1; e=$?
else
  [ -f "$O/lm.sides.npz" ] || cp "$G/lm.sides.npz" "$O/"
  "${PY[@]}" import_classic.py src 1 classic --norender --name step99_mountain_opt${R}${TAG}_a_desert4 "${common[@]}" --set "car_shade=\"$G/lm.carshade.npz\"" --set "lm_table=\"$G/lmA\"" > "$O/build.log" 2>&1; e=$?
fi
echo "R$R $STAGE exit $e, $(python -c "import sys; print('%.1f' % (float(sys.argv[2]) - float(sys.argv[1])))" $t0 $(date +%s.%N)) s"
# the same bytes as the finished run?
W="$W/out"
if [ "$STAGE" = collect ]; then
  for f in lm.lm.npz lm.scene faces.pkl lm.sides.npz lm.carpages.json gate.json; do cmp -s "$O/$f" "$G/$f" && echo "   $f: same bytes" || echo "   $f: DIFFERENT"; done
else
  if [ "$R" = 1 ]; then ref="step99_mountain_${PTAG}_a_desert4"; else ref="step99_mountain_r${R}n${PTAG}_a_desert4"; fi; nd=0
  for f in $(ls "$W/step99_mountain_opt${R}${TAG}_a_desert4/Desert4"); do cmp -s "$W/step99_mountain_opt${R}${TAG}_a_desert4/Desert4/$f" "$W/$ref/Desert4/$f" || { echo "   built $f: DIFFERENT"; nd=$((nd + 1)); }; done
  echo "   built files that differ from $ref: $nd (arcade_times.bin and road.txt are copied in by the route, not written by the importer)"
  grep -E "not found|taken over|fastdxt check" "$O/build.log" | sed -E 's/^ +//' | cut -c1-200
fi

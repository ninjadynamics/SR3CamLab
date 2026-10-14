#!/bin/bash
# The v11 builds read back from their own files: numbers, gaps, cars' pages, and check renders.   verify_v11.sh
SP="C:/Users/bruno/AppData/Local/Temp/claude/F--Jogos-SEGA-Rally-3/7efd0921-014b-4b6a-8439-6ea64a2cda95/scratchpad"; IMP="F:/Jogos/SEGA Rally 3/SR3CamLab/scripts/importer"; BL="C:/Program Files/Blender Foundation/Blender 5.1/blender.exe"; cd "$IMP" || exit 1; export PYTHONPATH="$(cygpath -w "$PWD")"
for e in "v11_a game_v11" "v11_c game_v11" "r2nv11_a game_r2nv11" "r4nv11_a game_r4nv11"; do set -- $e; st=step99_mountain_$1_desert4; D="$SP/verify_v11/$1"; rm -rf "$D"
  python "$SP/asbuilt_decode.py" $st "$SP/$2/faces.pkl" "$D" 2>&1 | tail -1 | cut -c1-250
  if [ "$1" != "v11_c" ]; then python "$SP/carshade/check_built.py" $st "$SP/$2/lm.carshade.npz" | tail -1; fi
  OMP_NUM_THREADS=4 python "$SP/seal_test.py" $st 2>&1 | grep -E "^before" | cut -c1-220
  RT_SAMPLES=8 "$BL" -b --factory-startup --python "$SP/asbuilt_scene.py" -- "$D" "$SP/game/views_v11.json" "$D/shots" 2>&1 | grep -E "Error|Traceback"
done

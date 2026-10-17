#!/bin/bash
# All RT versions from one scene: R1 (normal, soft, cars unshaded), R2 and R4 (rounded along the normal).   run_v11.sh <scene.blend> <tag>
. "$(dirname "${BASH_SOURCE[0]}")/paths.sh"; SCENE="$1"; TAG="$2"; LOG="$SP/run_$TAG.log"; : > "$LOG"
say() { echo "$(date +%H:%M:%S) $*" | tee -a "$LOG"; }
say "R1 collect"; GDIR="$SP/game_$TAG" NTAG="$TAG" bash "$SP/game_cycle3.sh" "$SCENE" collect 2>&1 | grep -E "exit|gates:|which side|light maps:|z-fight gate: [0-9]+ coplanar|Traceback|Error|REFUSED|STOPPED" | cut -c1-260 >> "$LOG"
say "R1 bake";    GDIR="$SP/game_$TAG" NTAG="$TAG" bash "$SP/game_cycle3.sh" "$SCENE" bake slow 2>&1 | grep -E "exit|RTG4|cars:|RTCG|Traceback|Error" | cut -c1-200 >> "$LOG"
say "R1 build";   GDIR="$SP/game_$TAG" NTAG="$TAG" bash "$SP/game_cycle3.sh" "$SCENE" build 2>&1 | grep -E "exit|light maps: [0-9]|scenery \(classic\)|written:|cars in baked|Traceback|Error|STOPPED" | cut -c1-240 >> "$LOG"
for cfg in "2 2n$TAG" "4 4n$TAG"; do set -- $cfg
  say "R$1 collect"; RLEVEL=$1 RSLIDE=false RTAG=$2 bash "$SP/game_cycle_r.sh" "$SCENE" collect 2>&1 | grep -E "exit|ROUNDED|which side|light maps:|Traceback|Error|REFUSED|STOPPED" | cut -c1-260 >> "$LOG"
  say "R$1 bake";    RLEVEL=$1 RSLIDE=false RTAG=$2 bash "$SP/game_cycle_r.sh" "$SCENE" bake slow 2>&1 | grep -E "exit|rectangles|RTG5|cars:|RTCG|Traceback|Error" | cut -c1-240 >> "$LOG"
  say "R$1 build";   RLEVEL=$1 RSLIDE=false RTAG=$2 bash "$SP/game_cycle_r.sh" "$SCENE" build 2>&1 | grep -E "exit|light maps: [0-9]|scenery \(classic\)|written:|cars in baked|Traceback|Error|STOPPED" | cut -c1-240 >> "$LOG"
done
say "all done"

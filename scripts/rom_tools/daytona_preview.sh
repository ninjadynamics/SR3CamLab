#!/bin/bash
# Preview stills of an exported Daytona USA course, rendered in Blender through the CPU guard.
#   bash daytona_preview.sh beginner [number of road views]
# Uses the *_lifted.obj (coplanar overlays moved 1.5 cm per layer) and writes <COURSES>/<course>/renders/*.png
HERE="$(cd "$(dirname "$0")" && pwd)"
COURSE="$1"
N="${2:-8}"
C="F:/Jogos/SEGA Rally 3/SR3 track format/classic/courses/daytona/$COURSE"
GUARD="C:/Users/bruno/AppData/Local/Temp/claude/F--Jogos-SEGA-Rally-3/7efd0921-014b-4b6a-8439-6ea64a2cda95/scratchpad/guard.sh"
BLENDER="C:/Program Files/Blender Foundation/Blender 5.1/blender.exe"
cd "$HERE" || exit 1
python daytona_course.py "$COURSE" "$N" || exit 1
if [ -f "$GUARD" ]; then RUN=(bash "$GUARD"); else RUN=(); fi
"${RUN[@]}" "$BLENDER" -b --factory-startup --python daytona_render.py -- "$C/daytona_${COURSE}_lifted.obj" "$C/views.json" "$C/renders" 2>&1 | grep -E "rendered|done|GUARD|Error|Traceback"

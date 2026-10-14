#!/bin/bash
# guard.sh <command ...>   Runs a job only while SEGA Rally 3 is NOT running (owner, 2026-10-13: "Are you using the CPU? The game is choking").
#   - the game is running when asked: with WAIT=1 it waits until the game has been closed for 20 s, otherwise it does not start (exit 98) ;
#   - the game starts while the job runs: the job and everything it started (the whole process tree) is stopped within 2 s (exit 99).
#   GUARD_PROC = the process to keep clear of, as a pattern on tasklist's lines (default the game; another name only to test this script).
PAT="${GUARD_PROC:-^Rally\.exe}"
game() { tasklist 2>/dev/null | grep -qiE "$PAT"; }
stopmine() {      # what may be left of an importer / bake / Blender job when its shell is gone
  powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { (\$_.Name -eq 'python.exe' -and \$_.CommandLine -match 'quiet\.py|import_classic\.py|rt_bake_game|rt_compose_game|bench_rays|scene_diff|tree_moves|asbuilt_|seal_test|spec_check|test_clusters|cmp_setup') -or (\$_.Name -eq 'blender.exe' -and \$_.CommandLine -match ' -b ') } | ForEach-Object { Stop-Process -Id \$_.ProcessId -Force -ErrorAction SilentlyContinue }" > /dev/null 2>&1
}
if game; then
  [ -z "$WAIT" ] && { echo "GUARD: the game is running - not started"; exit 98; }
  echo "GUARD $(date +%H:%M:%S): the game is running - waiting for it to close"
  while true; do while game; do sleep 5; done; sleep 20; game || break; done
  echo "GUARD $(date +%H:%M:%S): the game is closed - starting"
fi
"$@" & pid=$!; sleep 1; wp=$(cat /proc/$pid/winpid 2>/dev/null)
while kill -0 $pid 2>/dev/null; do
  if game; then
    echo "GUARD $(date +%H:%M:%S): the game started - job stopped"
    [ -n "$wp" ] && taskkill //T //F //PID $wp > /dev/null 2>&1
    kill $pid 2>/dev/null; [ -z "$GUARD_PROC" ] && stopmine; exit 99
  fi
  sleep 2
done
wait $pid

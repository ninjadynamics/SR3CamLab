# The folders of tools/import/settings.json for the bake scripts (sourced by them):
#   IMP = tools/import/core, W = <data_root>/work, BL = blender.exe, NT = worker threads, SP = the scripts' own working folder
#   (SR3_SCRATCH, default <data_root>/work/tmp/rtbake)
IMP="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
mapfile -t _P < <(python -c "import sys; sys.path.insert(0, sys.argv[1]); import common as c; print(c.WORK); print(c.BLENDER or ''); print(c.threads())" "$(cygpath -w "$IMP")" | tr -d '\r')
W="$(cygpath -m "${_P[0]}")"; BL="${_P[1]:+$(cygpath -m "${_P[1]}")}"; NT="${_P[2]}"
SP="${SR3_SCRATCH:-$W/tmp/rtbake}"; mkdir -p "$SP"

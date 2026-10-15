# Runs sr3mods.ps1's reading of the two settings "mouseSmoothing" and "cameraBlend" (file, switch, defaults, limits) on
# made-up profile files, without a game: the script is cut before its launch part, as cycle_mocktest.ps1 does.
$src = Get-Content (Join-Path $PSScriptRoot '..\sr3mods.ps1') -Raw
$cut = $src.IndexOf('# ---- launch (unless')
$body = $src.Substring(0, $cut).Replace('. (Join-Path $PSScriptRoot ''setup.ps1'')', ". '" + (Join-Path $PSScriptRoot '..\setup.ps1') + "'")
$body += "`n'{0} {1}' -f `$lookSmooth.ToString([Globalization.CultureInfo]::InvariantCulture), `$blendSec.ToString([Globalization.CultureInfo]::InvariantCulture)`n"
$dir = Join-Path $env:TEMP 'sr3settingstest'; Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue; [void](New-Item -ItemType Directory -Path $dir)
$tmp = Join-Path $dir 'patch_cut.ps1'; Set-Content -LiteralPath $tmp -Value $body -Encoding UTF8
$profiles = "profiles:`n  Daytona:`n    strength: 0.7`n    fadeInStartKmh: 14`n    fadeInFullKmh: 43`n    stiffnessMin: 65`n    stiffnessMax: 92`n    damping: 11.5`n"
$pass = 0; $fail = 0
function Case([string]$what, [string]$top, [string]$want, [hashtable]$switches = @{}, [string]$own = $null) {
    $file = Join-Path $dir 'case.yaml'; [IO.File]::WriteAllText($file, "default: Daytona`n$top`n$profiles")
    $ownFile = Join-Path $dir 'profiles.yaml'                          # "profiles.yaml next to the script": what a Launch file without the keys falls back on
    if ($null -ne $own) { [IO.File]::WriteAllText($ownFile, "default: Daytona`n$own`n$profiles") } elseif (Test-Path $ownFile) { Remove-Item $ownFile }
    $got = "$(& $tmp 'Daytona' -ProfilesFile $file @switches | Select-Object -Last 1)"
    if ($got -eq $want) { $script:pass++; $v = 'ok    ' } else { $script:fail++; $v = 'FAILED' }
    '  {0} {1}: mouseSmoothing / cameraBlend = {2} (want {3})' -f $v, $what, $got, $want
}
Case 'neither key in the file: the defaults, both on' '' '0.08 0.5'
Case 'both keys' "mouseSmoothing: 0.15`ncameraBlend: 1.2" '0.15 1.2'
Case 'keys in other letter case, a comment after the value' "MOUSESMOOTHING: 0.05   # light`nCameraBlend: 0.25" '0.05 0.25'
Case '0 = off' "mouseSmoothing: 0`ncameraBlend: 0" '0 0'
Case '"off" and "false" = 0' "mouseSmoothing: off`ncameraBlend: false" '0 0'
Case 'not a number (decimal comma, a word): the default' "mouseSmoothing: 0,2`ncameraBlend: fast" '0.08 0.5'
Case 'over the limits: 1 s and 3 s' "mouseSmoothing: 5`ncameraBlend: 60" '1 3'
Case 'negative: 0' "mouseSmoothing: -1`ncameraBlend: -0.5" '0 0'
Case 'a switch wins over the file' "mouseSmoothing: 0.15`ncameraBlend: 1.2" '0 2' @{ MouseSmoothing = 0; CameraBlend = 2 }
Case 'one switch, the other from the file' "cameraBlend: 1.2" '0.3 1.2' @{ MouseSmoothing = 0.3 }
Case 'a file without the keys (CamLab Launch): those of profiles.yaml next to the script' '' '0.2 0' @{} "mouseSmoothing: 0.2`ncameraBlend: 0"
Case 'a file with the keys: profiles.yaml next to the script does not count' "mouseSmoothing: 0.1`ncameraBlend: 0.4" '0.1 0.4' @{} "mouseSmoothing: 0.2`ncameraBlend: 0"
Remove-Item $dir -Recurse -Force -ErrorAction SilentlyContinue
"SETTINGS CHECKS: $pass passed, $fail failed"

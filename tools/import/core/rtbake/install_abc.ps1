# Puts built classic courses into the game as alternatives of the Classic mode's track (Desert4).
. (Join-Path $PSScriptRoot '..\..\..\..\extras.ps1') -NoWindow        # SR3 Extras' functions, no window
$tracks, $out = & python (Join-Path $PSScriptRoot '..\common.py') --paths tracks out          # from tools\import\settings.json
$set = @(@('step99_mountain_rt_a_desert4', 'Mountain RT'), @('step99_mountain_rt_b_desert4', 'Mountain RT soft'), @('step99_mountain_rt_c_desert4', 'Mountain RT (cars unshaded)'))
$list = @(); $k = 0
foreach ($e in $set) {
    $k++; $src = Join-Path $out "$($e[0])\Desert4"; $dst = Get-AltDir $tracks "$k" 'Desert4'
    if (-not (Test-Path $src)) { "missing $src"; continue }
    if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
    Copy-Item $src $dst -Recurse
    $list += @{ title = $e[1]; dir = "$k" }
    "{0} -> track{1}\Desert4 ({2} files, {3:N0} MB)" -f $e[1], $k, @(Get-ChildItem $dst -File).Count, ((Get-ChildItem $dst -File | Measure-Object Length -Sum).Sum / 1MB)
}
[IO.File]::WriteAllText((Join-Path (Get-StoreDir $tracks) 'classic.json'), (ConvertTo-Json @($list)))
$st = Read-ExtrasState $tracks; Write-SwitchFile $tracks $st
$j = Get-Content (Join-Path $tracks '_SR3Extras\switch.json') -Raw | ConvertFrom-Json
"switch.json Desert4: " + (($j.slots.Desert4.tracks | ForEach-Object { "$($_.dir)=$($_.title)" }) -join ', ')



























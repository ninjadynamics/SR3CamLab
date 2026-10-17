# install_track.ps1 -Build <built Desert4 folder> -Title <the name the game shows> [-Video <id>] [-Tracks <Main_release\tracks>]
# A built Classic course into SEGA Rally 3 as one alternative of the Classic mode's track (Desert4), beside the ones already there:
# a course with the same title takes the place of its earlier copy, a new one the lowest free number (Main_release\track1 .. track9).
# A track<N>\Desert4 folder the Classic list does not name is never touched. SR3 Extras' switch file is written again, so the
# game shows the course on its first menu the next time PLAY.bat starts it. The game must be closed. -Tracks: another copy of
# the game (tests); by default the game folder of tools\import\settings.json.
param([Parameter(Mandatory = $true)][string]$Build, [Parameter(Mandatory = $true)][string]$Title, [string]$Video = '', [string]$Tracks = '')
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\..\..\extras.ps1') -NoWindow        # SR3 Extras' functions, no window
if (-not $Tracks) { $Tracks = & (Find-Python) (Join-Path $PSScriptRoot 'common.py') --paths tracks }      # Find-Python (extras.ps1): the bundled one first
if (-not (Test-Path -LiteralPath (Join-Path $Tracks 'Desert4'))) { throw "no SEGA Rally 3 tracks folder at $Tracks (settings: sr3_game)" }
if (-not (Test-Path -LiteralPath (Join-Path $Build 'desert4_master_xdata.sbf'))) { throw "$Build is not a built track (no desert4_master_xdata.sbf)" }
Assert-GameClosed
$cf = Join-Path (Get-StoreDir $Tracks) 'classic.json'
$list = @()
if (Test-Path -LiteralPath $cf) { $list = @([IO.File]::ReadAllText($cf) | ConvertFrom-Json | ForEach-Object { $_ }) }
$old = @($list | Where-Object { "$($_.title)" -eq $Title })
if ($old.Count) { $k = "$($old[0].dir)" }
else {
    $used = @($list | ForEach-Object { "$($_.dir)" }); $k = ''
    foreach ($n in 1..9) { if ($used -notcontains "$n" -and -not (Test-Path -LiteralPath (Get-AltDir $Tracks "$n" 'Desert4'))) { $k = "$n"; break } }
    if (-not $k) { throw 'the Classic list is full (track1 .. track9 hold courses or folders it does not name); remove one in SR3 Extras first' }
}
$dst = Get-AltDir $Tracks $k 'Desert4'
if (Test-Path -LiteralPath $dst) { Remove-Item -LiteralPath $dst -Recurse -Force }
[void][IO.Directory]::CreateDirectory((Split-Path -Parent $dst)); Copy-Item -LiteralPath $Build -Destination $dst -Recurse
$entry = [ordered]@{ title = $Title; dir = $k; video = $(if ($Video) { $Video } elseif ($old.Count) { "$($old[0].video)" } else { '' }) }
$new = @(); $put = $false
foreach ($e in $list) { if ("$($e.title)" -eq $Title) { if (-not $put) { $new += $entry; $put = $true } } else { $new += $e } }
if (-not $put) { $new += $entry }
[void][IO.Directory]::CreateDirectory((Get-StoreDir $Tracks))
[IO.File]::WriteAllText($cf, (ConvertTo-Json @($new)))
$st = Read-ExtrasState $Tracks; Write-SwitchFile $Tracks $st
"{0} -> track{1}\Desert4 ({2} files, {3:N0} MB); the Classic list: {4}" -f $Title, $k, @(Get-ChildItem -LiteralPath $dst -File).Count, ((Get-ChildItem -LiteralPath $dst -File | Measure-Object Length -Sum).Sum / 1MB), (($new | ForEach-Object { "$($_.dir)=$($_.title)" }) -join ', ')

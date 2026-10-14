<#
  SR3Ultimate: extra content for SEGA Rally 3 (arcade). Start it with SR3Ultimate.bat.

  Tracks, two ways:
  - The three stage cards (Tropical, Canyon, Alpine) can hold ALTERNATIVE tracks. They sit beside
    the game's files (Main_release\track<k>\<slot>, a stage card video each) and replace nothing;
    PLAY.bat's track switcher points the running game at the one chosen with View Change on the
    stage-select screen. tracks\_SR3Extras\switch.json lists them for it.
  - Any other slot (Lakeside, Desert '95, Stadium) gets its track REPLACED, the way the community
    tutorial does it by hand: the track's files are copied over the slot's, renamed to the slot's
    names. The slot's own files are moved to tracks\_SR3Extras\original\<slot> first; Disable
    swaps them back in (the import waits in ...\parked\<slot>), Remove restores them for good.
  Sources: SEGA Rally Revo (PC, or PlayStation 3 disc files: converted to the PC layout by
  ps3conv.cs with the layouts in ps3model.txt) and SEGA Rally 3's own tracks.

  Pictures (menuart.cs): a Revo track's stage card video, banner and background are made from the
  card picture the game itself still carries; the videos need ffmpeg. The alternatives' banners
  and backgrounds are off by default (SR3Ultimate.bat -AltArt on / off).

  Announcer: the stage names of Revo's Arctic and Safari, from your own recordings in
  SR3CamLab\announcer\ (Arctic.wav, Safari.wav); see Update-Announcer.

  Race sounds of the alternative tracks (ambience, its zones, music): see Update-TrackSounds.

  Co-driver: another pace-note voice, SEGA Rally 2's or the 1995 SEGA Rally Championship's, from the clips
  in SR3CamLab\codriver\ (Options tab, or SR3Ultimate.bat -CoDriver sr3 / sr2 / src); see Set-CoDriverSource.

  Music: the 1995 SEGA Rally Championship's tunes for the 1995 courses in the Classic mode, from SR3CamLab\music\
  (Options tab, or SR3Ultimate.bat -Music sr3 / src). SEGA Rally 3's own stages and menus always keep their music;
  see Set-MusicSource.

  Nothing original is ever deleted; state.json in tracks\_SR3Extras remembers what is where.
#>
param([switch]$NoWindow, [ValidateSet('', 'on', 'off')][string]$AltArt = '',
      [ValidateSet('', 'on', 'off', 'sr3', 'sr2', 'src')][string]$CoDriver = '', [ValidateSet('', 'off', 'sr3', 'src')][string]$Music = '')

. (Join-Path $PSScriptRoot 'setup.ps1')

# ---- where things are ----
function Get-TracksDir([string]$gameExe) {
    if (-not (Test-FilePath $gameExe)) { return $null }
    $d = Join-Path (Split-Path -Parent $gameExe) 'Main_release\tracks'
    if (Test-Path -LiteralPath $d -PathType Container) { return $d }
    return $null
}
function Get-StoreDir([string]$tracks) { return (Join-Path $tracks '_SR3Extras') }

function Read-ExtrasState([string]$tracks) {
    $st = @{ revo = ''; slots = @{}; alts = @{}; art = $false; announcer = @{}; codriver = ''; music = '' }
    $f = Join-Path (Get-StoreDir $tracks) 'state.json'
    if (Test-Path -LiteralPath $f) {
        try {
            $j = [IO.File]::ReadAllText($f) | ConvertFrom-Json
            if ($j.revo) { $st.revo = "$($j.revo)" }
            if ($j.art) { $st.art = $true }
            if ($j.codriver) { $st.codriver = "$($j.codriver)" }
            if ($j.music) { $st.music = "$($j.music)" }
            if ($j.announcer) { foreach ($p in $j.announcer.PSObject.Properties) { $st.announcer[$p.Name] = "$($p.Value)" } }
            if ($j.alts) {
                foreach ($p in $j.alts.PSObject.Properties) {
                    $list = New-Object System.Collections.ArrayList
                    foreach ($a in @($p.Value)) { [void]$list.Add(@{ id = "$($a.id)"; track = "$($a.track)"; origin = "$($a.origin)"; source = "$($a.source)"; dir = "$($a.dir)"; video = "$($a.video)"; title = "$($a.title)" }) }
                    $st.alts[$p.Name] = $list
                }
            }
            if ($j.slots) { foreach ($p in $j.slots.PSObject.Properties) { $st.slots[$p.Name] = @{ source = "$($p.Value.source)"; enabled = [bool]$p.Value.enabled; track = "$($p.Value.track)"; origin = "$($p.Value.origin)" } } }
        } catch { }
    }
    # Whose co-driver is in the game: the kept originals decide (no folder = the game's own). A co-driver put in
    # before the choice was written down is SEGA Rally 2's, the only one there was. Music: what music.json says was
    # appended to the stream file, when the file really ends with it (Get-MusicInstall).
    if (-not (Test-Path -LiteralPath (Join-Path (Get-StoreDir $tracks) 'original\codriver'))) { $st.codriver = '' } elseif (-not $st.codriver) { $st.codriver = 'sr2' }
    $m = Get-MusicInstall (Split-Path -Parent (Split-Path -Parent $tracks)); $st.music = $(if ($m) { $m.source } else { '' })
    return $st
}
function Write-ExtrasState([string]$tracks, $st) {
    $store = Get-StoreDir $tracks
    [void][IO.Directory]::CreateDirectory($store)
    [IO.File]::WriteAllText((Join-Path $store 'state.json'), ($st | ConvertTo-Json -Depth 5))
}

# ---- track folders ----
# A track's files start with one of two prefixes: "<xxx>_track_route<N>" and "<name><N>"
# (alp_track_route4_... and alpine4_...). Returns both, as found in a folder.
function Get-TrackTokens([string]$dir) {
    $route = $null; $env = $null
    foreach ($f in Get-ChildItem -LiteralPath $dir -File -ErrorAction SilentlyContinue) {
        if (-not $route -and $f.Name -match '^([A-Za-z]+_track_route\d+)_') { $route = $Matches[1] }
        if (-not $env -and $f.Name -match '^([A-Za-z]+\d+)_master') { $env = $Matches[1] }
    }
    if ($route -and $env) { return @{ Route = $route; Env = $env } }
    return $null
}
function Get-TrackFiles([string]$dir, $tokens) {
    return @(Get-ChildItem -LiteralPath $dir -File | Where-Object {
        $_.Name.StartsWith($tokens.Route + '_', [StringComparison]::OrdinalIgnoreCase) -or $_.Name.StartsWith($tokens.Env + '_', [StringComparison]::OrdinalIgnoreCase) })
}
# 'pc' = same format as the arcade game, 'ps3' = console format (converted on import), 'unknown'
function Get-TrackKind([string]$dir) {
    if (@(Get-ChildItem -LiteralPath $dir -Filter '*.vbf' -File -ErrorAction SilentlyContinue).Count) { return 'ps3' }
    $f = Get-ChildItem -LiteralPath $dir -Filter '*_master_xdata.sbf' -File -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $f) { return 'unknown' }
    try {
        $fs = [IO.File]::OpenRead($f.FullName)
        try {
            $head = New-Object byte[] 10; [void]$fs.Read($head, 0, 10)
            if ([Text.Encoding]::ASCII.GetString($head, 0, 4) -ne 'SBZ1') { return 'unknown' }
            $fs.Position = 10                                         # past "SBZ1", the size and the 2-byte zlib header
            $z = New-Object IO.Compression.DeflateStream($fs, [IO.Compression.CompressionMode]::Decompress)
            $w = New-Object byte[] 4; [void]$z.Read($w, 0, 4)
            if ($w[0] -eq 4 -and $w[3] -eq 0) { return 'pc' }
            if ($w[0] -eq 0 -and $w[3] -eq 4) { return 'ps3' }
        } finally { $fs.Dispose() }
    } catch { }
    return 'unknown'
}
# The folder that holds the track folders, given a game folder (or any folder above / at it)
function Find-TracksFolder([string]$path) {
    if (-not $path -or -not (Test-Path -LiteralPath $path -PathType Container)) { return $null }
    $tries = @('', 'out\main release\tracks', 'out\main_release\tracks', 'main release\tracks', 'main_release\tracks', 'tracks',
               'PS3_GAME\USRDIR\main_release\tracks', 'USRDIR\main_release\tracks')
    foreach ($t in $tries) {
        $d = if ($t) { Join-Path $path $t } else { $path }
        if (-not (Test-Path -LiteralPath $d -PathType Container)) { continue }
        foreach ($sub in Get-ChildItem -LiteralPath $d -Directory -ErrorAction SilentlyContinue) { if (Get-TrackTokens $sub.FullName) { return $d } }
    }
    return $null
}

# The slots: SEGA Rally 3's own track folders. Where a slot's own files are right now depends on its state.
function Get-Slots([string]$tracks, $st) {
    $store = Get-StoreDir $tracks
    $list = New-Object System.Collections.ArrayList
    foreach ($d in Get-ChildItem -LiteralPath $tracks -Directory | Where-Object { $_.Name -ne '_SR3Extras' }) {
        $s = $st.slots[$d.Name]
        $origDir = if ($s -and $s.enabled) { Join-Path $store "original\$($d.Name)" } else { $d.FullName }
        $tok = Get-TrackTokens $origDir
        if (-not $tok) { continue }
        [void]$list.Add([pscustomobject]@{ Name = $d.Name; Dir = $d.FullName; OriginalDir = $origDir; Tokens = $tok
            Source = $(if ($s) { $s.source } else { '' }); Enabled = [bool]($s -and $s.enabled); Parked = [bool]($s -and -not $s.enabled) })
    }
    return ,$list
}
# Everything that can go into a slot: Revo's tracks, then SEGA Rally 3's own
function Get-Sources([string]$tracks, $st) {
    $list = New-Object System.Collections.ArrayList
    $revo = Find-TracksFolder $st.revo
    if ($revo) {
        foreach ($d in Get-ChildItem -LiteralPath $revo -Directory | Sort-Object Name) {
            $tok = Get-TrackTokens $d.FullName
            if (-not $tok) { continue }
            $kind = Get-TrackKind $d.FullName
            [void]$list.Add([pscustomobject]@{ Id = "revo:$($d.Name)"; Name = $d.Name; Dir = $d.FullName; Tokens = $tok; Kind = $kind; Origin = 'Revo' })
        }
    }
    $own = Get-Slots $tracks $st
    foreach ($s in $own) {
        [void]$list.Add([pscustomobject]@{ Id = "sr3:$($s.Name)"; Name = $s.Name; Dir = $s.OriginalDir; Tokens = $s.Tokens; Kind = 'pc'; Origin = 'SR3' })
    }
    return ,$list
}
function Get-SourceLabel($src) {
    $where = if ($src.Origin -eq 'SR3') { 'SEGA Rally 3' } else { 'Revo' }
    $note = switch ($src.Kind) { 'ps3' { '   (PS3)' } 'unknown' { '   (not recognised)' } default { '' } }
    return "$where  -  $($src.Name)$note"
}

# ---- the compiled parts: ps3conv.cs (PS3 track converter, file reader / writer) and menuart.cs (stage-select pictures) ----
function Import-ExtrasCode {
    if ('SR3Extras.MenuArt' -as [type]) { return }
    $files = @((Join-Path $PSScriptRoot 'ps3conv.cs'), (Join-Path $PSScriptRoot 'menuart.cs'), (Join-Path $PSScriptRoot 'revofix.cs'))
    foreach ($f in $files) { if (-not (Test-Path -LiteralPath $f)) { throw "SR3Ultimate is incomplete: $f is missing." } }
    Add-Type -AssemblyName System.Drawing
    Add-Type -Path $files -ReferencedAssemblies 'System.Core', 'System.Drawing'
}

# ---- the stage-select pictures ----
# The name shown on the stage card and banner: the environment, without the route number ("arctic2" -> "Arctic")
function Get-TrackTitle([string]$name) {
    $n = $name -replace '[0-9]+$', ''
    if (-not $n) { return $name }
    return $n.Substring(0, 1).ToUpper() + $n.Substring(1).ToLower()
}
# Rebuilds the game's menu pictures from the untouched original, so that every slot holding a
# SEGA Rally Revo track shows that track's name and scenery. With nothing imported, the original is put back.
# The stage cards are short videos, one per language: frontend\PC\Videos\LANG_<language>_<code>.wmv.
# A slot holding a Revo track gets a card made from that track's picture (6 s, slow zoom and pan, the
# track's name). Making a video needs ffmpeg; without it the slot keeps its own card.
$script:CardVideo = @{ Tropical4 = @{ Code = 'TRO'; Level = 'EASY' }; Canyon4 = @{ Code = 'CAN'; Level = 'MEDIUM' }; Alpine4 = @{ Code = 'ALP'; Level = 'HARD' } }
function Update-CardVideos([string]$game, [string]$store, $want, $cardFile, $named) {
    $dir = Join-Path $game 'frontend\PC\Videos'
    if (-not (Test-Path -LiteralPath $dir)) { return $null }
    $bakDir = Join-Path $store 'original\Videos'
    $ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue | Select-Object -First 1
    $note = $null
    foreach ($slot in $script:CardVideo.Keys) {
        $code = $script:CardVideo[$slot].Code
        $files = @(Get-ChildItem -LiteralPath $dir -Filter "LANG_*_$code.wmv" -File)
        $key = if ($want.ContainsKey($slot)) { 'TRACKSLIDE_' + $want[$slot].ToUpper() } else { '' }
        if (-not $key -or -not $named -or -not $named.ContainsKey($key) -or -not $ffmpeg) {
            # the slot's own cards come back
            foreach ($f in $files) { $b = Join-Path $bakDir $f.Name; if (Test-Path -LiteralPath $b) { [IO.File]::Copy($b, $f.FullName, $true); [IO.File]::Delete($b) } }
            if ($key -and -not $ffmpeg) { $note = "The stage cards are videos; to give them the new track's picture, install ffmpeg (ffmpeg.org) and import again." }
            continue
        }
        if ($files.Count -eq 0) { continue }
        $tmp = Join-Path $store 'tmp\card'; [void][IO.Directory]::CreateDirectory($tmp)
        $photo = Join-Path $tmp 'photo.png'; $over = Join-Path $tmp 'overlay.png'; $out = Join-Path $tmp 'card.wmv'
        $card = [SR3Extras.MenuArt]::Decode($cardFile, $named[$key])
        $p1 = [SR3Extras.MenuArt]::MakeCardPhoto($card); $p1.Save($photo); $p1.Dispose()
        $p2 = [SR3Extras.MenuArt]::MakeCardOverlay((Get-TrackTitle $want[$slot]), $script:CardVideo[$slot].Level); $p2.Save($over); $p2.Dispose(); $card.Dispose()
        # 6 seconds that loop, like the game's own cards: a slow zoom, a cross-fade into a slow pan, and a cross-fade back.
        # The picture is enlarged first so that the movement is smooth instead of stepping from pixel to pixel.
        $zp = 'd=1:s=640x360:fps=30'; $mid = "x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2'"
        $filter = "[0:v]scale=5120:2880:flags=bicubic,split=3[a0][b0][c0];" +
            "[a0]zoompan=z='1+0.10*(on+15)/105':${mid}:$zp,trim=end_frame=90,setpts=PTS-STARTPTS[A];" +
            "[b0]zoompan=z='1.12':x='(iw-iw/zoom)*on/104':y='ih/2-ih/zoom/2':$zp,trim=end_frame=105,setpts=PTS-STARTPTS[B];" +
            "[c0]zoompan=z='1+0.10*on/105':${mid}:$zp,trim=end_frame=16,setpts=PTS-STARTPTS[C];" +
            "[A][B]xfade=transition=fade:duration=0.5:offset=2.5[AB];[AB][C]xfade=transition=fade:duration=0.5:offset=5.5[bg];[bg][1:v]overlay=0:0,format=yuv420p"
        if (Test-Path -LiteralPath $out) { [IO.File]::Delete($out) }
        & $ffmpeg.Source -v error -y -loop 1 -framerate 30 -t 8 -i $photo -loop 1 -framerate 30 -t 8 -i $over -filter_complex $filter -t 6 -c:v wmv2 -b:v 9M -an $out 2>$null
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $out) -or (Get-Item -LiteralPath $out).Length -lt 100000) { $note = "ffmpeg couldn't make the stage card video for $($want[$slot]); that slot keeps its own card."; continue }
        [void][IO.Directory]::CreateDirectory($bakDir)
        foreach ($f in $files) {
            $b = Join-Path $bakDir $f.Name
            if (-not (Test-Path -LiteralPath $b)) { [IO.File]::Copy($f.FullName, $b) }
            [IO.File]::Copy($out, $f.FullName, $true)
        }
        Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    }
    if ((Test-Path -LiteralPath $bakDir) -and -not @(Get-ChildItem -LiteralPath $bakDir -File).Count) { [IO.Directory]::Delete($bakDir) }
    return $note
}
function Update-MenuArt([string]$tracks, $st) {
    $game = Split-Path -Parent (Split-Path -Parent $tracks)
    $file = Join-Path $game 'frontend\arcade permanent resources_data.sbf'
    $cards = Join-Path $game 'frontend\frontend track cards_data.sbf'
    $bak = Join-Path (Get-StoreDir $tracks) 'original\arcade permanent resources_data.sbf'
    if (-not (Test-Path -LiteralPath $file)) { return "The game's menu pictures weren't found, so the slots keep their own." }
    # replaced slots: the slot's own two pictures are redrawn
    $want = @{}
    foreach ($slot in @($st.slots.Keys)) {
        $s = $st.slots[$slot]
        if ($s.enabled -and $s.track -and $s.origin -eq 'Revo') { $want[$slot] = $s.track }
    }
    # stage-card alternatives (only when switched on, see Set-AltArt): a second set of names per track
    # folder number, "BKG<k>_NAME_<slot>" and "MENU_BANNE<k>_<slot>", which PLAY.bat's track switcher
    # makes the game ask for while an alternative from track<k> is the current track
    $dirs = @{}
    if ($st.art) { foreach ($slot in @($st.alts.Keys)) { foreach ($a in $st.alts[$slot]) { if (-not $dirs.ContainsKey($a.dir)) { $dirs[$a.dir] = @{} }; $dirs[$a.dir][$slot] = $a } } }
    if ($want.Count -eq 0 -and $dirs.Count -eq 0) {
        if (Test-Path -LiteralPath $bak) { [IO.File]::Copy($bak, $file, $true); [IO.File]::Delete($bak) }
        [void](Update-CardVideos $game (Get-StoreDir $tracks) $want $null $null)
        return $null
    }
    if (-not (Test-Path -LiteralPath $cards)) { return "The game's track cards file is missing, so the slots keep their own pictures." }
    Import-ExtrasCode
    if (-not (Test-Path -LiteralPath $bak)) { [void][IO.Directory]::CreateDirectory((Split-Path -Parent $bak)); [IO.File]::Copy($file, $bak) }
    $cardFile = New-Object SR3Extras.Sbf($cards, $false)
    $named = [SR3Extras.MenuArt]::Named($cardFile)
    $skipped = @()
    $cur = $bak; $n = 0
    $step = {
        param($work)                                              # $work: (source file, target file) -> writes the target
        $script:MenuStep++; $t = "$file.new$($script:MenuStep)"
        & $work $cur $t
        if ($cur -ne $bak) { [IO.File]::Delete($cur) }
        return $t
    }
    $script:MenuStep = 0
    try {
        if ($want.Count) {
            $pics = New-Object 'System.Collections.Generic.Dictionary[string,System.Drawing.Bitmap]'
            try {
                foreach ($slot in $want.Keys) {
                    $key = 'TRACKSLIDE_' + $want[$slot].ToUpper()
                    if (-not $named.ContainsKey($key)) { $skipped += $want[$slot]; continue }
                    $card = [SR3Extras.MenuArt]::Decode($cardFile, $named[$key])
                    $pics["BKGD_NAME_$slot"] = [SR3Extras.MenuArt]::MakeBackground($card)
                    $pics["MENU_BANNER_$slot"] = [SR3Extras.MenuArt]::MakeBanner($card, (Get-TrackTitle $want[$slot]))
                    $card.Dispose()
                }
                $cur = & $step { param($a, $b) [SR3Extras.MenuArt]::Replace($a, $b, $pics) }
            } finally { foreach ($b in $pics.Values) { $b.Dispose() } }
        }
        $menuFile = $null; $menuNamed = $null
        foreach ($k in @($dirs.Keys | Sort-Object)) {
            $pics = New-Object 'System.Collections.Generic.Dictionary[string,System.Drawing.Bitmap]'
            try {
                foreach ($slot in $dirs[$k].Keys) {
                    $a = $dirs[$k][$slot]
                    $key = 'TRACKSLIDE_' + "$($a.track)".ToUpper()
                    # the background is a blur: a quarter of the size shows the same and keeps the file small
                    # (the game does not start with this file much bigger than it was)
                    if ($a.origin -ne 'Revo' -or -not $named.ContainsKey($key)) {          # no card art: the slot's own pictures
                        if (-not $menuFile) { $menuFile = New-Object SR3Extras.Sbf($bak, $false); $menuNamed = [SR3Extras.MenuArt]::Named($menuFile) }
                        if (-not $menuNamed.ContainsKey("BKGD_NAME_$slot") -or -not $menuNamed.ContainsKey("MENU_BANNER_$slot")) { continue }
                        $full = [SR3Extras.MenuArt]::Decode($menuFile, $menuNamed["BKGD_NAME_$slot"])
                        $pics["BKG${k}_NAME_$slot"] = New-Object System.Drawing.Bitmap($full, 320, 180); $full.Dispose()
                        $pics["MENU_BANNE${k}_$slot"] = [SR3Extras.MenuArt]::Decode($menuFile, $menuNamed["MENU_BANNER_$slot"])
                        continue
                    }
                    $card = [SR3Extras.MenuArt]::Decode($cardFile, $named[$key])
                    $full = [SR3Extras.MenuArt]::MakeBackground($card)
                    $pics["BKG${k}_NAME_$slot"] = New-Object System.Drawing.Bitmap($full, 320, 180); $full.Dispose()
                    $pics["MENU_BANNE${k}_$slot"] = [SR3Extras.MenuArt]::MakeBanner($card, (Get-TrackTitle $a.track))
                    $card.Dispose()
                }
                $rename = New-Object 'System.Collections.Generic.Dictionary[string,string]'
                $rename['BKGD_NAME_'] = "BKG${k}_NAME_"; $rename['MENU_BANNER_'] = "MENU_BANNE${k}_"
                $cur = & $step { param($a, $b) [void][SR3Extras.MenuArt]::AddNames($a, $b, $rename, $pics) }
            } finally { foreach ($b in $pics.Values) { $b.Dispose() } }
        }
        if ($cur -ne $bak) { [IO.File]::Copy($cur, $file, $true); [IO.File]::Delete($cur) } else { [IO.File]::Copy($bak, $file, $true) }
    } catch {
        if ($cur -ne $bak -and (Test-Path -LiteralPath $cur)) { [IO.File]::Delete($cur) }
        throw
    }
    $videoNote = Update-CardVideos $game (Get-StoreDir $tracks) $want $cardFile $named
    if ($skipped.Count) { return "No card picture found for $($skipped -join ', '); that slot keeps its own." }
    return $videoNote
}
# The alternatives' own banners and backgrounds: off until switched on (it rewrites the game's menu
# pictures file with extra names; the original is kept and comes back when it is switched off).
function Set-AltArt([string]$tracks, [bool]$on) {
    Assert-GameClosed
    $st = Read-ExtrasState $tracks
    $st.art = $on
    Write-ExtrasState $tracks $st
    $n = Update-MenuArt $tracks $st
    Write-SwitchFile $tracks $st
    return $n
}

# ---- the PS3 converter ----
# Compiled the first time a PS3 track is imported.
function Get-Ps3Model {
    if (-not $script:Ps3Model) {
        $cs = Join-Path $PSScriptRoot 'ps3conv.cs'; $model = Join-Path $PSScriptRoot 'ps3model.txt'
        foreach ($f in $cs, $model) { if (-not (Test-Path -LiteralPath $f)) { throw "The PlayStation 3 converter is incomplete: $f is missing." } }
        Import-ExtrasCode
        $script:Ps3Model = [SR3Extras.Model]::Load($model)
    }
    return $script:Ps3Model
}
# Converts the PS3 track in $src into $dst, named for $slot. Returns notes for the user.
function Convert-Ps3Track($src, $slot, [string]$dst) {
    $model = Get-Ps3Model                                         # also loads the converter's types
    # converted first into a folder of its own, then fitted to the arcade game (revofix.cs): Revo has two
    # shaders the arcade game lacks, and what uses them (finish banners, some bushes) would not be drawn
    $raw = "$dst.converted"
    if (Test-Path -LiteralPath $raw) { Remove-Item -LiteralPath $raw -Recurse -Force }
    try {
        $r = [SR3Extras.Ps3Conv]::ConvertTrack($model, $src.Dir, $raw, $src.Tokens.Route, $src.Tokens.Env, $slot.Tokens.Route, $slot.Tokens.Env)
        if ($r.Files -lt 6) { throw "'$($src.Name)' is missing track files: only $($r.Files) could be converted." }
        $fix = [SR3Extras.RevoFix]::FixTrack($raw, $dst, $true, $false, $false)
        $script:LastRevoFix = $fix
    } finally { if (Test-Path -LiteralPath $raw) { Remove-Item -LiteralPath $raw -Recurse -Force } }
    return @($r.Notes)
}

# ---- the operations ----
function Assert-GameClosed { if (Get-Process -Name Rally -ErrorAction SilentlyContinue) { throw 'SEGA Rally 3 is running. Close the game first.' } }
function Move-AllFiles([string]$from, [string]$to) {
    [void][IO.Directory]::CreateDirectory($to)
    foreach ($f in Get-ChildItem -LiteralPath $from -File) { [IO.File]::Move($f.FullName, (Join-Path $to $f.Name)) }
}
function Remove-AllFiles([string]$dir) { foreach ($f in Get-ChildItem -LiteralPath $dir -File -ErrorAction SilentlyContinue) { [IO.File]::Delete($f.FullName) } }
function Test-HasFiles([string]$dir) { return [bool]((Test-Path -LiteralPath $dir) -and @(Get-ChildItem -LiteralPath $dir -File).Count) }

# Puts $src into $slot. Returns notes for the user (files the slot had that the new track lacks, and the like).
function Import-Track([string]$tracks, $st, $slot, $src) {
    Assert-GameClosed
    if ($src.Kind -notin 'pc', 'ps3') { throw "'$($src.Name)' isn't a track SR3Ultimate recognises." }
    if ($src.Id -eq "sr3:$($slot.Name)") { throw "That is the track this slot already has. Use Remove to get it back." }
    $store = Get-StoreDir $tracks
    $orig = Join-Path $store "original\$($slot.Name)"; $parked = Join-Path $store "parked\$($slot.Name)"; $tmp = Join-Path $store "tmp\$($slot.Name)"
    $notes = New-Object System.Collections.ArrayList

    # 1) build the renamed copy first: nothing in the game changes if this fails
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
    [void][IO.Directory]::CreateDirectory($tmp)
    if ($src.Kind -eq 'ps3') {
        foreach ($n in Convert-Ps3Track $src $slot $tmp) { [void]$notes.Add($n) }
    } else {
        $files = Get-TrackFiles $src.Dir $src.Tokens
        if ($files.Count -eq 0) { throw "No track files found in $($src.Dir)." }
        foreach ($f in $files) {
            $n = $f.Name
            if ($n.StartsWith($src.Tokens.Route + '_', [StringComparison]::OrdinalIgnoreCase)) { $n = $slot.Tokens.Route + $n.Substring($src.Tokens.Route.Length) }
            else { $n = $slot.Tokens.Env + $n.Substring($src.Tokens.Env.Length) }
            [IO.File]::Copy($f.FullName, (Join-Path $tmp $n), $true)
        }
    }

    # 2) the slot's own files go to the store (once); an earlier import is replaced
    if ($slot.Enabled) {
        if (-not (Test-HasFiles $orig)) { throw "The saved original files of $($slot.Name) are missing from $orig. Not touching the slot." }
        Remove-AllFiles $slot.Dir
    } else {
        if (Test-HasFiles $orig) { throw "$orig already holds files, but the slot isn't marked as replaced. Not touching it; check that folder." }
        Move-AllFiles $slot.Dir $orig
    }
    if (Test-Path -LiteralPath $parked) { Remove-Item -LiteralPath $parked -Recurse -Force }
    # 3) the new track goes in
    Move-AllFiles $tmp $slot.Dir
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    $st.slots[$slot.Name] = @{ source = (Get-SourceLabel $src).Trim(); enabled = $true; track = $src.Name; origin = $src.Origin }
    Write-ExtrasState $tracks $st
    $n = Update-MenuArt $tracks $st; if ($n) { [void]$notes.Add($n) }
    return ,$notes
}
function Disable-Track([string]$tracks, $st, $slot) {
    Assert-GameClosed
    if (-not $slot.Enabled) { throw "$($slot.Name) has its own track." }
    $store = Get-StoreDir $tracks
    $orig = Join-Path $store "original\$($slot.Name)"; $parked = Join-Path $store "parked\$($slot.Name)"
    if (-not (Test-HasFiles $orig)) { throw "The saved original files of $($slot.Name) are missing from $orig. Not touching the slot." }
    if (Test-Path -LiteralPath $parked) { Remove-Item -LiteralPath $parked -Recurse -Force }
    Move-AllFiles $slot.Dir $parked
    Move-AllFiles $orig $slot.Dir
    $st.slots[$slot.Name].enabled = $false
    Write-ExtrasState $tracks $st
    [void](Update-MenuArt $tracks $st)
}
function Enable-Track([string]$tracks, $st, $slot) {
    Assert-GameClosed
    if (-not $slot.Parked) { throw "$($slot.Name) has no disabled track to switch back on." }
    $store = Get-StoreDir $tracks
    $orig = Join-Path $store "original\$($slot.Name)"; $parked = Join-Path $store "parked\$($slot.Name)"
    if (-not (Test-HasFiles $parked)) { throw "The disabled track's files are missing from $parked." }
    if (Test-HasFiles $orig) { throw "$orig already holds files. Not touching the slot; check that folder." }
    Move-AllFiles $slot.Dir $orig
    Move-AllFiles $parked $slot.Dir
    $st.slots[$slot.Name].enabled = $true
    Write-ExtrasState $tracks $st
    [void](Update-MenuArt $tracks $st)
}
# Back to the game's own track; the imported one is deleted.
function Remove-Track([string]$tracks, $st, $slot) {
    Assert-GameClosed
    if (-not ($slot.Enabled -or $slot.Parked)) { throw "$($slot.Name) has its own track." }
    $store = Get-StoreDir $tracks
    $orig = Join-Path $store "original\$($slot.Name)"; $parked = Join-Path $store "parked\$($slot.Name)"
    if ($slot.Enabled) {
        if (-not (Test-HasFiles $orig)) { throw "The saved original files of $($slot.Name) are missing from $orig. Not touching the slot." }
        Remove-AllFiles $slot.Dir
        Move-AllFiles $orig $slot.Dir
    }
    foreach ($d in $orig, $parked) { if (Test-Path -LiteralPath $d) { Remove-Item -LiteralPath $d -Recurse -Force } }
    $st.slots.Remove($slot.Name)
    Write-ExtrasState $tracks $st
    [void](Update-MenuArt $tracks $st)
}

# ---- alternative tracks for the stage cards ----
# The three stage-select cards can hold more tracks than their own. An alternative lives beside the
# game's files and replaces nothing:
#   <game>\Main_release\track<k>\<slot>\      the track, named like the slot's own files (k = 1..9)
#   <game>\frontend\PC\Videos\LANG_<language>_<code><k>.wmv   its stage card (code: TR, CA, AL)
# tracks\_SR3Extras\switch.json lists them for PLAY.bat, whose track switcher points the running
# game at the chosen one (View Change on the stage-select screen).
$script:CardSlots = @{ Tropical4 = @{ Code = 'TR'; Own = 'TRO'; Title = 'Tropical'; Level = 'EASY' }
                       Canyon4   = @{ Code = 'CA'; Own = 'CAN'; Title = 'Canyon';   Level = 'MEDIUM' }
                       Alpine4   = @{ Code = 'AL'; Own = 'ALP'; Title = 'Alpine';   Level = 'HARD' } }
function Test-CardSlot([string]$slot) { return $script:CardSlots.ContainsKey($slot) }
function Get-GameDir([string]$tracks) { return (Split-Path -Parent (Split-Path -Parent $tracks)) }
function Get-AltDir([string]$tracks, [string]$k, [string]$slot) { return (Join-Path (Get-GameDir $tracks) "Main_release\track$k\$slot") }
# "arctic2" -> "Arctic 2" (the name the switcher shows; the card itself says just "Arctic")
function Get-TrackLabel([string]$name) {
    if ($name -match '^([A-Za-z]+?)(\d+)$') { return $Matches[1].Substring(0, 1).ToUpper() + $Matches[1].Substring(1).ToLower() + ' ' + $Matches[2] }
    return $name
}
# The announcer's clip for a track's name. SEGA Rally 3 has one per environment of its own. Revo's
# Arctic and Safari were never recorded: they get your recording when there is one (see
# Update-Announcer), the "Secret" clip otherwise.
function Get-TrackSpeech([string]$name, $st) {
    switch -Regex ($name) {
        '^tropical' { return 'SP_Tropical' }
        '^alpine'   { return 'SP_Alpine' }
        '^canyon'   { return 'SP_Canyon' }
        '^lakeside' { return 'SP_Lakeside' }
        '^desert'   { return 'SP_Desert95' }
        '^stadium'  { return 'SP_Stadium' }
    }
    $env = ($name -replace '\d+$', '').ToLower()
    if ($st -and $st.announcer -and $st.announcer[$env]) { return $st.announcer[$env] }
    return 'SP_Secret'
}
function Get-Alternatives($st, [string]$slot) {
    if (-not $st.alts.ContainsKey($slot)) { $st.alts[$slot] = New-Object System.Collections.ArrayList }
    return ,$st.alts[$slot]
}
# Which 1995 course an alternative of the Classic slot is: 'desert', 'forest', 'mountain', 'lakeside', or '' for anything
# else. The importer leaves texmap.json in the folder of every course it builds; its first lines name the game and the
# course the textures came from (...\courses\src\course1_mountain\...). Without that file the title decides.
function Get-ClassicCourse([string]$tracks, [string]$dir, [string]$title) {
    $name = $title; $f = Join-Path (Get-AltDir $tracks $dir 'Desert4') 'texmap.json'
    if (Test-Path -LiteralPath $f) {
        $b = New-Object byte[] 600; $fs = [IO.File]::OpenRead($f)
        try { $n = $fs.Read($b, 0, 600) } finally { $fs.Dispose() }
        $head = [Text.Encoding]::ASCII.GetString($b, 0, $n)
        if ($head -match 'courses[\\/]+src[\\/]+course\d+_([a-z]+)') { $name = $Matches[1] }
        elseif ($head -match 'courses[\\/]+[a-z0-9]+[\\/]+course') { return '' }               # a course of another game
    } elseif ($title -match 'SR2|Rally 2') { return '' }
    foreach ($c in $script:TuneCourses) { if ($name -match $c.Match) { return $c.Key } }
    return ''
}
# Where the tune of a Classic alternative is, for the switcher (patch.ps1, Set-CourseTune): only a 1995 course whose own
# tune was appended to the stream file gets one ($m = Get-MusicInstall). Every other track plays its slot's music.
function Get-ClassicTune([string]$tracks, $m, [string]$dir, [string]$title) {
    if (-not $m) { return $null }
    $course = Get-ClassicCourse $tracks $dir $title
    if (-not $course) { return $null }
    foreach ($t in @($m.tunes)) { if ("$($t.course)" -eq $course) { return @{ stream = [int]$m.stream; offset = [long]"$($t.offset)"; bytes = [long]"$($t.bytes)"; loopstart = [long]"$($t.loopstart)" } } }
    return $null
}
function Write-SwitchFile([string]$tracks, $st) {
    $file = Join-Path (Get-StoreDir $tracks) 'switch.json'
    $slots = @{}; $sounds = Read-TrackSounds $tracks
    foreach ($slot in @($st.alts.Keys)) {
        if (-not (Test-CardSlot $slot) -or $st.alts[$slot].Count -eq 0) { continue }
        $slots[$slot] = @{ title = $script:CardSlots[$slot].Title; speech = (Get-TrackSpeech $slot $st)
                           tracks = @($st.alts[$slot] | ForEach-Object { $snd = $sounds["$slot/$($_.dir)"]; if (-not $snd) { $snd = @{ ambience = ''; music = ''; events = '' } }
                               @{ title = $_.title; dir = $_.dir; video = $_.video; speech = (Get-TrackSpeech $_.track $st); ambience = $snd.ambience; music = $snd.music; events = $snd.events } }) }
    }
    # the Classic mode's track (Desert4) has no stage card: its alternatives are listed in classic.json
    # ([{ title, dir, video }], files in Main_release\track<dir>\Desert4) and stepped through on the game's first menu;
    # video = the mode menu's Classic card for that track, frontend\PC\Videos\classic_<video>.wmv (the launcher's Classic card)
    $cf = Join-Path (Get-StoreDir $tracks) 'classic.json'
    if (Test-Path -LiteralPath $cf) {
        try {
            $c = @([IO.File]::ReadAllText($cf) | ConvertFrom-Json | ForEach-Object { $_ } | Where-Object { "$($_.dir)" -match '^[1-9]$' -and (Test-Path -LiteralPath (Get-AltDir $tracks "$($_.dir)" 'Desert4')) })
            $m = Get-MusicInstall (Get-GameDir $tracks)
            if ($c.Count) { $slots['Desert4'] = @{ title = "Desert '95"; speech = ''; tracks = @($c | ForEach-Object {
                $v = if ("$($_.video)" -match '^[A-Za-z0-9]{1,8}$') { "$($_.video)" } else { '' }
                $e = @{ title = "$($_.title)"; dir = "$($_.dir)"; video = $v; speech = ''; ambience = ''; music = ''; events = '' }
                $t = Get-ClassicTune $tracks $m "$($_.dir)" "$($_.title)"; if ($t) { $e.tune = $t }
                $e }) } }
        } catch { }
    }
    if ($slots.Count -eq 0) { if (Test-Path -LiteralPath $file) { [IO.File]::Delete($file) }; return }
    [void][IO.Directory]::CreateDirectory((Get-StoreDir $tracks))
    [IO.File]::WriteAllText($file, (@{ art = [bool]$st.art; slots = $slots } | ConvertTo-Json -Depth 6))
}
# Copies (or converts) $src's files into $dst, named for $slot. Returns notes for the user.
function Copy-TrackForSlot($src, $slot, [string]$dst) {
    $notes = @()
    if ($src.Kind -eq 'ps3') { $notes += @(Convert-Ps3Track $src $slot $dst) }
    else {
        $files = Get-TrackFiles $src.Dir $src.Tokens
        if ($files.Count -eq 0) { throw "No track files found in $($src.Dir)." }
        foreach ($f in $files) {
            $n = $f.Name
            if ($n.StartsWith($src.Tokens.Route + '_', [StringComparison]::OrdinalIgnoreCase)) { $n = $slot.Tokens.Route + $n.Substring($src.Tokens.Route.Length) }
            else { $n = $slot.Tokens.Env + $n.Substring($src.Tokens.Env.Length) }
            [IO.File]::Copy($f.FullName, (Join-Path $dst $n), $true)
        }
    }
    return ,$notes
}
# Makes the stage card video of a Revo track (6 s that loop: a slow zoom, a cross-fade into a slow
# pan and a cross-fade back) from the card picture the game carries. Returns $true when $out exists.
function New-CardVideo([string]$game, [string]$track, [string]$level, [string]$out, [string]$work) {
    $ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue | Select-Object -First 1
    $cards = Join-Path $game 'frontend\frontend track cards_data.sbf'
    if (-not $ffmpeg -or -not (Test-Path -LiteralPath $cards)) { return $false }
    Import-ExtrasCode
    $cardFile = New-Object SR3Extras.Sbf($cards, $false); $named = [SR3Extras.MenuArt]::Named($cardFile)
    $key = 'TRACKSLIDE_' + $track.ToUpper()
    if (-not $named.ContainsKey($key)) { return $false }
    [void][IO.Directory]::CreateDirectory($work)
    $photo = Join-Path $work 'photo.png'; $over = Join-Path $work 'overlay.png'
    $card = [SR3Extras.MenuArt]::Decode($cardFile, $named[$key])
    $p1 = [SR3Extras.MenuArt]::MakeCardPhoto($card); $p1.Save($photo); $p1.Dispose()
    $p2 = [SR3Extras.MenuArt]::MakeCardOverlay((Get-TrackTitle $track), $level); $p2.Save($over); $p2.Dispose(); $card.Dispose()
    # the picture is enlarged first so that the movement is smooth instead of stepping from pixel to pixel
    $zp = 'd=1:s=640x360:fps=30'; $mid = "x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2'"
    $filter = "[0:v]scale=5120:2880:flags=bicubic,split=3[a0][b0][c0];" +
        "[a0]zoompan=z='1+0.10*(on+15)/105':${mid}:$zp,trim=end_frame=90,setpts=PTS-STARTPTS[A];" +
        "[b0]zoompan=z='1.12':x='(iw-iw/zoom)*on/104':y='ih/2-ih/zoom/2':$zp,trim=end_frame=105,setpts=PTS-STARTPTS[B];" +
        "[c0]zoompan=z='1+0.10*on/105':${mid}:$zp,trim=end_frame=16,setpts=PTS-STARTPTS[C];" +
        "[A][B]xfade=transition=fade:duration=0.5:offset=2.5[AB];[AB][C]xfade=transition=fade:duration=0.5:offset=5.5[bg];[bg][1:v]overlay=0:0,format=yuv420p"
    if (Test-Path -LiteralPath $out) { [IO.File]::Delete($out) }
    & $ffmpeg.Source -v error -y -loop 1 -framerate 30 -t 8 -i $photo -loop 1 -framerate 30 -t 8 -i $over -filter_complex $filter -t 6 -c:v wmv2 -b:v 9M -an $out 2>$null
    $ok = ($LASTEXITCODE -eq 0) -and (Test-Path -LiteralPath $out) -and ((Get-Item -LiteralPath $out).Length -gt 100000)
    foreach ($f in $photo, $over) { if (Test-Path -LiteralPath $f) { [IO.File]::Delete($f) } }
    return $ok
}
# Adds $src to a stage card as an alternative. Returns notes for the user.
function Add-Alternative([string]$tracks, $st, $slot, $src) {
    Assert-GameClosed
    if (-not (Test-CardSlot $slot.Name)) { throw "$($slot.Name) isn't one of the stage-select cards." }
    if ($src.Kind -notin 'pc', 'ps3') { throw "'$($src.Name)' isn't a track SR3Ultimate recognises." }
    if ($src.Id -eq "sr3:$($slot.Name)") { throw "That is this card's own track; it is always there." }
    $list = Get-Alternatives $st $slot.Name
    if (@($list | Where-Object { $_.id -eq $src.Id }).Count) { throw "'$($src.Name)' is already on the $($script:CardSlots[$slot.Name].Title) card." }
    $k = 1..9 | Where-Object { $n = "$_"; -not @($list | Where-Object { $_.dir -eq $n }).Count } | Select-Object -First 1
    if (-not $k) { throw "The $($script:CardSlots[$slot.Name].Title) card already has nine alternatives; remove one first." }
    $k = "$k"
    $game = Get-GameDir $tracks; $store = Get-StoreDir $tracks
    $notes = New-Object System.Collections.ArrayList
    $tmp = Join-Path $store "tmp\$($slot.Name)"
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
    [void][IO.Directory]::CreateDirectory($tmp)
    foreach ($n in (Copy-TrackForSlot $src $slot $tmp)) { [void]$notes.Add($n) }
    $dst = Get-AltDir $tracks $k $slot.Name
    if (Test-Path -LiteralPath $dst) { Remove-Item -LiteralPath $dst -Recurse -Force }
    Move-AllFiles $tmp $dst
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
    # the stage card
    $video = ''
    $vdir = Join-Path $game 'frontend\PC\Videos'
    $own = @(Get-ChildItem -LiteralPath $vdir -Filter "LANG_*_$($script:CardSlots[$slot.Name].Own).wmv" -File -ErrorAction SilentlyContinue)
    if ($own.Count) {
        $code = $script:CardSlots[$slot.Name].Code + $k; $made = Join-Path $store 'tmp\card.wmv'
        $ok = $false
        if ($src.Origin -eq 'Revo') { $ok = New-CardVideo $game $src.Name $script:CardSlots[$slot.Name].Level $made (Join-Path $store 'tmp\card') }
        elseif ($script:CardSlots.ContainsKey($src.Name)) {           # another card's own track: its own video
            $other = Join-Path $vdir ($own[0].Name -replace "_$($script:CardSlots[$slot.Name].Own)\.wmv$", "_$($script:CardSlots[$src.Name].Own).wmv")
            if (Test-Path -LiteralPath $other) { [IO.File]::Copy($other, $made, $true); $ok = $true }
        }
        if ($ok) {
            foreach ($f in $own) { [IO.File]::Copy($made, (Join-Path $vdir ($f.Name -replace "_$($script:CardSlots[$slot.Name].Own)\.wmv$", "_$code.wmv")), $true) }
            [IO.File]::Delete($made); $video = $code
        } elseif ($src.Origin -eq 'Revo' -and -not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
            [void]$notes.Add("The stage cards are videos; without ffmpeg (ffmpeg.org) this track shows the card's own video.")
        } else { [void]$notes.Add("No card video could be made for this track; it shows the card's own video.") }
    }
    $title = if ($src.Origin -eq 'Revo') { Get-TrackLabel $src.Name } elseif ($script:CardSlots.ContainsKey($src.Name)) { $script:CardSlots[$src.Name].Title } else { $src.Name -replace '\d+$', '' }
    [void]$list.Add(@{ id = $src.Id; track = $src.Name; origin = $src.Origin; source = (Get-SourceLabel $src).Trim(); dir = $k; video = $video; title = $title })
    foreach ($n in (Update-Announcer $tracks $st)) { [void]$notes.Add($n) }
    foreach ($n in (Update-TrackSounds $tracks $st)) { [void]$notes.Add($n) }
    Write-ExtrasState $tracks $st
    if ($st.art) { $n = Update-MenuArt $tracks $st; if ($n) { [void]$notes.Add($n) } }
    Write-SwitchFile $tracks $st
    return ,$notes
}
function Remove-Alternative([string]$tracks, $st, [string]$slot, [string]$k) {
    Assert-GameClosed
    $list = Get-Alternatives $st $slot
    $alt = $list | Where-Object { $_.dir -eq $k } | Select-Object -First 1
    if (-not $alt) { throw "That alternative isn't on the card any more." }
    $dir = Get-AltDir $tracks $k $slot
    if (Test-Path -LiteralPath $dir) { Remove-Item -LiteralPath $dir -Recurse -Force }
    $parent = Split-Path -Parent $dir
    if ((Test-Path -LiteralPath $parent) -and -not @(Get-ChildItem -LiteralPath $parent -Force).Count) { [IO.Directory]::Delete($parent) }
    if ($alt.video) {
        foreach ($f in Get-ChildItem -LiteralPath (Join-Path (Get-GameDir $tracks) 'frontend\PC\Videos') -Filter "LANG_*_$($alt.video).wmv" -File -ErrorAction SilentlyContinue) { [IO.File]::Delete($f.FullName) }
    }
    $list.Remove($alt)
    [void](Update-Announcer $tracks $st)
    [void](Update-TrackSounds $tracks $st)
    Write-ExtrasState $tracks $st
    if ($st.art) { [void](Update-MenuArt $tracks $st) }
    Write-SwitchFile $tracks $st
}

# ---- the announcer's stage names ----
# SEGA Rally 3's announcer has a clip for each of its own environments; Revo's Arctic and Safari were
# never recorded. Your own recordings go in SR3CamLab\announcer\ (Arctic.wav, Safari.wav: any WAV,
# about a second, just the word). They are put where two clips the arcade game never plays are
# stored: the "SEGA Rally Revo" and "SEGA Rally Revolution" title shouts of the home version.
#   Audio\EnglishStreamHeader.stm: at 0x100 {first record, count, ...}; 200-byte records {path[192],
#     index, -> info}; info = {source path[192], channels, rate, bytes, ...}
#   Audio\EnglishStreamData.stm: from 0x100, per stream in index order: path[192], then the samples
#     (16-bit, mono, 32000 Hz)
# Only the samples of those two clips are overwritten; what was there is kept in
# tracks\_SR3Extras\original\announcer_<clip>.bin and put back when a recording is taken away.
$script:AnnouncerSpares = @{ arctic = @{ Event = 'SP_SEGARALLYREVO'; Stream = 'segarallyrevo'; File = 'Arctic.wav' }
                             safari = @{ Event = 'SP_SEGARALLYREVOLUTION'; Stream = 'segarallyrevolution'; File = 'Safari.wav' } }
function Get-AnnouncerDir { return (Join-Path $PSScriptRoot 'announcer') }
# The streams as the header file lists them: @{ Streams = name -> @{ Index; Offset; Size; Channels; Rate } (where each
# one's samples are in the data file); End = where SEGA's last stream ends }. One name is used twice, for a speech clip
# and for a tune ("gameoveryeah"): $channels (1 or 2) picks the streams of that kind only.
function Read-StreamLayout([string]$game, [int]$channels = 0) {
    $hf = Join-Path $game 'Audio\EnglishStreamHeader.stm'
    if (-not (Test-Path -LiteralPath $hf)) { return $null }
    $h = [IO.File]::ReadAllBytes($hf)
    if ($h.Length -lt 0x110) { return $null }
    $first = [BitConverter]::ToInt32($h, 0x100); $count = [BitConverter]::ToInt32($h, 0x104)
    if ($first -lt 0x110 -or $count -lt 1 -or $count -gt 5000 -or $first + 200 * $count -gt $h.Length) { return $null }
    $byIndex = @{}
    for ($i = 0; $i -lt $count; $i++) {
        $r = $first + 200 * $i
        $n = [Array]::IndexOf($h, [byte]0, $r); if ($n -lt 0 -or $n -gt $r + 192) { $n = $r + 192 }
        $name = ([Text.Encoding]::ASCII.GetString($h, $r, $n - $r) -split '\\')[-1].ToLower()
        $idx = [BitConverter]::ToInt32($h, $r + 192); $info = [BitConverter]::ToInt32($h, $r + 196)
        if ($info -lt 0 -or $info + 224 -gt $h.Length) { return $null }
        $byIndex[$idx] = @{ Name = $name; Index = $idx; Channels = [BitConverter]::ToInt32($h, $info + 192); Rate = [BitConverter]::ToInt32($h, $info + 196); Size = [BitConverter]::ToInt32($h, $info + 200) }
    }
    $map = @{}; $pos = 0x100
    for ($i = 0; $i -lt $count; $i++) {
        if (-not $byIndex.ContainsKey($i)) { return $null }
        $s = $byIndex[$i]; $s.Offset = $pos + 192; $pos += 192 + $s.Size
        if (-not $channels -or $s.Channels -eq $channels) { $map[$s.Name] = $s }
    }
    return @{ Streams = $map; End = [long]$pos }
}
# name -> @{ Index; Offset; Size; Channels; Rate } of every stream's samples in the data file, or $null when the data file is
# not the one this tool knows: it must end with SEGA's last stream, or with the tunes this tool appended after it
# (Set-MusicSource; music.json says how many bytes).
function Get-AnnouncerStreams([string]$game, [int]$channels = 0) {
    $l = Read-StreamLayout $game $channels
    $df = Join-Path $game 'Audio\EnglishStreamData.stm'
    if (-not $l -or -not (Test-Path -LiteralPath $df)) { return $null }
    $len = (Get-Item -LiteralPath $df).Length
    if ($len -ne $l.End) { $m = Read-MusicFile $game; if (-not $m -or $m.dataLength -ne $l.End -or $len -ne $l.End + $m.appended) { return $null } }
    return $l.Streams
}
# Puts the recordings that are needed (an alternative track of that environment is on a card) into the
# game, takes the others out, and remembers in $st.announcer which clip says which environment.
function Update-Announcer([string]$tracks, $st) {
    $game = Get-GameDir $tracks; $store = Get-StoreDir $tracks
    $notes = @()
    $needed = @{}
    foreach ($slot in @($st.alts.Keys)) { foreach ($a in $st.alts[$slot]) { $env = ("$($a.track)" -replace '\d+$', '').ToLower(); if ($script:AnnouncerSpares.ContainsKey($env)) { $needed[$env] = $true } } }
    $streams = $null
    $st.announcer = @{}
    foreach ($env in $script:AnnouncerSpares.Keys) {
        $spare = $script:AnnouncerSpares[$env]
        $wav = Join-Path (Get-AnnouncerDir) $spare.File
        $bak = Join-Path $store "original\announcer_$($spare.Stream).bin"
        $want = $needed[$env] -and (Test-Path -LiteralPath $wav)
        if (-not $want -and -not (Test-Path -LiteralPath $bak)) { continue }
        if (-not $streams) { $streams = Get-AnnouncerStreams $game }
        if (-not $streams -or -not $streams.ContainsKey($spare.Stream)) { $notes += "The game's sound files aren't laid out the way SR3Ultimate expects; the announcer keeps a stand-in for $env."; continue }
        $s = $streams[$spare.Stream]; $df = Join-Path $game 'Audio\EnglishStreamData.stm'
        if ($s.Channels -ne 1 -or $s.Rate -ne 32000 -or $s.Size -lt 2000) { $notes += "The clip SR3Ultimate would use for $env isn't what it expects; the announcer keeps a stand-in."; continue }
        $fs = [IO.File]::Open($df, 'Open', 'ReadWrite', 'Read')
        try {
            # the clip's own header must be right before the samples
            $head = New-Object byte[] 192; $fs.Position = $s.Offset - 192; [void]$fs.Read($head, 0, 192)
            if ([Text.Encoding]::ASCII.GetString($head).ToLower().IndexOf('\' + $spare.Stream + '.wav') -lt 0) { $notes += "The clip SR3Ultimate would use for $env isn't where it expects; the announcer keeps a stand-in."; continue }
            if (-not (Test-Path -LiteralPath $bak)) {
                $orig = New-Object byte[] $s.Size; $fs.Position = $s.Offset; [void]$fs.Read($orig, 0, $s.Size)
                [void][IO.Directory]::CreateDirectory((Split-Path -Parent $bak)); [IO.File]::WriteAllBytes($bak, $orig)
            }
            if (-not $want) {                                         # back to what the game had
                $orig = [IO.File]::ReadAllBytes($bak)
                if ($orig.Length -eq $s.Size) { $fs.Position = $s.Offset; $fs.Write($orig, 0, $orig.Length); $fs.Flush(); $fs.Close(); [IO.File]::Delete($bak) }
                continue
            }
            $ffmpeg = Get-Command ffmpeg -ErrorAction SilentlyContinue | Select-Object -First 1
            if (-not $ffmpeg) { $notes += "Your announcer recordings need ffmpeg (ffmpeg.org) to be put into the game; until then the announcer uses a stand-in."; continue }
            $raw = Join-Path $store 'tmp\announcer.raw'; [void][IO.Directory]::CreateDirectory((Split-Path -Parent $raw))
            if (Test-Path -LiteralPath $raw) { [IO.File]::Delete($raw) }
            & $ffmpeg.Source -v error -y -i $wav -ac 1 -ar 32000 -f s16le $raw 2>$null
            if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $raw)) { $notes += "$($spare.File) couldn't be read as sound; the announcer uses a stand-in for $env."; continue }
            $pcm = [IO.File]::ReadAllBytes($raw); [IO.File]::Delete($raw)
            # As loud as the announcer, whose clips are pressed hard against full scale (the louder half
            # of "Canyon" averages about 10000 of 32767): a normal recording is lost under the menu
            # music. Gain to that level, with a soft ceiling instead of clipping.
            $n16 = [int]($pcm.Length / 2); $frame = 1600; $levels = New-Object System.Collections.Generic.List[double]
            for ($f0 = 0; $f0 + $frame -le $n16; $f0 += $frame) {
                $sum = 0.0
                for ($k = $f0; $k -lt $f0 + $frame; $k++) { $v = [BitConverter]::ToInt16($pcm, 2 * $k); $sum += $v * $v }
                $levels.Add([Math]::Sqrt($sum / $frame))
            }
            if ($levels.Count -ge 2) {
                $levels.Sort(); $loud = 0.0; $half = [int]($levels.Count / 2)
                for ($k = $half; $k -lt $levels.Count; $k++) { $loud += $levels[$k] }
                $loud /= ($levels.Count - $half)
                if ($loud -gt 20) {
                    $gain = [Math]::Min(11500 / $loud, 40)
                    for ($k = 0; $k -lt $n16; $k++) {
                        $v = [BitConverter]::ToInt16($pcm, 2 * $k) * $gain / 32000.0
                        $b2 = [BitConverter]::GetBytes([int16](32000.0 * [Math]::Tanh($v))); $pcm[2 * $k] = $b2[0]; $pcm[2 * $k + 1] = $b2[1]
                    }
                }
            }
            $buf = New-Object byte[] $s.Size                                 # silence after a shorter recording
            $n = [Math]::Min($pcm.Length - ($pcm.Length % 2), $s.Size - ($s.Size % 2))
            [Array]::Copy($pcm, 0, $buf, 0, $n)
            if ($pcm.Length -gt $s.Size) {                                    # a longer one is cut, with a short fade
                $fade = [Math]::Min(1600, $n / 2)
                for ($k = 0; $k -lt $fade; $k++) {
                    $o = $n - 2 * ($k + 1); $v = [BitConverter]::ToInt16($buf, $o)
                    $b2 = [BitConverter]::GetBytes([int16]($v * $k / $fade)); $buf[$o] = $b2[0]; $buf[$o + 1] = $b2[1]
                }
                $notes += ("{0} is {1:N1} s long; the game has room for {2:N1} s, so its end was faded out." -f $spare.File, ($pcm.Length / 64000), ($s.Size / 64000))
            }
            $fs.Position = $s.Offset; $fs.Write($buf, 0, $buf.Length); $fs.Flush()
            $st.announcer[$env] = $spare.Event
        } finally { $fs.Dispose() }
    }
    return ,$notes
}

# ---- the race sounds of the alternative tracks ----
# The game makes three names from a track's sound id ("ID_TRACK_CANYON_1"): the ambience event
# "SFX_AMBIENT_<id>", the music event "MU_RACE_<id>" and the file Audio\<id>_Events.bin (where along
# the route which ambience and reverb plays). The switcher can give a track other ids (patch.ps1).
#   Ambience: the arcade sound bank has the events of most of Revo's routes (Safari is "DESERT").
#   Events files: the arcade has only its own five; Revo's are in SR3CamLab\sounds\events\ (converted
#     from your PlayStation 3 disc: the same file with every 32-bit word byte-swapped) and are copied
#     into Audio\ under the arcade's id. New files only; they are listed in
#     tracks\_SR3Extras\sounds_added.txt and removed with the track.
#   Arctic has no ambience in the arcade bank. It borrows a Tropical route's event that no arcade track
#     uses (ID_TRACK_TROPICAL_7, _8); all Tropical events share one set of ten sounds, of which the two
#     "night" ones (slots 9, 10) are never asked for by an installed track. Their samples are
#     overwritten with Arctic's (SR3CamLab\sounds\arctic\<clip>.wav, 16-bit mono 24000 Hz, from your
#     PS3 disc; originals kept in tracks\_SR3Extras\original\sounds\), and Arctic's events file is
#     written with its zones turned to those two: quiet + low wind (8), lake + high wind (9).
$script:ArcticDonors = @('ID_TRACK_TROPICAL_7', 'ID_TRACK_TROPICAL_8')
$script:ArcticClips = @('tropicalswampnight_l', 'tropicalswampnight_r', 'tropicalforestnight_l', 'tropicalforestnight_r')
$script:ArcticZones = @{ 0 = 8; 4 = 8; 5 = 8 }                    # every other Arctic zone -> 9
function Get-SoundsDir { return (Join-Path $PSScriptRoot 'sounds') }
function Read-TrackSounds([string]$tracks) {
    $f = Join-Path (Get-StoreDir $tracks) 'sounds.json'; $map = @{}
    if (Test-Path -LiteralPath $f) { try { foreach ($p in ([IO.File]::ReadAllText($f) | ConvertFrom-Json).PSObject.Properties) { $map[$p.Name] = @{ ambience = "$($p.Value.ambience)"; music = "$($p.Value.music)"; events = "$($p.Value.events)" } } } catch { } }
    return $map
}
# Works out the sounds of every alternative track, puts the files they need into the game and writes
# tracks\_SR3Extras\sounds.json ("<slot>/<folder number>" -> ids) for Write-SwitchFile. Returns notes.
function Update-TrackSounds([string]$tracks, $st) {
    $game = Get-GameDir $tracks; $store = Get-StoreDir $tracks; $audio = Join-Path $game 'Audio'
    $notes = @(); $map = @{}
    $running = [bool](Get-Process -Name Rally -ErrorAction SilentlyContinue)
    $names = ''; $list = Join-Path $audio 'SFX_HashCode.h'
    if (Test-Path -LiteralPath $list) { $names = [IO.File]::ReadAllText($list) }
    # the events files added before go; the ones still wanted are written again
    $addedFile = Join-Path $store 'sounds_added.txt'
    if (Test-Path -LiteralPath $addedFile) {
        foreach ($n in [IO.File]::ReadAllLines($addedFile)) { if ($n -match '^ID_TRACK_[A-Z]+_[0-9]_Events\.bin$') { $p = Join-Path $audio $n; if (Test-Path -LiteralPath $p) { [IO.File]::Delete($p) } } }
        [IO.File]::Delete($addedFile)
    }
    $added = @(); $donor = 0; $arctic = $false
    $haveArctic = $true; foreach ($c in $script:ArcticClips) { if (-not (Test-Path -LiteralPath (Join-Path (Get-SoundsDir) "arctic\$c.wav"))) { $haveArctic = $false } }
    foreach ($slot in @($st.alts.Keys | Sort-Object)) {
        foreach ($a in $st.alts[$slot]) {
            $r = @{ ambience = ''; music = ''; events = '' }; $map["$slot/$($a.dir)"] = $r
            if ("$($a.track)" -notmatch '^([A-Za-z]+?)(\d+)$') { continue }
            $env = $Matches[1].ToUpper(); $n = $Matches[2]
            $src = Join-Path (Get-SoundsDir) "events\ID_TRACK_${env}_${n}_Events.bin"       # Revo's own name
            if ($env -eq 'ARCTIC') {
                if (-not $haveArctic -or $donor -ge $script:ArcticDonors.Count -or -not (Test-Path -LiteralPath $src) -or $names -notmatch "\bSFX_AMBIENT_$($script:ArcticDonors[$donor])\b") { continue }
                $id = $script:ArcticDonors[$donor]; $dst = Join-Path $audio "${id}_Events.bin"
                if (Test-Path -LiteralPath $dst) { continue }                               # not ours to overwrite
                $b = [IO.File]::ReadAllBytes($src)
                if ($b.Length -ne 9612) { continue }
                $count = [Math]::Min([BitConverter]::ToInt32($b, 0x1774), 300)
                for ($i = 0; $i -lt $count; $i++) {                                         # {route position, side, zone}
                    $o = 0x1778 + 12 * $i + 8; $z = [BitConverter]::ToInt32($b, $o)
                    $to = if ($script:ArcticZones.ContainsKey($z)) { $script:ArcticZones[$z] } else { 9 }
                    [BitConverter]::GetBytes([int]$to).CopyTo($b, $o)
                }
                [IO.File]::WriteAllBytes($dst, $b); $added += "${id}_Events.bin"
                $r.ambience = $id; $r.events = $id; $donor++; $arctic = $true
                continue
            }
            if ($env -eq 'SAFARI') { $env = 'DESERT' }
            $id = "ID_TRACK_${env}_$n"
            if ($names -match "\bSFX_AMBIENT_$id\b") {
                $r.ambience = $id
                $dst = Join-Path $audio "${id}_Events.bin"
                if (Test-Path -LiteralPath $dst) { $r.events = $id }
                elseif ((Test-Path -LiteralPath $src) -and (Get-Item -LiteralPath $src).Length -eq 9612) { [IO.File]::Copy($src, $dst); $added += "${id}_Events.bin"; $r.events = $id }
            }
            if ($names -match "\bMU_RACE_ID_TRACK_${env}_1\b") { $r.music = "ID_TRACK_${env}_1" }
        }
    }
    if ($added.Count) { [IO.File]::WriteAllLines($addedFile, [string[]]$added) }
    # Arctic's two sounds, in the place of the Tropical night sounds (or those back)
    $keep = Join-Path $store 'original\sounds'
    if ($arctic -or (Test-Path -LiteralPath $keep)) {
        if ($running) { $notes += 'The game is running, so the Arctic ambience was left as it is.' }
        else {
            $streams = Get-AnnouncerStreams $game
            if (-not $streams) { $notes += "The game's sound files aren't laid out the way SR3Ultimate expects; Arctic keeps the card's ambience."; $arctic = $false }
            else {
                $fs = [IO.File]::Open((Join-Path $audio 'EnglishStreamData.stm'), 'Open', 'ReadWrite', 'Read')
                try {
                    foreach ($c in $script:ArcticClips) {
                        if (-not $streams.ContainsKey($c)) { $arctic = $false; continue }
                        $s = $streams[$c]; $bak = Join-Path $keep "$c.bin"
                        if ($arctic) {
                            $pcm = Read-WavSamples (Join-Path (Get-SoundsDir) "arctic\$c.wav") 24000
                            if ($null -eq $pcm -or $s.Rate -ne 24000 -or $s.Channels -ne 1) { $notes += "sounds\arctic\$c.wav isn't 16-bit mono 24000 Hz; skipped."; continue }
                            if (-not (Test-Path -LiteralPath $bak)) {
                                $orig = New-Object byte[] $s.Size; $fs.Position = $s.Offset; [void]$fs.Read($orig, 0, $s.Size)
                                [void][IO.Directory]::CreateDirectory($keep); [IO.File]::WriteAllBytes($bak, $orig)
                            }
                            $buf = New-Object byte[] $s.Size
                            [Array]::Copy($pcm, 0, $buf, 0, [Math]::Min($pcm.Length - ($pcm.Length % 2), $s.Size - ($s.Size % 2)))
                            $fs.Position = $s.Offset; $fs.Write($buf, 0, $buf.Length)
                        } elseif (Test-Path -LiteralPath $bak) {
                            $orig = [IO.File]::ReadAllBytes($bak)
                            if ($orig.Length -eq $s.Size) { $fs.Position = $s.Offset; $fs.Write($orig, 0, $orig.Length); [IO.File]::Delete($bak) }
                        }
                    }
                    $fs.Flush()
                } finally { $fs.Dispose() }
                if ((Test-Path -LiteralPath $keep) -and @(Get-ChildItem -LiteralPath $keep).Count -eq 0) { [IO.Directory]::Delete($keep) }
            }
        }
    }
    [void][IO.Directory]::CreateDirectory($store)
    [IO.File]::WriteAllText((Join-Path $store 'sounds.json'), ($map | ConvertTo-Json -Depth 4))
    return ,$notes
}

# ---- another co-driver ----
# The game's speech is made of streams of one big file (Audio\EnglishStreamData.stm, layout above at the announcer).
# A stream can be given other samples in place: the file keeps its size and the stream its length, so a shorter
# clip is followed by silence and a longer one is cut. What the game had is kept in
# tracks\_SR3Extras\original\codriver\<stream>.bin and put back before anything else goes in, so one voice never
# sits on top of another and the game's own is always one step away.
#   One WAV per clip, named after the game's clip ("easyright.wav"...), 16-bit mono 32000 Hz. Clips without a file
#   keep the game's voice.
#     sr2  SEGA Rally 2's: SR3CamLab\codriver\ (or codriver\sr2\ when that folder holds clips)
#     src  SEGA Rally Championship's (1995): SR3CamLab\codriver\src\, made from your own ROM set by
#          scripts\rom_tools\src_audio.py codriver
# state.json remembers the choice ("codriver"); the kept originals decide what is really in the game.
$script:VoiceSources = [ordered]@{
    ''    = @{ Title = "SEGA Rally 3 (the game's own)" }
    'sr2' = @{ Title = 'SEGA Rally 2'; Hint = 'Its clips go in the codriver folder (one WAV per clip).' }
    'src' = @{ Title = 'SEGA Rally Championship (1995)'; Hint = 'Make its clips from your ROM set: scripts\rom_tools\src_audio.py codriver' } }
function Test-HasWavs([string]$dir) { return [bool]((Test-Path -LiteralPath $dir -PathType Container) -and @(Get-ChildItem -LiteralPath $dir -Filter '*.wav' -File).Count) }
function Get-CoDriverDir([string]$source = 'sr2') {
    $root = Join-Path $PSScriptRoot 'codriver'
    if ($source -eq 'sr2' -and -not (Test-HasWavs (Join-Path $root 'sr2'))) { return $root }      # where SEGA Rally 2's clips were put at first
    return (Join-Path $root $source)
}
# the samples of a WAV file, or $null when it is not 16-bit PCM with that many channels at that rate
function Read-WavSamples([string]$file, [int]$rate = 32000, [int]$channels = 1) {
    $b = [IO.File]::ReadAllBytes($file)
    if ($b.Length -lt 44 -or [Text.Encoding]::ASCII.GetString($b, 0, 4) -ne 'RIFF' -or [Text.Encoding]::ASCII.GetString($b, 8, 4) -ne 'WAVE') { return $null }
    $p = 12; $ok = $false
    while ($p + 8 -le $b.Length) {
        $id = [Text.Encoding]::ASCII.GetString($b, $p, 4); $n = [BitConverter]::ToInt32($b, $p + 4)
        if ($n -lt 0 -or $p + 8 + $n -gt $b.Length) { $n = $b.Length - $p - 8 }
        if ($id -eq 'fmt ') { $ok = [BitConverter]::ToInt16($b, $p + 8) -eq 1 -and [BitConverter]::ToInt16($b, $p + 10) -eq $channels -and [BitConverter]::ToInt32($b, $p + 12) -eq $rate -and [BitConverter]::ToInt16($b, $p + 22) -eq 16 }
        if ($id -eq 'data') { if (-not $ok) { return $null }; $d = New-Object byte[] $n; [Array]::Copy($b, $p + 8, $d, 0, $n); return ,$d }
        $p += 8 + $n + ($n % 2)
    }
    return $null
}
# Puts the game's own samples back into every stream whose original is kept in $keep, then (when $dir is given)
# the WAV files of $dir over the streams of the same names. $channels: the streams of that kind only (1 = speech).
# Returns @{ Done; Back; Skipped (file names); Cut (file names) }.
function Set-StreamClips([string]$tracks, [string]$keep, [string]$dir, [int]$channels) {
    Assert-GameClosed
    $game = Get-GameDir $tracks
    $streams = Get-AnnouncerStreams $game $channels
    if (-not $streams) { throw "The game's sound files aren't laid out the way SR3Ultimate expects." }
    $df = Join-Path $game 'Audio\EnglishStreamData.stm'
    $spare = @{}; foreach ($s in $script:AnnouncerSpares.Values) { $spare[$s.Stream] = $true }
    $r = @{ Done = 0; Back = 0; Skipped = @(); Cut = @() }
    $fs = [IO.File]::Open($df, 'Open', 'ReadWrite', 'Read')
    try {
        # first everything back to the game's own
        if (Test-Path -LiteralPath $keep) {
            foreach ($f in Get-ChildItem -LiteralPath $keep -Filter '*.bin' -File) {
                $name = [IO.Path]::GetFileNameWithoutExtension($f.Name)
                if (-not $streams.ContainsKey($name) -or $streams[$name].Size -ne $f.Length) { continue }
                $orig = [IO.File]::ReadAllBytes($f.FullName)
                $fs.Position = $streams[$name].Offset; $fs.Write($orig, 0, $orig.Length); $fs.Flush()
                [IO.File]::Delete($f.FullName); $r.Back++
            }
        }
        if ($dir) {
            [void][IO.Directory]::CreateDirectory($keep)
            foreach ($f in Get-ChildItem -LiteralPath $dir -Filter '*.wav' -File) {
                $name = [IO.Path]::GetFileNameWithoutExtension($f.Name).ToLower()
                if ($spare[$name] -or -not $streams.ContainsKey($name)) { $r.Skipped += $f.Name; continue }
                $s = $streams[$name]; $bak = Join-Path $keep "$name.bin"
                if ($s.Channels -ne $channels -or $s.Rate -ne 32000) { $r.Skipped += $f.Name; continue }
                if (Test-Path -LiteralPath $bak) { $r.Skipped += $f.Name; continue }        # an original that could not be put back: never overwritten
                $pcm = Read-WavSamples $f.FullName 32000 $channels
                if ($null -eq $pcm) { $r.Skipped += $f.Name; continue }
                $head = New-Object byte[] 192; $fs.Position = $s.Offset - 192; [void]$fs.Read($head, 0, 192)
                if ([Text.Encoding]::ASCII.GetString($head).ToLower().IndexOf('\' + $name + '.wav') -lt 0) { $r.Skipped += $f.Name; continue }
                $orig = New-Object byte[] $s.Size; $fs.Position = $s.Offset; [void]$fs.Read($orig, 0, $s.Size)
                [IO.File]::WriteAllBytes($bak, $orig)
                $frame = 2 * $channels; $buf = New-Object byte[] $s.Size
                [Array]::Copy($pcm, 0, $buf, 0, [Math]::Min($pcm.Length - ($pcm.Length % $frame), $s.Size - ($s.Size % $frame)))
                if ($pcm.Length -gt $s.Size) { $r.Cut += $f.Name }
                $fs.Position = $s.Offset; $fs.Write($buf, 0, $buf.Length); $r.Done++
            }
        }
        $fs.Flush()
    } finally { $fs.Dispose() }
    if ((Test-Path -LiteralPath $keep) -and @(Get-ChildItem -LiteralPath $keep).Count -eq 0) { [IO.Directory]::Delete($keep) }
    return $r
}
function Get-ClipNotes($r, [string]$format) {
    $notes = @()
    if ($r.Skipped.Count) { $notes += "Not used (no clip of that name, or not $format): $((@($r.Skipped) | Select-Object -First 5) -join ', ')$(if ($r.Skipped.Count -gt 5) { " and $($r.Skipped.Count - 5) more" })." }
    if ($r.Cut.Count) { $notes += "Longer than what it replaces, so cut at the end: $((@($r.Cut) | Select-Object -First 5) -join ', ')$(if ($r.Cut.Count -gt 5) { " and $($r.Cut.Count - 5) more" })." }
    return $notes
}
# The pace-note voice: '' = the game's own, 'sr2', 'src' ($script:VoiceSources). Returns notes for the user.
function Set-CoDriverSource([string]$tracks, [string]$source) {
    if (-not $script:VoiceSources.Contains($source)) { throw "There is no co-driver called '$source'." }
    $dir = ''
    if ($source) {
        $dir = Get-CoDriverDir $source
        if (-not (Test-HasWavs $dir)) { throw "There are no clips of $($script:VoiceSources[$source].Title) to put in: $dir holds none. $($script:VoiceSources[$source].Hint)" }
    }
    $r = Set-StreamClips $tracks (Join-Path (Get-StoreDir $tracks) 'original\codriver') $dir 1
    $st = Read-ExtrasState $tracks; $st.codriver = $(if ($r.Done) { $source } else { '' }); Write-ExtrasState $tracks $st
    $notes = @()
    if ($source) { $notes += "Co-driver: $($script:VoiceSources[$source].Title), $($r.Done) clips; every other call keeps the game's voice." }
    else { $notes += "Co-driver: the game's own again ($($r.Back) clips put back)." }
    return ,(@($notes) + @(Get-ClipNotes $r '16-bit mono 32000 Hz'))
}
function Set-CoDriver([string]$tracks, [bool]$on) { return ,(Set-CoDriverSource $tracks $(if ($on) { 'sr2' } else { '' })) }

# ---- the music of the imported courses ----
# Another game's tunes are never put in the place of SEGA Rally 3's music: every stage and the menus keep theirs,
# whatever is chosen here. A tune is APPENDED to the stream file (Audio\EnglishStreamData.stm) after SEGA's last
# stream, where nothing of the game points: a 192-byte block and the samples (16-bit stereo 32000 Hz), the way the
# game's own streams lie in that file. tracks\_SR3Extras\music.json says what was appended and how long the file was
# before; taking the music out cuts the file back to that length, which makes it byte for byte what it was. No
# other file of the game changes.
# Who plays a tune: only the course it belongs to. A 1995 course in the Classic mode (Get-ClassicCourse) whose tune
# is there gets the tune's place in switch.json ("tune"). PLAY.bat's switcher then turns the stream record of the
# Classic mode's music to it, in the game's memory, while that course is the one chosen, and back for every other
# track (patch.ps1, Set-CourseTune). A course without a tune plays the Classic mode's own music, as it always did.
#   src  SEGA Rally Championship's (1995): SR3CamLab\music\src\desert.wav, forest.wav, mountain.wav, lakeside.wav
#        (any of them) and tunes.json (where each one's loop starts), made from your own ROM set by
#        scripts\rom_tools\src_music.py
$script:MusicSources = [ordered]@{
    ''    = @{ Title = "SEGA Rally 3 (the game's own)" }
    'src' = @{ Title = 'SEGA Rally Championship (1995)'; Hint = 'Make its tunes from your ROM set: scripts\rom_tools\src_music.py' } }
$script:TuneCourses = @(@{ Key = 'desert'; Match = 'desert' }, @{ Key = 'forest'; Match = 'forest' }, @{ Key = 'mountain'; Match = 'mountain' }, @{ Key = 'lakeside'; Match = 'lake' })
$script:ClassicMusicStream = 'hyper conditioned reflex_fullqualityversion'      # the stream the Classic mode's music event plays
function Get-MusicDir([string]$source) { return (Join-Path $PSScriptRoot "music\$source") }
function Get-MusicFile([string]$game) { return (Join-Path $game 'Main_release\tracks\_SR3Extras\music.json') }
function Get-TuneFiles([string]$source) {                             # the tune files of a source that are there
    $dir = Get-MusicDir $source
    return @($script:TuneCourses | ForEach-Object { Join-Path $dir "$($_.Key).wav" } | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf })
}
# what music.json says was appended to the stream file: @{ source; dataLength; appended; stream; tunes }, or $null
function Read-MusicFile([string]$game) {
    $f = Get-MusicFile $game
    if (-not (Test-Path -LiteralPath $f)) { return $null }
    try { $j = [IO.File]::ReadAllText($f) | ConvertFrom-Json } catch { return $null }
    if ("$($j.dataLength)" -notmatch '^\d+$' -or "$($j.appended)" -notmatch '^\d+$' -or "$($j.stream)" -notmatch '^\d+$') { return $null }
    return @{ source = "$($j.source)"; dataLength = [long]"$($j.dataLength)"; appended = [long]"$($j.appended)"; stream = [int]"$($j.stream)"; tunes = @($j.tunes | ForEach-Object { $_ }) }
}
# ... and only when the stream file really ends with it: what is in the game
function Get-MusicInstall([string]$game) {
    $m = Read-MusicFile $game; $df = Join-Path $game 'Audio\EnglishStreamData.stm'
    if (-not $m -or -not (Test-Path -LiteralPath $df) -or (Get-Item -LiteralPath $df).Length -ne $m.dataLength + $m.appended) { return $null }
    return $m
}
# The music: '' = nothing but the game's own, 'src' ($script:MusicSources). Returns notes for the user.
function Set-MusicSource([string]$tracks, [string]$source) {
    if (-not $script:MusicSources.Contains($source)) { throw "There is no music called '$source'." }
    Assert-GameClosed
    $game = Get-GameDir $tracks; $df = Join-Path $game 'Audio\EnglishStreamData.stm'; $mf = Get-MusicFile $game
    $layout = Read-StreamLayout $game 2
    if (-not $layout -or -not (Test-Path -LiteralPath $df)) { throw "The game's sound files aren't laid out the way SR3Ultimate expects; nothing was changed." }
    $notes = @(); $tunes = @(); $total = [long]0
    if ($source) {                                                  # the tunes are read and checked before anything changes
        $title = $script:MusicSources[$source].Title; $dir = Get-MusicDir $source
        $own = $layout.Streams[$script:ClassicMusicStream]
        if (-not $own -or $own.Channels -ne 2 -or $own.Rate -ne 32000) { throw "The Classic mode's music isn't the stream SR3Ultimate expects; nothing was changed." }
        $loops = @{}; $lf = Join-Path $dir 'tunes.json'
        if (Test-Path -LiteralPath $lf) { try { foreach ($p in ([IO.File]::ReadAllText($lf) | ConvertFrom-Json).PSObject.Properties) { $loops[$p.Name] = $p.Value } } catch { } }
        foreach ($w in Get-TuneFiles $source) {
            $fi = Get-Item -LiteralPath $w; $key = [IO.Path]::GetFileNameWithoutExtension($fi.Name).ToLower()
            $pcm = Read-WavSamples $w 32000 2
            if ($null -eq $pcm -or $pcm.Length -lt 128000) { $notes += "$($fi.Name) was not used (not 16-bit stereo 32000 Hz, or shorter than a second)."; continue }
            $n = $pcm.Length - ($pcm.Length % 4); $start = [long]0; $l = $loops[$key]      # the loop start counts only for the very file it was written for
            if ($l -and "$($l.frames)" -eq "$($n / 4)" -and "$($l.loop_start)" -match '^\d+$' -and 4 * [long]"$($l.loop_start)" -lt $n) { $start = 4 * [long]"$($l.loop_start)" }
            $tunes += @{ course = $key; file = $fi.Name; fileBytes = $fi.Length; fileTime = "$($fi.LastWriteTimeUtc.Ticks)"; bytes = $n; loopstart = $start; pcm = $pcm }
            $total += 192 + $n
        }
        if (-not $tunes.Count) { throw "There are no tunes of $title to put in: $dir holds none (desert.wav, forest.wav, mountain.wav, lakeside.wav; 16-bit stereo 32000 Hz). $($script:MusicSources[$source].Hint)" }
        if ($layout.End + $total -gt 0x7FFFFFFF) { throw "The game's sound file would grow past 2 GB; nothing was changed." }
    }
    # first what was appended before goes: the file ends with SEGA's last stream again
    $old = Read-MusicFile $game; $len = (Get-Item -LiteralPath $df).Length; $back = 0
    if ($old) {
        if ($old.dataLength -ne $layout.End -or $len -lt $layout.End) { throw "music.json doesn't fit the game's sound file; nothing was changed." }
        if ($len -gt $layout.End) { $fs = [IO.File]::Open($df, 'Open', 'ReadWrite', 'Read'); try { $fs.SetLength($layout.End) } finally { $fs.Dispose() } }
        [IO.File]::Delete($mf); $back = @($old.tunes).Count
    } elseif ($len -ne $layout.End) { throw "The game's sound file isn't laid out the way SR3Ultimate expects; nothing was changed." }
    if ($source) {
        $at = [long]$layout.End; $list = @()
        foreach ($t in $tunes) { $list += @{ course = $t.course; file = $t.file; fileBytes = $t.fileBytes; fileTime = $t.fileTime; offset = $at; bytes = $t.bytes; loopstart = $t.loopstart }; $at += 192 + $t.bytes }
        [void][IO.Directory]::CreateDirectory((Split-Path -Parent $mf))                # written first: a half-done append can still be cut off
        [IO.File]::WriteAllText($mf, (@{ source = $source; dataLength = [long]$layout.End; appended = $total; stream = [int]$own.Index; tunes = $list } | ConvertTo-Json -Depth 4))
        $fs = [IO.File]::Open($df, 'Open', 'ReadWrite', 'Read')
        try {
            $fs.Position = $layout.End
            foreach ($t in $tunes) {
                $block = New-Object byte[] 192; $name = [Text.Encoding]::ASCII.GetBytes("M:\Audio\Arcade Source\Music 2\Stereo\${source}_$($t.course).wav")
                [Array]::Copy($name, 0, $block, 0, [Math]::Min($name.Length, 191))
                $fs.Write($block, 0, 192); $fs.Write($t.pcm, 0, $t.bytes)
            }
            $fs.Flush()
        } finally { $fs.Dispose() }
        $notes = @("Music: $($tunes.Count) tunes of $title are in the game's sound file, after SEGA's own ($((@($tunes | ForEach-Object { $_.course }) -join ', '))). Only their own courses in the Classic mode play them, when the game is started with PLAY.bat; SEGA Rally 3's stages and menus keep their music.") + $notes
    } else { $notes += "Music: nothing but the game's own again ($back tunes taken out; the sound file has its own length back)." }
    $st = Read-ExtrasState $tracks; Write-ExtrasState $tracks $st     # state.json says what the files say
    Write-SwitchFile $tracks $st                                     # the Classic courses' tunes come and go with it
    return ,$notes
}

# ---- Handling (docs\kb\28_handling_flavors.md) ----
# Which cars drive with which handling. handling.json next to PLAY.bat (patch.ps1, Read-Handling / Set-Handling):
#   {"version": 1, "default": "src", "cars": {"ST205": "sr3"}, "flavors": {"src": {"digit": "1", "grip_file": true, "steer_return_s": 0.25}}}
# "default" is every car's flavor, "cars" the exceptions; no file = the game's own handling for every car. A flavor is a
# folder of car files Main_release\car<digit> (and a grip file SurfacePairEffect<digit>) built on this PC from the game's
# own files by scripts\handling\build_flavor.py (Python); the launcher points the game at it when a race loads.
$script:HandlingFlavors = [ordered]@{
    'sr3'     = @{ Title = "SEGA Rally 3 (the game's own)" }
    'src'     = @{ Title = 'SEGA Rally Championship (1995)'; Digit = '1'; Grip = $true; Table = 'flavor_src.json' }
    'realism' = @{ Title = "Realism (the real cars' specs)"; Digit = '2'; Grip = $false; Table = 'flavor_realism.json'; Specs = 'realism_specs.json' } }
$script:HandlingCars = [ordered]@{                                   # handling.json's names (the cars' data file names), the menu's
    'C4' = "Citro$([char]0xEB)n C4 WRC";'RSFocus' = 'Ford Focus RS WRC 07'; 'SubaruImpreza' = 'Subaru Impreza WRC2008'; 'SX4' = 'Suzuki SX4 WRC'
    'MitsubishiEvo' = 'Mitsubishi Lancer Evolution X'; '207' = 'Peugeot 207 Super 2000'; 'ST205' = 'Toyota Celica ST205'
    'Delta_HF' = 'Lancia Super Delta HF integrale'; 'Bowler' = 'Bowler Nemesis'; 'Enduro' = 'McRae Enduro' }
$script:SteerReturnSeconds = 0.25                                    # SRC: from full lock to the centre, like the cabinet wheel's spring
function Get-HandlingFile { return (Join-Path $PSScriptRoot 'handling.json') }
# the cars a handling can be set for: SEGA's ten and the added ones (Main_release\cars\<name>gravel_data.sbf, e.g. the Hornet)
function Get-HandlingCars([string]$tracks) {
    $cars = [ordered]@{}; foreach ($k in $script:HandlingCars.Keys) { $cars[$k] = $script:HandlingCars[$k] }
    foreach ($f in @(Get-ChildItem -LiteralPath (Join-Path (Get-GameDir $tracks) 'Main_release\cars') -Filter '*gravel_data.sbf' -ErrorAction SilentlyContinue)) {
        $n = $f.Name -replace '(?i)gravel_data\.sbf$', ''
        if (-not @($cars.Keys | Where-Object { $_ -eq $n }).Count) { $cars[$n] = (Get-Culture).TextInfo.ToTitleCase($n) }
    }
    return $cars
}
# @{ Default; Cars = @{ name -> flavor }; Steer = seconds of SRC's steering return (0 = off) }
function Read-HandlingFile {
    $h = @{ Default = 'sr3'; Cars = @{}; Steer = $script:SteerReturnSeconds }
    $f = Get-HandlingFile
    if (-not (Test-Path -LiteralPath $f)) { return $h }
    try { $j = [IO.File]::ReadAllText($f) | ConvertFrom-Json } catch { return $h }
    if ($script:HandlingFlavors.Contains("$($j.default)".ToLower())) { $h.Default = "$($j.default)".ToLower() }
    if ($j.cars) { foreach ($p in $j.cars.PSObject.Properties) { if ($script:HandlingFlavors.Contains("$($p.Value)".ToLower())) { $h.Cars[$p.Name] = "$($p.Value)".ToLower() } } }
    if ($j.flavors -and $j.flavors.src) { $h.Steer = if ($j.flavors.src.steer_return_s) { [double]$j.flavors.src.steer_return_s } else { 0.0 } }
    return $h
}
function Write-HandlingFile($h) {
    $flavors = [ordered]@{}
    foreach ($k in $script:HandlingFlavors.Keys) {
        $v = $script:HandlingFlavors[$k]; if (-not $v.Digit) { continue }
        $e = [ordered]@{ digit = $v.Digit; grip_file = [bool]$v.Grip }; if ($k -eq 'src' -and $h.Steer -gt 0) { $e.steer_return_s = $h.Steer }
        $flavors[$k] = $e
    }
    $cars = [ordered]@{}; foreach ($c in $h.Cars.Keys) { if ($h.Cars[$c] -ne $h.Default) { $cars[$c] = $h.Cars[$c] } }
    if ($h.Default -eq 'sr3' -and -not $cars.Count) { $f = Get-HandlingFile; if (Test-Path -LiteralPath $f) { [IO.File]::Delete($f) }; return }
    [IO.File]::WriteAllText((Get-HandlingFile), ([ordered]@{ version = 1; default = $h.Default; cars = $cars; flavors = $flavors } | ConvertTo-Json -Depth 4))
}
# a flavor's files are in the game: its car folder holds the cars' files
function Test-HandlingBuilt([string]$tracks, [string]$key) {
    $v = $script:HandlingFlavors[$key]; if (-not $v.Digit) { return $true }
    return [bool]@(Get-ChildItem -LiteralPath (Join-Path (Get-GameDir $tracks) "Main_release\car$($v.Digit)") -Filter '*_data.sbf' -ErrorAction SilentlyContinue).Count
}
function Find-Python {
    foreach ($n in 'python', 'py') { $c = Get-Command $n -ErrorAction SilentlyContinue; if ($c) { return $c.Source } }
    return $null
}
# Builds a flavor's files from the game's own (scripts\handling\build_flavor.py into a folder of its own in TEMP) and puts
# them into the game: Main_release\car<digit>, SurfacePairEffect<digit>. Only these new folders are written; SEGA's files
# are only read. Returns notes for the user.
function Build-HandlingFlavor([string]$tracks, [string]$key) {
    $v = $script:HandlingFlavors[$key]; if (-not $v.Digit) { return ,@() }
    Assert-GameClosed
    $py = Find-Python; if (-not $py) { throw "Building $($v.Title) needs Python (python.org); nothing was changed." }
    $dir = Join-Path $PSScriptRoot 'scripts\handling'; $game = Get-GameDir $tracks
    $stage = Join-Path ([IO.Path]::GetTempPath()) "SR3Lab_handling_$key"
    if (Test-Path -LiteralPath $stage) { [IO.Directory]::Delete($stage, $true) }
    $table = Join-Path $dir $v.Table
    if ($v.Specs) {                                                    # Realism: the real specs become SR3's numbers first
        $table = Join-Path $stage $v.Table; [void][IO.Directory]::CreateDirectory($stage)
        $o = & $py (Join-Path $dir 'realism_map.py') (Join-Path $dir $v.Specs) $table 2>&1
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $table)) { throw "$($v.Title): realism_map.py failed: $(($o | Select-Object -Last 3) -join ' ')" }
    }
    $o = & $py (Join-Path $dir 'build_flavor.py') $table --game $game --out (Join-Path $stage 'Rally') 2>&1
    $cars = Join-Path $stage "Rally\Main_release\car$($v.Digit)"
    if ($LASTEXITCODE -ne 0 -or -not @(Get-ChildItem -LiteralPath $cars -Filter '*_data.sbf' -ErrorAction SilentlyContinue).Count) { throw "$($v.Title): build_flavor.py failed: $(($o | Select-Object -Last 3) -join ' ')" }
    $notes = @()
    foreach ($d in @("Main_release\car$($v.Digit)", "SurfacePairEffect$($v.Digit)")) {
        $from = Join-Path $stage "Rally\$d"; $to = Join-Path $game $d
        if (-not (Test-Path -LiteralPath $from)) { continue }
        [void][IO.Directory]::CreateDirectory($to)
        foreach ($f in Get-ChildItem -LiteralPath $from -File) { [IO.File]::Copy($f.FullName, (Join-Path $to $f.Name), $true) }
        $notes += "$d ($(@(Get-ChildItem -LiteralPath $from -File).Count) files)"
    }
    [IO.Directory]::Delete($stage, $true)
    return ,@("$($v.Title): built from your game's files into $($notes -join ' and ').")
}
# The handling pop-up (Options tab): one handling for every car (the default), or car by car; SRC's steering return;
# building a handling's files. Returns what to write into handling.json (Write-HandlingFile), or $null for Cancel.
# $OnShown runs when the pop-up is on screen (pictures, tests).
function Show-HandlingDialog($owner, [string]$tracks, [scriptblock]$OnShown) {
    $hf = Read-HandlingFile; $cars = Get-HandlingCars $tracks; $keys = @($script:HandlingFlavors.Keys)
    $d = New-Object Windows.Forms.Form; $d.Text = 'Handling'; $d.FormBorderStyle = 'FixedDialog'; $d.MaximizeBox = $false; $d.MinimizeBox = $false
    $d.Font = if ($owner) { $owner.Font } else { New-Object Drawing.Font('Segoe UI', 9) }
    $d.StartPosition = 'CenterParent'; $d.AutoSize = $true; $d.AutoSizeMode = 'GrowAndShrink'; $d.Padding = New-Object Windows.Forms.Padding(12)
    $flow = New-Object Windows.Forms.FlowLayoutPanel; $flow.FlowDirection = 'TopDown'; $flow.WrapContents = $false; $flow.AutoSize = $true; $flow.Dock = 'Fill'
    $d.Controls.Add($flow)
    $titles = { param($k) $script:HandlingFlavors[$k].Title + $(if (-not (Test-HandlingBuilt $tracks $k)) { '   (not built yet)' } else { '' }) }
    $mkBox = { $c = New-Object Windows.Forms.ComboBox; $c.DropDownStyle = 'DropDownList'; $c.Width = 300; foreach ($k in $keys) { [void]$c.Items.Add((& $titles $k)) }; $c }
    $rAll = New-Object Windows.Forms.RadioButton; $rAll.Text = 'The same handling for every car'; $rAll.AutoSize = $true
    $cAll = & $mkBox; $cAll.Margin = New-Object Windows.Forms.Padding(20, 0, 0, 10); $cAll.SelectedIndex = [Math]::Max(0, [Array]::IndexOf($keys, $hf.Default))
    $rPer = New-Object Windows.Forms.RadioButton; $rPer.Text = 'Car by car'; $rPer.AutoSize = $true
    $grid = New-Object Windows.Forms.TableLayoutPanel; $grid.ColumnCount = 2; $grid.AutoSize = $true; $grid.Margin = New-Object Windows.Forms.Padding(20, 0, 0, 10)
    $per = [ordered]@{}; $row = 0
    foreach ($c in $cars.Keys) {
        $l = New-Object Windows.Forms.Label; $l.Text = $cars[$c]; $l.AutoSize = $true; $l.Margin = New-Object Windows.Forms.Padding(0, 6, 12, 0)
        $b = & $mkBox; $f = if ($hf.Cars.ContainsKey($c)) { $hf.Cars[$c] } else { $hf.Default }; $b.SelectedIndex = [Math]::Max(0, [Array]::IndexOf($keys, $f))
        $grid.Controls.Add($l, 0, $row); $grid.Controls.Add($b, 1, $row); $per[$c] = $b; $row++
    }
    $odd = @($cars.Keys | Where-Object { $hf.Cars.ContainsKey($_) -and $hf.Cars[$_] -ne $hf.Default }).Count
    $rAll.Checked = -not $odd; $rPer.Checked = [bool]$odd
    $sync = { $cAll.Enabled = $rAll.Checked; $grid.Enabled = $rPer.Checked }.GetNewClosure(); & $sync
    $rAll.Add_CheckedChanged($sync); $rPer.Add_CheckedChanged($sync)
    $cSteer = New-Object Windows.Forms.CheckBox; $cSteer.AutoSize = $true; $cSteer.Checked = $hf.Steer -gt 0; $cSteer.Margin = New-Object Windows.Forms.Padding(0, 4, 0, 0)
    $cSteer.Text = "SEGA Rally Championship: the wheels come back to the centre over $($script:SteerReturnSeconds) s when you let go,`nlike the arcade wheel's spring (turning in stays instant)"
    $note = New-Object Windows.Forms.Label; $note.AutoSize = $true; $note.MaximumSize = New-Object Drawing.Size(560, 0); $note.Margin = New-Object Windows.Forms.Padding(0, 10, 0, 6)
    $note.Text = "A handling marked 'not built yet' needs its files first: 'Build the files' makes them from your own game files (Python needed) into new folders; the game's own car files are never changed. A car on a handling that isn't built drives with the game's own. The choice takes effect the next time the game is started with PLAY.bat."
    $btns = New-Object Windows.Forms.FlowLayoutPanel; $btns.AutoSize = $true; $btns.WrapContents = $false; $btns.Margin = New-Object Windows.Forms.Padding(0, 6, 0, 0)
    $bBuild = New-Object Windows.Forms.Button; $bBuild.Text = 'Build the files'; $bBuild.AutoSize = $true
    $bOk = New-Object Windows.Forms.Button; $bOk.Text = 'OK'; $bOk.AutoSize = $true; $bOk.DialogResult = 'OK'
    $bCancel = New-Object Windows.Forms.Button; $bCancel.Text = 'Cancel'; $bCancel.AutoSize = $true; $bCancel.DialogResult = 'Cancel'
    $btns.Controls.AddRange(@($bBuild, $bOk, $bCancel)); $d.AcceptButton = $bOk; $d.CancelButton = $bCancel
    $flow.Controls.AddRange(@($rAll, $cAll, $rPer, $grid, $cSteer, $note, $btns))
    $chosen = { if ($rAll.Checked) { @($keys[$cAll.SelectedIndex]) } else { @($per.Values | ForEach-Object { $keys[$_.SelectedIndex] }) | Sort-Object -Unique } }.GetNewClosure()
    $bBuild.Add_Click({                                                # runs inside ShowDialog below, so it sees this function's variables
        $todo = @(& $chosen | Where-Object { $script:HandlingFlavors[$_].Digit })
        if (-not $todo.Count) { [void][Windows.Forms.MessageBox]::Show($d, "The game's own handling needs no files.", 'Handling'); return }
        $d.Cursor = [Windows.Forms.Cursors]::WaitCursor
        try {
            $notes = @(); foreach ($k in $todo) { $notes += @(Build-HandlingFlavor $tracks $k) }
            foreach ($b in @($cAll) + @($per.Values)) { $i = $b.SelectedIndex; $b.BeginUpdate(); for ($n = 0; $n -lt $keys.Count; $n++) { $b.Items[$n] = (& $titles $keys[$n]) }; $b.SelectedIndex = $i; $b.EndUpdate() }
            [void][Windows.Forms.MessageBox]::Show($d, ($notes -join "`n"), 'Handling', 'OK', 'Information')
        } catch { [void][Windows.Forms.MessageBox]::Show($d, $_.Exception.Message, 'Handling', 'OK', 'Warning') }
        finally { $d.Cursor = [Windows.Forms.Cursors]::Default }
    })
    if ($OnShown) { $d.Add_Shown($OnShown) }
    $ok = $d.ShowDialog($owner) -eq 'OK'
    $h = @{ Default = $keys[$cAll.SelectedIndex]; Cars = @{}; Steer = $(if ($cSteer.Checked) { $script:SteerReturnSeconds } else { 0.0 }) }
    if ($rPer.Checked) {                                               # car by car: the most used handling becomes the default
        $h.Default = @($per.Values | ForEach-Object { $keys[$_.SelectedIndex] } | Group-Object | Sort-Object Count -Descending)[0].Name
        foreach ($c in $per.Keys) { $h.Cars[$c] = $keys[$per[$c].SelectedIndex] }
    }
    $d.Dispose()
    if ($ok) { return $h }
    return $null
}

# ---- the window ----
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
try { Add-Type -Namespace SR3CamLab -Name Dpi -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();' -ErrorAction Stop } catch { }
try { [void][SR3CamLab.Dpi]::SetProcessDPIAware() } catch { }
[Windows.Forms.Application]::EnableVisualStyles()

function Show-ExtrasWindow([string]$tracks, [switch]$Render, [string]$Png, [int]$Tab = 0, [switch]$Offscreen) {
    $x = @{ Tracks = $tracks; St = (Read-ExtrasState $tracks) }
    $x.Opening = @()
    if (-not $Render -and -not (Get-Process -Name Rally -ErrorAction SilentlyContinue)) {      # your announcer recordings may be new
        try { $x.Opening = @(Update-Announcer $tracks $x.St) + @(Update-TrackSounds $tracks $x.St); Write-ExtrasState $tracks $x.St; Write-SwitchFile $tracks $x.St } catch { $x.Opening = @($_.Exception.Message) }
    }
    $script:Extras = $x
    $form = New-Object Windows.Forms.Form
    $form.Text = 'SR3Ultimate'; $form.Font = New-Object Drawing.Font('Segoe UI', 9)
    $form.AutoScaleMode = [Windows.Forms.AutoScaleMode]::Dpi
    $form.StartPosition = 'CenterScreen'; $form.FormBorderStyle = 'FixedDialog'; $form.MaximizeBox = $false
    $form.AutoSize = $true; $form.AutoSizeMode = 'GrowAndShrink'; $form.Padding = New-Object Windows.Forms.Padding(10)

    $tabs = New-Object Windows.Forms.TabControl; $tabs.Size = New-Object Drawing.Size(940, 660)
    $form.Controls.Add($tabs)
    $page = New-Object Windows.Forms.TabPage; $page.Text = 'Tracks'; $page.Padding = New-Object Windows.Forms.Padding(12); $page.UseVisualStyleBackColor = $true
    $tabs.TabPages.Add($page)
    $grid = New-Object Windows.Forms.TableLayoutPanel; $grid.Dock = 'Fill'; $grid.ColumnCount = 2; $grid.RowCount = 6
    [void]$grid.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Percent, 50)))
    [void]$grid.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Percent, 50)))
    foreach ($h in 'AutoSize', 'AutoSize', 'AutoSize', 'Percent', 'AutoSize', 'AutoSize') {
        [void]$grid.RowStyles.Add($(if ($h -eq 'Percent') { New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::Percent, 100) } else { New-Object Windows.Forms.RowStyle([Windows.Forms.SizeType]::AutoSize) }))
    }
    $page.Controls.Add($grid)
    $mk = { param($text) $l = New-Object Windows.Forms.Label; $l.Text = $text; $l.AutoSize = $true; $l.Margin = New-Object Windows.Forms.Padding(0, 4, 0, 4); $l }

    $intro = & $mk ("Give SEGA Rally 3 more tracks: SEGA Rally Revo's (PC version or PlayStation 3 disc), or the game's own in other places. " +
                    "The three stage cards (Tropical, Canyon, Alpine) can hold several: in the game, View Change on the stage-select screen steps through them. " +
                    "The other slots can only be replaced; their own track is kept safe and comes back with Disable or Remove.")
    $intro.MaximumSize = New-Object Drawing.Size(890, 0)
    $grid.Controls.Add($intro, 0, 0); $grid.SetColumnSpan($intro, 2)

    $revoRow = New-Object Windows.Forms.FlowLayoutPanel; $revoRow.AutoSize = $true; $revoRow.WrapContents = $false; $revoRow.Margin = New-Object Windows.Forms.Padding(0, 6, 0, 8)
    $revoRow.Controls.Add((& $mk 'SEGA Rally Revo folder'))
    $revoBox = New-Object Windows.Forms.TextBox; $revoBox.Width = 600; $revoBox.Text = $x.St.revo; $revoBox.Margin = New-Object Windows.Forms.Padding(8, 2, 6, 0)
    $revoRow.Controls.Add($revoBox)
    $revoBrowse = New-Object Windows.Forms.Button; $revoBrowse.Text = 'Browse...'; $revoBrowse.AutoSize = $true
    $revoRow.Controls.Add($revoBrowse)
    $grid.Controls.Add($revoRow, 0, 1); $grid.SetColumnSpan($revoRow, 2)

    $grid.Controls.Add((& $mk "SEGA Rally 3's track slots"), 0, 2)
    $grid.Controls.Add((& $mk 'Tracks you can put in'), 1, 2)
    $slots = New-Object Windows.Forms.ListView; $slots.View = 'Details'; $slots.FullRowSelect = $true; $slots.MultiSelect = $false; $slots.HideSelection = $false
    $slots.Dock = 'Fill'; $slots.Margin = New-Object Windows.Forms.Padding(0, 0, 8, 0)
    [void]$slots.Columns.Add('Slot', 90); [void]$slots.Columns.Add('Tracks', 340)
    $grid.Controls.Add($slots, 0, 3)
    $sources = New-Object Windows.Forms.ListBox; $sources.Dock = 'Fill'; $sources.IntegralHeight = $false; $sources.HorizontalScrollbar = $true
    $grid.Controls.Add($sources, 1, 3)

    $btnRow = New-Object Windows.Forms.FlowLayoutPanel; $btnRow.AutoSize = $true; $btnRow.Margin = New-Object Windows.Forms.Padding(0, 8, 0, 4)
    $bImport = New-Object Windows.Forms.Button; $bImport.Text = 'Add the selected track to the selected stage card'; $bImport.AutoSize = $true
    $bToggle = New-Object Windows.Forms.Button; $bToggle.Text = 'Disable'; $bToggle.AutoSize = $true
    $bRemove = New-Object Windows.Forms.Button; $bRemove.Text = 'Remove'; $bRemove.AutoSize = $true
    $btnRow.Controls.AddRange(@($bImport, $bToggle, $bRemove))
    $grid.Controls.Add($btnRow, 0, 4); $grid.SetColumnSpan($btnRow, 2)

    $status = & $mk ''
    $status.MaximumSize = New-Object Drawing.Size(890, 0); $status.MinimumSize = New-Object Drawing.Size(890, 54)
    $grid.Controls.Add($status, 0, 5); $grid.SetColumnSpan($status, 2)

    $x.Form = $form; $x.Slots = $slots; $x.Sources = $sources; $x.Revo = $revoBox; $x.Status = $status
    $x.Import = $bImport; $x.Toggle = $bToggle; $x.Remove = $bRemove
    $x.Note = ("Good to know: these tracks weren't made for SEGA Rally 3. Time limits can be tight, some checkpoints may not add time, " +
               "a few tracks load without music, and the odd one freezes or crashes on loading. Tracks added to a stage card need the game " +
               "started with PLAY.bat; Remove takes a track out again.")

    $x.Say = { param($text, $bad) $u = $script:Extras; $u.Status.Text = $text
               $u.Status.ForeColor = $(if ($bad) { [Drawing.Color]::FromArgb(190, 30, 30) } else { [Drawing.SystemColors]::ControlText }) }
    $x.Reload = {
        $u = $script:Extras
        $keepSlot = if ($u.Slots.SelectedItems.Count) { "$($u.Slots.SelectedItems[0].Tag)" } else { '' }
        $keepSrc = if ($u.Sources.SelectedIndex -ge 0) { $u.SrcList[$u.Sources.SelectedIndex].Id } else { '' }
        $u.SlotList = Get-Slots $u.Tracks $u.St
        $u.SrcList = Get-Sources $u.Tracks $u.St
        $u.Slots.BeginUpdate(); $u.Slots.Items.Clear()
        foreach ($s in $u.SlotList) {
            $card = Test-CardSlot $s.Name
            $alts = if ($card) { Get-Alternatives $u.St $s.Name } else { @() }
            $now = if ($s.Enabled) { $s.Source } elseif ($s.Parked) { "its own track   ($($s.Source): disabled)" } else { 'its own track' }
            if ($card -and -not $s.Enabled -and -not $s.Parked) { $now = 'its own track   (stage card)' }
            $it = New-Object Windows.Forms.ListViewItem($s.Name); [void]$it.SubItems.Add($now); $it.Tag = "$($s.Name)|"
            if ($s.Enabled) { $it.ForeColor = [Drawing.Color]::FromArgb(20, 110, 170) }
            [void]$u.Slots.Items.Add($it)
            if ($it.Tag -eq $keepSlot) { $it.Selected = $true }
            foreach ($a in $alts) {
                $row = New-Object Windows.Forms.ListViewItem('     +'); [void]$row.SubItems.Add("$($a.title)   ($($a.source))"); $row.Tag = "$($s.Name)|$($a.dir)"
                $row.ForeColor = [Drawing.Color]::FromArgb(20, 110, 170)
                [void]$u.Slots.Items.Add($row)
                if ($row.Tag -eq $keepSlot) { $row.Selected = $true }
            }
        }
        $u.Slots.EndUpdate()
        $u.Sources.BeginUpdate(); $u.Sources.Items.Clear()
        foreach ($s in $u.SrcList) { [void]$u.Sources.Items.Add((Get-SourceLabel $s)); if ($s.Id -eq $keepSrc) { $u.Sources.SelectedIndex = $u.Sources.Items.Count - 1 } }
        $u.Sources.EndUpdate()
        & $u.Buttons
    }
    $x.Pick = {
        $u = $script:Extras
        $tag = if ($u.Slots.SelectedItems.Count) { "$($u.Slots.SelectedItems[0].Tag)".Split('|') } else { @('', '') }
        $slot = if ($tag[0]) { $u.SlotList | Where-Object { $_.Name -eq $tag[0] } | Select-Object -First 1 } else { $null }
        $src = if ($u.Sources.SelectedIndex -ge 0) { $u.SrcList[$u.Sources.SelectedIndex] } else { $null }
        return @{ Slot = $slot; Src = $src; Alt = $tag[1]; Card = [bool]($slot -and (Test-CardSlot $slot.Name)) }
    }
    $x.Buttons = {
        $u = $script:Extras; $p = & $u.Pick
        $u.Import.Enabled = [bool]($p.Slot -and $p.Src -and $p.Src.Kind -in 'pc', 'ps3' -and $p.Src.Id -ne "sr3:$($p.Slot.Name)")
        $u.Import.Text = if ($p.Card) { 'Add the selected track to the selected stage card' } else { 'Put the selected track into the selected slot' }
        $u.Toggle.Enabled = [bool]($p.Slot -and -not $p.Alt -and ($p.Slot.Enabled -or $p.Slot.Parked))
        $u.Toggle.Text = if ($p.Slot -and $p.Slot.Parked) { 'Enable' } else { 'Disable' }
        $u.Remove.Enabled = [bool]($p.Alt -or $u.Toggle.Enabled)
    }
    $x.Run = { param($what, $done)
        $u = $script:Extras
        try { $u.Form.Cursor = [Windows.Forms.Cursors]::WaitCursor; $r = & $what; & $u.Say ((@($done) + @($r)) -join '  ') $false }
        catch { & $u.Say $_.Exception.Message $true }
        finally { $u.Form.Cursor = [Windows.Forms.Cursors]::Default; $u.St = Read-ExtrasState $u.Tracks; & $u.Reload }
    }

    $slots.Add_SelectedIndexChanged({ & $script:Extras.Buttons })
    $sources.Add_SelectedIndexChanged({
        $u = $script:Extras; & $u.Buttons; $p = & $u.Pick
        if ($p.Src -and $p.Src.Kind -eq 'ps3') { & $u.Say "$($p.Src.Name) is from the PlayStation 3 version. It is converted to the PC layout when you import it (a few seconds). Your disc files are only read." $false }
        else { & $u.Say $u.Note $false }
    })
    $x.SetRevo = {
        $u = $script:Extras; $path = $u.Revo.Text.Trim().Trim('"')
        $u.St.revo = $path; Write-ExtrasState $u.Tracks $u.St; & $u.Reload
        if (-not $path) { & $u.Say $u.Note $false }
        elseif (-not (Find-TracksFolder $path)) { & $u.Say "No tracks found in that folder. Pick SEGA Rally Revo's main folder: the PC game's (it has 'out\main release\tracks' inside) or the PS3 disc's (it has PS3_GAME inside)." $true }
        else { & $u.Say ("Found SEGA Rally Revo's tracks in " + (Find-TracksFolder $path) + '.') $false }
    }
    $revoBox.Add_Leave({ $u = $script:Extras; if ($u.Revo.Text.Trim().Trim('"') -ne $u.St.revo) { & $u.SetRevo } })
    $revoBox.Add_KeyDown({ param($s, $e) if ($e.KeyCode -eq 'Enter') { $e.SuppressKeyPress = $true; & $script:Extras.SetRevo } })
    $revoBrowse.Add_Click({
        $u = $script:Extras
        $d = New-Object Windows.Forms.FolderBrowserDialog; $d.Description = "Pick SEGA Rally Revo's folder"; $d.ShowNewFolderButton = $false
        if ($u.Revo.Text -and (Test-Path -LiteralPath $u.Revo.Text)) { $d.SelectedPath = $u.Revo.Text }
        if ($d.ShowDialog($u.Form) -eq 'OK') { $u.Revo.Text = $d.SelectedPath; & $u.SetRevo }
    })
    $bImport.Add_Click({
        $u = $script:Extras; $p = & $u.Pick
        if (-not ($p.Slot -and $p.Src)) { return }
        if ($p.Card) {
            $q = "Add '$($p.Src.Name)' to the $($script:CardSlots[$p.Slot.Name].Title) stage card?`n`nNothing is replaced. In the game, on the stage-select screen, View Change steps the highlighted card through its tracks (start the game with PLAY.bat)."
            if ([Windows.Forms.MessageBox]::Show($u.Form, $q, 'SR3Ultimate', 'OKCancel', 'Question') -ne 'OK') { return }
            & $u.Run { Add-Alternative $script:Extras.Tracks $script:Extras.St $p.Slot $p.Src }.GetNewClosure() "'$($p.Src.Name)' is on the $($script:CardSlots[$p.Slot.Name].Title) card now."
            return
        }
        $q = "Put '$($p.Src.Name)' into the $($p.Slot.Name) slot?`n`n$($p.Slot.Name)'s own track is kept safe and comes back with Disable or Remove."
        if ([Windows.Forms.MessageBox]::Show($u.Form, $q, 'SR3Ultimate', 'OKCancel', 'Question') -ne 'OK') { return }
        & $u.Run { Import-Track $script:Extras.Tracks $script:Extras.St $p.Slot $p.Src }.GetNewClosure() "$($p.Slot.Name) now plays $($p.Src.Name)."
    })
    $bToggle.Add_Click({
        $u = $script:Extras; $p = & $u.Pick
        if (-not $p.Slot) { return }
        if ($p.Slot.Parked) { & $u.Run { Enable-Track $script:Extras.Tracks $script:Extras.St $p.Slot }.GetNewClosure() "$($p.Slot.Name) plays the imported track again."; return }
        $q = "Are you sure? $($p.Slot.Name) goes back to its own track.`n`nThe imported track is kept, so Enable brings it back."
        if ([Windows.Forms.MessageBox]::Show($u.Form, $q, 'Disable', 'YesNo', 'Question') -ne 'Yes') { return }
        & $u.Run { Disable-Track $script:Extras.Tracks $script:Extras.St $p.Slot }.GetNewClosure() "$($p.Slot.Name) is back to its own track. The imported one is kept for later."
    })
    $bRemove.Add_Click({
        $u = $script:Extras; $p = & $u.Pick
        if (-not $p.Slot) { return }
        if ($p.Alt) {
            $a = (Get-Alternatives $u.St $p.Slot.Name) | Where-Object { $_.dir -eq $p.Alt } | Select-Object -First 1
            $q = "Are you sure? '$($a.title)' is taken off the $($script:CardSlots[$p.Slot.Name].Title) card and its files are deleted from the game folder.`n`n(Your SEGA Rally Revo files are not touched.)"
            if ([Windows.Forms.MessageBox]::Show($u.Form, $q, 'Remove', 'YesNo', 'Warning') -ne 'Yes') { return }
            & $u.Run { Remove-Alternative $script:Extras.Tracks $script:Extras.St $p.Slot.Name $p.Alt }.GetNewClosure() "'$($a.title)' is off the $($script:CardSlots[$p.Slot.Name].Title) card."
            return
        }
        $q = "Are you sure? $($p.Slot.Name) goes back to its own track and the imported track is deleted from the game folder.`n`n(Your SEGA Rally Revo files are not touched.)"
        if ([Windows.Forms.MessageBox]::Show($u.Form, $q, 'Remove', 'YesNo', 'Warning') -ne 'Yes') { return }
        & $u.Run { Remove-Track $script:Extras.Tracks $script:Extras.St $p.Slot }.GetNewClosure() "$($p.Slot.Name) is back to its own track; the imported one is removed."
    })

    # ---- Options: whose co-driver, whose music, and things that are simply on or off ----
    $opt = New-Object Windows.Forms.TabPage; $opt.Text = 'Options'; $opt.Padding = New-Object Windows.Forms.Padding(12); $opt.UseVisualStyleBackColor = $true
    $tabs.TabPages.Add($opt)
    $olist = New-Object Windows.Forms.TableLayoutPanel; $olist.Dock = 'Top'; $olist.AutoSize = $true; $olist.ColumnCount = 2
    # The left column is as wide as the longest text its controls can show (text grows with the display's scaling,
    # the window does not); the explanations get the rest of the page.
    $artTexts = 'Stage pictures: back to the game''s own', 'Stage pictures for the added tracks'
    $wide = 236
    foreach ($t in @($artTexts) + @($script:VoiceSources.Values + $script:MusicSources.Values | ForEach-Object { $_.Title + '   (not made yet)' })) {
        $wide = [Math]::Max($wide, [Windows.Forms.TextRenderer]::MeasureText($t, $form.Font).Width + 34)
    }
    $wide = [Math]::Min($wide, 440); $rest = $tabs.Width - 44 - $wide - 16
    [void]$olist.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::Absolute, ($wide + 16))))
    [void]$olist.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::AutoSize)))
    $opt.Controls.Add($olist)
    # a choice: its name over a drop-down list
    $mkPick = { param($caption)
        $p = New-Object Windows.Forms.FlowLayoutPanel; $p.FlowDirection = 'TopDown'; $p.WrapContents = $false; $p.AutoSize = $true; $p.Margin = New-Object Windows.Forms.Padding(0, 2, 0, 14)
        $l = New-Object Windows.Forms.Label; $l.Text = $caption; $l.AutoSize = $true; $l.Margin = New-Object Windows.Forms.Padding(0, 0, 0, 3)
        $c = New-Object Windows.Forms.ComboBox; $c.DropDownStyle = 'DropDownList'; $c.Width = $wide; $c.Margin = New-Object Windows.Forms.Padding(0)
        $p.Controls.AddRange(@($l, $c)); @{ Panel = $p; Box = $c } }
    $pVoice = & $mkPick 'Co-driver'; $pMusic = & $mkPick 'Music'
    $lVoice = & $mk ''; $lVoice.MaximumSize = New-Object Drawing.Size($rest, 0); $lVoice.Margin = New-Object Windows.Forms.Padding(0, 6, 0, 4)
    $lMusic = & $mk ''; $lMusic.MaximumSize = New-Object Drawing.Size($rest, 0); $lMusic.Margin = New-Object Windows.Forms.Padding(0, 6, 0, 4)
    $bArt = New-Object Windows.Forms.Button; $bArt.Width = $wide; $bArt.Height = 30; $bArt.Margin = New-Object Windows.Forms.Padding(0, 6, 0, 14)
    $lArt = & $mk ''; $lArt.MaximumSize = New-Object Drawing.Size($rest, 0)
    $olist.Controls.Add($pVoice.Panel, 0, 0); $olist.Controls.Add($lVoice, 1, 0); $olist.Controls.Add($pMusic.Panel, 0, 1); $olist.Controls.Add($lMusic, 1, 1)
    $olist.Controls.Add($bArt, 0, 2); $olist.Controls.Add($lArt, 1, 2)
    $bHand = New-Object Windows.Forms.Button; $bHand.Text = 'Handling...'; $bHand.Width = $wide; $bHand.Height = 30; $bHand.Margin = New-Object Windows.Forms.Padding(0, 6, 0, 14)
    $lHand = & $mk ''; $lHand.MaximumSize = New-Object Drawing.Size($rest, 0)
    $olist.Controls.Add($bHand, 0, 3); $olist.Controls.Add($lHand, 1, 3)
    $x.HandText = $lHand
    $oStatus = & $mk ''; $oStatus.MaximumSize = New-Object Drawing.Size(890, 0); $oStatus.Dock = 'Bottom'
    $opt.Controls.Add($oStatus)
    $x.Voice = $pVoice.Box; $x.VoiceText = $lVoice; $x.Music = $pMusic.Box; $x.MusicText = $lMusic; $x.Art = $bArt; $x.ArtText = $lArt; $x.ArtTexts = $artTexts; $x.OptStatus = $oStatus
    # fills a drop-down list with the sources (the ones without files say so) and shows the one that is in the game
    $x.Fill = { param($box, $sources, $now, $ready)
        $box.BeginUpdate(); $box.Items.Clear()
        foreach ($k in $sources.Keys) { [void]$box.Items.Add($sources[$k].Title + $(if ($k -and -not $ready[$k]) { '   (not made yet)' } else { '' })) }
        $box.SelectedIndex = [Math]::Max(0, [Array]::IndexOf(@($sources.Keys), "$now")); $box.EndUpdate()
    }
    $x.Options = {
        $u = $script:Extras
        $ready = @{}; foreach ($k in $script:VoiceSources.Keys) { if ($k) { $ready[$k] = Test-HasWavs (Get-CoDriverDir $k) } }
        & $u.Fill $u.Voice $script:VoiceSources $u.St.codriver $ready
        $u.VoiceText.Text = switch ("$($u.St.codriver)") {
            'sr2'   { "Co-driver: SEGA Rally 2's voice is in the game. Calls it has no clip for keep the game's voice." }
            'src'   { "Co-driver: the voice of the 1995 SEGA Rally Championship is in the game. It knows fewer calls than SEGA Rally 3: " +
                      "'opens', 'tightens' and some 'long' and 'maybe' are left out of what it says, and the calls it never had (bridge, water, road narrows, stay wide...) keep the game's voice." }
            default { "Co-driver: the game's own voice. Pick another one to put its clips into the game's sound file; the game's own clips are kept and come back when you pick it again." }
        }
        $miss = @($script:VoiceSources.Keys | Where-Object { $_ -and -not $ready[$_] } | ForEach-Object { "$($script:VoiceSources[$_].Title): $($script:VoiceSources[$_].Hint)" })
        if ($miss.Count) { $u.VoiceText.Text += "`n" + ($miss -join "`n") }
        $ready = @{}; foreach ($k in $script:MusicSources.Keys) { if ($k) { $ready[$k] = [bool]@(Get-TuneFiles $k).Count } }
        & $u.Fill $u.Music $script:MusicSources $u.St.music $ready
        $u.MusicText.Text = switch ("$($u.St.music)") {
            'src'   { "Music: the tunes of the 1995 SEGA Rally Championship are in the game's sound file, after SEGA's own. Only a 1995 course in the Classic mode plays one " +
                      "(its own), when the game is started with PLAY.bat; a course without a tune, every SEGA Rally 3 stage and the menus play the game's music as always." }
            default { "Music: the game's own. Pick the 1995 game to give its courses in the Classic mode their own tunes: they are added at the end of the game's sound file " +
                      "and taken off again when you pick the game's own. SEGA Rally 3's stages and menus keep their music either way." }
        }
        $miss = @($script:MusicSources.Keys | Where-Object { $_ -and -not $ready[$_] } | ForEach-Object { "$($script:MusicSources[$_].Title): $($script:MusicSources[$_].Hint)" })
        if ($miss.Count) { $u.MusicText.Text += "`n" + ($miss -join "`n") }
        $m = Get-MusicInstall (Get-GameDir $u.Tracks)                # the tune files changed since they were put in?
        if ($m) {
            $now = @(Get-TuneFiles $m.source | ForEach-Object { $fi = Get-Item -LiteralPath $_; "$($fi.Name)|$($fi.Length)|$($fi.LastWriteTimeUtc.Ticks)" } | Sort-Object)
            $was = @($m.tunes | ForEach-Object { "$($_.file)|$($_.fileBytes)|$($_.fileTime)" } | Sort-Object)
            if (($now -join ';') -ne ($was -join ';')) { $u.MusicText.Text += "`nThe tune files in the music folder are not the ones in the game any more: pick the game's own and then the 1995 game again to renew them." }
        }
        $hf = Read-HandlingFile; $cars = Get-HandlingCars $u.Tracks
        $odd = @($cars.Keys | Where-Object { $hf.Cars.ContainsKey($_) -and $hf.Cars[$_] -ne $hf.Default })
        $u.HandText.Text = "Handling: $($script:HandlingFlavors[$hf.Default].Title) for " + $(if ($odd.Count) { "every car but $(($odd | ForEach-Object { "$($cars[$_]) ($($script:HandlingFlavors[$hf.Cars[$_]].Title))" }) -join ', ')." } else { 'every car.' }) +
                           " It takes effect when the game is started with PLAY.bat; the game's own car files are never changed."
        $u.Art.Text = $u.ArtTexts[$(if ($u.St.art) { 0 } else { 1 })]
        $u.ArtText.Text = if ($u.St.art) { 'The tracks you added to a stage card have their own background and banner. This rewrites the game''s menu pictures file (the original is kept). If the game stops starting, switch this off.' }
                          else { "The tracks you added to a stage card show the card's own background and banner. Switching this on rewrites the game's menu pictures file (the original is kept)." }
    }
    $x.Option = { param($what, $done)
        $u = $script:Extras
        try { $u.Form.Cursor = [Windows.Forms.Cursors]::WaitCursor; $r = & $what; $u.OptStatus.ForeColor = [Drawing.SystemColors]::ControlText; $u.OptStatus.Text = ((@($done) + @($r)) -join '  ') }
        catch { $u.OptStatus.ForeColor = [Drawing.Color]::FromArgb(190, 30, 30); $u.OptStatus.Text = $_.Exception.Message }
        finally { $u.Form.Cursor = [Windows.Forms.Cursors]::Default; $u.St = Read-ExtrasState $u.Tracks; & $u.Options }
    }
    # Picking another source asks first, then puts it in; with "Cancel", or when it fails, the list goes back to what is in
    # the game. Nothing here acts by itself: the lists are only filled when the window opens (SelectionChangeCommitted is
    # raised by the user's own pick, never by the filling).
    $pVoice.Box.Add_SelectionChangeCommitted({
        $u = $script:Extras; $key = @($script:VoiceSources.Keys)[$u.Voice.SelectedIndex]
        if ("$key" -eq "$($u.St.codriver)") { return }
        $q = if ($key) { "Put the co-driver of $($script:VoiceSources[$key].Title) into the game's sound file?`n`nThe game's own clips are kept and come back when you pick SEGA Rally 3 again." }
             else { "Put the game's own co-driver back?" }
        if ([Windows.Forms.MessageBox]::Show($u.Form, $q, 'SR3Ultimate', 'OKCancel', 'Question') -ne 'OK') { & $u.Options; return }
        & $u.Option { Set-CoDriverSource $script:Extras.Tracks $key }.GetNewClosure() ''
    })
    $pMusic.Box.Add_SelectionChangeCommitted({
        $u = $script:Extras; $key = @($script:MusicSources.Keys)[$u.Music.SelectedIndex]
        if ("$key" -eq "$($u.St.music)") { return }
        $q = if ($key) { "Add the tunes of $($script:MusicSources[$key].Title) to the game's sound file?`n`nThey go after SEGA's own music, for the 1995 courses in the Classic mode only. Picking SEGA Rally 3 again takes them off and the file is as it was." }
             else { "Take the added tunes off the game's sound file?" }
        if ([Windows.Forms.MessageBox]::Show($u.Form, $q, 'SR3Ultimate', 'OKCancel', 'Question') -ne 'OK') { & $u.Options; return }
        & $u.Option { Set-MusicSource $script:Extras.Tracks $key }.GetNewClosure() ''
    })
    $bArt.Add_Click({
        $u = $script:Extras; $on = [bool]$u.St.art
        & $u.Option { Set-AltArt $script:Extras.Tracks (-not $on) }.GetNewClosure() $(if ($on) { "The game's own menu pictures are back." } else { 'The added tracks have their own pictures now.' })
    })
    # the handling pop-up (Show-HandlingDialog): OK writes handling.json (nothing else), Cancel changes nothing
    $bHand.Add_Click({
        $u = $script:Extras; $h = Show-HandlingDialog $u.Form $u.Tracks
        if ($h) { & $u.Option { Write-HandlingFile $h; @() }.GetNewClosure() 'Handling saved; it takes effect the next time the game is started with PLAY.bat.' }
    })
    & $x.Options

    # ---- under the tabs: play, and the camera tuner ----
    $bar = New-Object Windows.Forms.FlowLayoutPanel; $bar.AutoSize = $true; $bar.WrapContents = $false
    $bar.Location = New-Object Drawing.Point(10, ($tabs.Bottom + 8))
    $bPlay = New-Object Windows.Forms.Button; $bPlay.Text = 'Launch SEGA Rally 3'; $bPlay.AutoSize = $true; $bPlay.Padding = New-Object Windows.Forms.Padding(14, 4, 14, 4)
    $bCam = New-Object Windows.Forms.Button; $bCam.Text = 'Open CamLab (cameras)'; $bCam.AutoSize = $true; $bCam.Padding = New-Object Windows.Forms.Padding(14, 4, 14, 4)
    $bCam.Enabled = Test-Path -LiteralPath (Join-Path $PSScriptRoot 'camlab.exe')
    $bar.Controls.AddRange(@($bPlay, $bCam)); $form.Controls.Add($bar)
    # the same PLAY.bat you can double-click: it starts the game and puts every mod in
    $bPlay.Add_Click({
        $u = $script:Extras
        if (Get-Process -Name Rally -ErrorAction SilentlyContinue) { & $u.Say 'SEGA Rally 3 is already running.' $true; return }
        $bat = Join-Path $PSScriptRoot 'PLAY.bat'
        if (-not (Test-Path -LiteralPath $bat)) { & $u.Say "PLAY.bat isn't next to SR3Ultimate." $true; return }
        Start-Process -FilePath $bat -WorkingDirectory $PSScriptRoot
        & $u.Say 'Starting the game with PLAY.bat (its window shows what it is doing)...' $false
    })
    $bCam.Add_Click({ Start-Process -FilePath (Join-Path $PSScriptRoot 'camlab.exe') -WorkingDirectory $PSScriptRoot })

    & $x.Reload
    if ($x.Opening.Count) { & $x.Say ($x.Opening -join '  ') $false } else { & $x.Say $x.Note $false }
    if ($Render) {                                                # a picture of the window (-Tab: which page), for the documentation and for checks
        $tabs.SelectedIndex = [Math]::Max(0, [Math]::Min($Tab, $tabs.TabPages.Count - 1))
        if ($Offscreen) {                                         # the window is never on screen: its controls are made unshown and print themselves
            [void][Windows.Forms.Control].GetMethod('CreateControl', [Reflection.BindingFlags]'NonPublic, Instance', $null, [Type[]]@([bool]), $null).Invoke($form, @($true))
            $form.PerformLayout()
        } else { $form.Show(); [Windows.Forms.Application]::DoEvents() }
        $bmp = New-Object Drawing.Bitmap $form.Width, $form.Height
        $form.DrawToBitmap($bmp, (New-Object Drawing.Rectangle 0, 0, $form.Width, $form.Height))
        if ($Offscreen -and $tabs.SelectedTab -eq $opt) {         # an unshown drop-down list prints its frame but not its text
            $g = [Drawing.Graphics]::FromImage($bmp)
            foreach ($c in $x.Voice, $x.Music) {
                $at = $c.PointToScreen((New-Object Drawing.Point 0, 0))
                [Windows.Forms.TextRenderer]::DrawText($g, $c.Text, $c.Font, (New-Object Drawing.Rectangle ($at.X - $form.Left + 4), ($at.Y - $form.Top), ($c.Width - 24), $c.Height), [Drawing.SystemColors]::ControlText, [Windows.Forms.TextFormatFlags]'Left, VerticalCenter, EndEllipsis')
            }
            $g.Dispose()
        }
        $bmp.Save($Png); $bmp.Dispose(); $form.Close(); return
    }
    [void]$form.ShowDialog()
    $form.Dispose()
}

if ($NoWindow) { return }

$setup = Find-Setup
$tracksDir = Get-TracksDir $setup.game
if ($AltArt) {                                                    # SR3Ultimate.bat -AltArt on / off
    if (-not $tracksDir) { "SR3Ultimate can't find SEGA Rally 3's tracks folder. Run PLAY.bat -Setup first."; return }
    try {
        $n = Set-AltArt $tracksDir ($AltArt -eq 'on')
        if ($AltArt -eq 'on') { "Banners and backgrounds of the stage cards' alternative tracks: ON. The game's menu pictures file was rewritten; the original is kept. $n" }
        else { "Banners and backgrounds of the alternative tracks: OFF. The game's menu pictures file is the original again. $n" }
    } catch { "Nothing was changed: $($_.Exception.Message)" }
    return
}
if ($CoDriver -or $Music) {                                       # SR3Ultimate.bat -CoDriver sr3 / sr2 / src (on = sr2, off = sr3)   -Music sr3 / src (off = sr3)
    if (-not $tracksDir) { "SR3Ultimate can't find SEGA Rally 3's tracks folder. Run PLAY.bat -Setup first."; return }
    if ($CoDriver) {
        $source = switch ($CoDriver) { 'on' { 'sr2' } 'off' { '' } 'sr3' { '' } default { $CoDriver } }
        try { (Set-CoDriverSource $tracksDir $source) -join ' ' } catch { "Co-driver: nothing was changed: $($_.Exception.Message)" }
    }
    if ($Music) {
        $source = switch ($Music) { 'off' { '' } 'sr3' { '' } default { $Music } }
        try { (Set-MusicSource $tracksDir $source) -join ' ' } catch { "Music: nothing was changed: $($_.Exception.Message)" }
    }
    return
}
if (-not $tracksDir) {
    [void][Windows.Forms.MessageBox]::Show("SR3Ultimate can't find SEGA Rally 3's tracks folder. Run PLAY.bat -Setup first, so it knows where the game is.", 'SR3Ultimate', 'OK', 'Warning')
    return
}
Show-ExtrasWindow $tracksDir

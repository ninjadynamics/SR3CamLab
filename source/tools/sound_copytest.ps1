# Checks the settings app's co-driver and music switching on a COPY of the game's sound files, never on the game.
#   Co-driver: every voice is put in and taken out again; each time the replaced streams must hold exactly their WAV
#     files. (In place: the sound file keeps its size.)
#   Music: the tunes are appended after SEGA's last stream. The part of the file that was there before must not change
#     by a byte, the appended part must be exactly the tunes, switch.json must give a tune to the 1995 courses of the
#     Classic mode only, and taking the music out must leave the file as it was.
#   At the end the copy must be byte-identical to the game's own file, with the same kept originals.
# The copy (about 500 MB) is deleted afterwards unless -Keep is given.
#   powershell -NoProfile -ExecutionPolicy Bypass -File tools\sound_copytest.ps1 [-Work <folder>] [-Keep]
# Tunes: the ones in SR3CamLab\music\src when there are any; otherwise short stand-ins cut from the game's own music.
param([string]$Work = (Join-Path $env:TEMP 'sr3lab_soundtest'), [switch]$Keep)
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\extras.ps1') -NoWindow
$realTracks = Get-TracksDir (Find-Setup).game
if (-not $realTracks) { "SEGA Rally 3 was not found (run PLAY.bat -Setup first)."; return }
$realGame = Get-GameDir $realTracks; $realStore = Get-StoreDir $realTracks
$tracks = Join-Path $Work 'Rally\Main_release\tracks'; $game = Get-GameDir $tracks; $store = Get-StoreDir $tracks
if ($Work.ToLower().StartsWith($realGame.ToLower())) { "The work folder must not be inside the game folder."; return }
$data = Join-Path $game 'Audio\EnglishStreamData.stm'; $realData = Join-Path $realGame 'Audio\EnglishStreamData.stm'
function Assert-GameClosed { }                                    # the copy is not the running game's
# SHA-256 of a file, or of its first $length bytes
function Get-Sha([string]$file, [long]$length = -1) {
    $sha = [Security.Cryptography.SHA256]::Create(); $fs = [IO.File]::OpenRead($file); $buf = New-Object byte[] 4194304
    try {
        $left = if ($length -lt 0) { $fs.Length } else { [Math]::Min($length, $fs.Length) }
        while ($left -gt 0) { $n = $fs.Read($buf, 0, [int][Math]::Min($buf.Length, $left)); if ($n -le 0) { break }; [void]$sha.TransformBlock($buf, 0, $n, $null, 0); $left -= $n }
        [void]$sha.TransformFinalBlock($buf, 0, 0)
    } finally { $fs.Dispose() }
    return [BitConverter]::ToString($sha.Hash).Replace('-', '')
}
function Get-KeptSignature([string]$dir) {                         # names, sizes and contents of a folder of kept originals
    if (-not (Test-Path -LiteralPath $dir)) { return 'none' }
    $lines = Get-ChildItem -LiteralPath $dir -File | Sort-Object Name | ForEach-Object { "$($_.Name):$($_.Length):$((Get-FileHash -LiteralPath $_.FullName -Algorithm MD5).Hash)" }
    return "$(@($lines).Count) files " + [BitConverter]::ToString([Security.Cryptography.MD5]::Create().ComputeHash([Text.Encoding]::UTF8.GetBytes(($lines -join "`n")))).Replace('-', '').Substring(0, 12)
}

# ---- the copy ----
if (Test-Path -LiteralPath $Work) { Remove-Item -LiteralPath $Work -Recurse -Force }
[void][IO.Directory]::CreateDirectory((Join-Path $game 'Audio')); [void][IO.Directory]::CreateDirectory((Join-Path $store 'original'))
foreach ($f in 'EnglishStreamHeader.stm', 'EnglishStreamData.stm') { [IO.File]::Copy((Join-Path $realGame "Audio\$f"), (Join-Path $game "Audio\$f")) }
foreach ($f in 'state.json', 'classic.json', 'sounds.json', 'music.json') { if (Test-Path -LiteralPath (Join-Path $realStore $f)) { [IO.File]::Copy((Join-Path $realStore $f), (Join-Path $store $f)) } }
foreach ($d in 'codriver', 'sounds') {
    $from = Join-Path $realStore "original\$d"
    if (Test-Path -LiteralPath $from) { Copy-Item -LiteralPath $from -Destination (Join-Path $store 'original') -Recurse }
}
foreach ($f in Get-ChildItem -LiteralPath (Join-Path $realStore 'original') -Filter 'announcer_*.bin' -File -ErrorAction SilentlyContinue) { [IO.File]::Copy($f.FullName, (Join-Path $store "original\$($f.Name)")) }
# the Classic alternatives: their folders with the start of the importer's texmap.json (what tells which course each one is),
# and two made-up ones: a course of another game with a 1995 course's name, and a track nobody built
$classic = @()
if (Test-Path -LiteralPath (Join-Path $store 'classic.json')) { $classic = @([IO.File]::ReadAllText((Join-Path $store 'classic.json')) | ConvertFrom-Json | ForEach-Object { $_ } | Where-Object { "$($_.dir)" -match '^[1-7]$' }) }
foreach ($c in $classic) {
    $to = Get-AltDir $tracks "$($c.dir)" 'Desert4'; [void][IO.Directory]::CreateDirectory($to)
    $tm = Join-Path (Get-AltDir $realTracks "$($c.dir)" 'Desert4') 'texmap.json'
    if (Test-Path -LiteralPath $tm) { $b = New-Object byte[] 600; $fs = [IO.File]::OpenRead($tm); try { $n = $fs.Read($b, 0, 600) } finally { $fs.Dispose() }; $fs = [IO.File]::Create((Join-Path $to 'texmap.json')); try { $fs.Write($b, 0, $n) } finally { $fs.Dispose() } }
}
$made = @(@{ dir = '8'; title = 'Mountain'; texmap = '{"extra_tex": "X:\\classic\\courses\\sr2\\course1\\textures", ' }, @{ dir = '9'; title = 'Test track'; texmap = '' })
foreach ($c in $made) { $to = Get-AltDir $tracks $c.dir 'Desert4'; [void][IO.Directory]::CreateDirectory($to); if ($c.texmap) { [IO.File]::WriteAllText((Join-Path $to 'texmap.json'), $c.texmap) } }
[IO.File]::WriteAllText((Join-Path $store 'classic.json'), (@(@($classic | ForEach-Object { @{ dir = "$($_.dir)"; title = "$($_.title)" } }) + @($made | ForEach-Object { @{ dir = $_.dir; title = $_.title } })) | ConvertTo-Json))
$startSha = Get-Sha $realData
if ((Get-Sha $data) -ne $startSha) { "The copy does not match the game's file."; return }
$start = Read-ExtrasState $tracks
"copy made in $Work; the game has: co-driver '$($start.codriver)', music '$($start.music)'"

# ---- stand-in tunes when the 1995 ones are not made yet ----
$standIn = -not @(Get-TuneFiles 'src').Count
if ($standIn) {
    $script:TestMusicDir = Join-Path $Work 'music_standin\src'; [void][IO.Directory]::CreateDirectory($script:TestMusicDir)
    function Get-MusicDir([string]$source) { return $script:TestMusicDir }
    $s = (Read-StreamLayout $game 2).Streams['coastal1_1']; $fs = [IO.File]::OpenRead($data)
    function Write-TestWav([string]$file, [byte[]]$pcm, [int]$channels) {
        $w = New-Object IO.BinaryWriter([IO.File]::Create($file))
        try {
            $w.Write([Text.Encoding]::ASCII.GetBytes('RIFF')); $w.Write([int](36 + $pcm.Length)); $w.Write([Text.Encoding]::ASCII.GetBytes('WAVEfmt ')); $w.Write([int]16)
            $w.Write([int16]1); $w.Write([int16]$channels); $w.Write([int]32000); $w.Write([int](64000 * $channels)); $w.Write([int16](2 * $channels)); $w.Write([int16]16)
            $w.Write([Text.Encoding]::ASCII.GetBytes('data')); $w.Write([int]$pcm.Length); $w.Write($pcm)
        } finally { $w.Dispose() }
    }
    try {
        $k = 0
        foreach ($t in @(@('mountain', 12, 2), @('desert', 20, 2), @('forest', 3, 1))) {       # forest: mono, must be refused
            $pcm = New-Object byte[] (128000 * $t[1]); $fs.Position = $s.Offset + 1280000 * (++$k); [void]$fs.Read($pcm, 0, $pcm.Length)
            Write-TestWav (Join-Path $script:TestMusicDir "$($t[0]).wav") $pcm $t[2]
        }
    } finally { $fs.Dispose() }
    # mountain loops from its second second on; the note for desert is for another file (wrong length) and must be ignored
    [IO.File]::WriteAllText((Join-Path $script:TestMusicDir 'tunes.json'), '{ "mountain": { "frames": 384000, "loop_start": 32000 }, "desert": { "frames": 123, "loop_start": 64 } }')
    "music: no 1995 tunes in SR3CamLab\music\src yet, so stand-ins cut from the game's own music are used (two good ones, one of a wrong format)"
}

# ---- what must be in the copy for a choice ----
$script:Problems = New-Object System.Collections.ArrayList
function Fail([string]$what) { [void]$script:Problems.Add($what) }
# every speech stream that has a WAV in $dir holds exactly that WAV (then silence, or cut); returns how many
function Test-Voice([string]$dir) {
    $streams = Get-AnnouncerStreams $game 1; $sha = [Security.Cryptography.SHA256]::Create(); $n = 0
    $spare = @{}; foreach ($s in $script:AnnouncerSpares.Values) { $spare[$s.Stream] = $true }
    $fs = [IO.File]::OpenRead($data)
    try {
        foreach ($f in Get-ChildItem -LiteralPath $dir -Filter '*.wav' -File) {
            $name = [IO.Path]::GetFileNameWithoutExtension($f.Name).ToLower(); $s = $streams[$name]
            if (-not $s -or $spare[$name] -or $s.Rate -ne 32000) { continue }
            $pcm = Read-WavSamples $f.FullName 32000 1; if ($null -eq $pcm) { continue }
            $want = New-Object byte[] $s.Size; [Array]::Copy($pcm, 0, $want, 0, [Math]::Min($pcm.Length - ($pcm.Length % 2), $s.Size - ($s.Size % 2)))
            $got = New-Object byte[] $s.Size; $fs.Position = $s.Offset; [void]$fs.Read($got, 0, $s.Size)
            if ([BitConverter]::ToString($sha.ComputeHash($got)) -ne [BitConverter]::ToString($sha.ComputeHash($want))) { Fail "stream $name does not hold its WAV" }
            $n++
        }
    } finally { $fs.Dispose() }
    return $n
}
# the appended tunes: each one's 192-byte block and samples exactly where music.json says, and the file ends there
function Test-Music {
    $m = Get-MusicInstall $game; if (-not $m) { Fail 'music.json and the sound file do not agree'; return 0 }
    $end = (Read-StreamLayout $game).End; $sha = [Security.Cryptography.SHA256]::Create(); $at = $end; $n = 0
    if ($m.dataLength -ne $end) { Fail 'music.json does not start at the end of SEGA''s last stream' }
    $fs = [IO.File]::OpenRead($data)
    try {
        foreach ($t in $m.tunes) {
            $pcm = Read-WavSamples (Join-Path (Get-MusicDir $m.source) "$($t.file)") 32000 2
            if ([long]"$($t.offset)" -ne $at -or [long]"$($t.bytes)" -ne $pcm.Length - ($pcm.Length % 4)) { Fail "tune $($t.course) is not where it should be" }
            $got = New-Object byte[] ([int]"$($t.bytes)"); $fs.Position = $at + 192; [void]$fs.Read($got, 0, $got.Length)
            $want = New-Object byte[] $got.Length; [Array]::Copy($pcm, 0, $want, 0, $got.Length)
            if ([BitConverter]::ToString($sha.ComputeHash($got)) -ne [BitConverter]::ToString($sha.ComputeHash($want))) { Fail "tune $($t.course): the samples in the sound file are not the WAV's" }
            $at += 192 + $got.Length; $n++
        }
        if ($at -ne $fs.Length) { Fail 'the sound file does not end with the last tune' }
    } finally { $fs.Dispose() }
    return $n
}
# switch.json: a tune for the Classic alternatives that are 1995 courses with a tune in the file, for nothing else
function Test-Switch {
    $m = Get-MusicInstall $game; $f = Join-Path $store 'switch.json'; $out = @()
    $j = if (Test-Path -LiteralPath $f) { [IO.File]::ReadAllText($f) | ConvertFrom-Json } else { $null }
    foreach ($p in @($(if ($j) { $j.slots.PSObject.Properties }))) {
        foreach ($t in @($p.Value.tracks)) {
            $course = if ($p.Name -eq 'Desert4') { Get-ClassicCourse $tracks "$($t.dir)" "$($t.title)" } else { '' }
            $has = @(if ($m -and $course) { $m.tunes | Where-Object { "$($_.course)" -eq $course } })
            if ($t.tune -and -not ($course -and $has.Count)) { Fail "'$($t.title)' on $($p.Name) has a tune it must not have" }
            if (-not $t.tune -and $course -and $has.Count) { Fail "'$($t.title)' has no tune though its course has one" }
            if ($t.tune -and $has.Count -and ("$($t.tune.offset)" -ne "$($has[0].offset)" -or "$($t.tune.bytes)" -ne "$($has[0].bytes)" -or "$($t.tune.loopstart)" -ne "$($has[0].loopstart)" -or "$($t.tune.stream)" -ne "$($m.stream)")) { Fail "'$($t.title)': the tune's place in switch.json is not the one in music.json" }
            if ($p.Name -eq 'Desert4') { $out += "'$($t.title)' " + $(if ($t.tune) { "-> $course tune (loop from byte $($t.tune.loopstart))" } else { '-> the Classic mode''s own music' }) }
        }
    }
    return ($out -join '; ')
}
function Step([string]$what, [scriptblock]$act, [string]$source = '') {
    $before = Read-ExtrasState $tracks; $shaBefore = Get-Sha $data; $lenBefore = (Get-Item -LiteralPath $data).Length
    try { $r = (& $act $source) -join ' ' } catch { $r = "THROWN: $($_.Exception.Message)"; Fail 'the step threw' }
    $st = Read-ExtrasState $tracks; $len = (Get-Item -LiteralPath $data).Length; $end = (Read-StreamLayout $game).End
    "{0,-28} file {1} bytes, {2}  kept co-driver clips: {3}   {4}" -f $what, $len, (Get-Sha $data).Substring(0, 12), (Get-KeptSignature (Join-Path $store 'original\codriver')), $r
    if ($st.codriver) { $n = Test-Voice (Get-CoDriverDir $st.codriver); "   co-driver '$($st.codriver)': $n streams hold exactly their WAV" }
    if ($st.music) { $n = Test-Music; "   music '$($st.music)': $n tunes lie after SEGA's last stream, exactly as their WAV files" } elseif ($len -ne $end) { Fail 'no music, but the sound file does not end with SEGA''s last stream' }
    if ($before.music -ne $st.music) {                               # the music came or went: SEGA's part of the file must be what it was
        $same = if ($st.music) { $lenBefore -eq $end -and (Get-Sha $data $lenBefore) -eq $shaBefore } else { $len -eq $end }
        if (-not $same) { Fail "SEGA's part of the sound file changed" } else { "   SEGA's part of the sound file (the first $end bytes) is unchanged" }
        "   Classic mode: " + (Test-Switch)
    } else { [void](Test-Switch) }
}

# ---- every choice, then back to where the game is ----
$voices = @($script:VoiceSources.Keys | Where-Object { $_ -and (Test-HasWavs (Get-CoDriverDir $_)) })
$setVoice = { param($source) Set-CoDriverSource $tracks $source }; $setMusic = { param($source) Set-MusicSource $tracks $source }
if ($start.music) { Step 'music -> own' $setMusic '' }
Step 'co-driver -> own' $setVoice ''
$ownSha = Get-Sha $data
foreach ($v in $voices) { Step "co-driver -> $v" $setVoice $v }
$shaVoice = Get-Sha $data
Step 'music -> src' $setMusic 'src'
foreach ($v in $voices) { Step "co-driver -> $v (music in)" $setVoice $v }
Step 'music -> src (again)' $setMusic 'src'
Step 'music -> own' $setMusic ''
if ((Get-Sha $data) -ne $shaVoice) { Fail 'after the music came and went the file is not what it was before' } else { '   the file is byte for byte what it was before the music was added' }
Step 'co-driver -> own' $setVoice ''
if ((Get-Sha $data) -ne $ownSha) { Fail 'not the same file as the first time everything was the game''s own' }
if ($standIn -and $start.music) { "(the game has music in and its tunes are not in SR3CamLab\music\src: the start state cannot be rebuilt, the last comparison is skipped)" }
else {
    if ($start.codriver) { Step "back: co-driver -> $($start.codriver)" $setVoice $start.codriver }
    if ($start.music) { Step "back: music -> $($start.music)" $setMusic $start.music }
    $same = (Get-Sha $data) -eq $startSha
    $kept = (Get-KeptSignature (Join-Path $store 'original\codriver')) -eq (Get-KeptSignature (Join-Path $realStore 'original\codriver'))
    if (-not ($same -and $kept)) { Fail 'the copy did not come back to the game''s state' }
    "the copy is byte-identical to the game's sound file again: $same;  its kept originals are the game's: $kept"
}
"the game's own file was not touched: $((Get-Sha $realData) -eq $startSha)"
if ($script:Problems.Count) { "RESULT: $($script:Problems.Count) PROBLEM(S):"; $script:Problems | ForEach-Object { "   $_" } } else { 'RESULT: all good' }
if (-not $Keep) { Remove-Item -LiteralPath $Work -Recurse -Force }

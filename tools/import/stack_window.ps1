# The import stack's window: folders, a course, a checklist of steps (each with its own .blend export), HD textures, the 1995 audio.
# It writes tools\import\settings.json and runs stack.py with the Python next to it (tools\python, the release zip's) or yours.
#   powershell -STA -ExecutionPolicy Bypass -File stack_window.ps1        (IMPORT.bat in the repository's folder does this)
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
[Windows.Forms.Application]::EnableVisualStyles()
$Here = $PSScriptRoot; $Repo = (Resolve-Path (Join-Path $Here '..\..')).Path
$SettingsFile = Join-Path $Here 'settings.json'

function Find-Py {
    $b = Join-Path $Repo 'tools\python\python.exe'                   # the toolchain zip's
    if (Test-Path -LiteralPath $b) { return $b }
    if ($S -and $S.python -and (Test-Path -LiteralPath "$($S.python)")) { return "$($S.python)" }      # winget's (setup_toolchain.ps1 -Winget)
    foreach ($n in 'python', 'py') { $c = Get-Command $n -ErrorAction SilentlyContinue; if ($c) { return $c.Source } }
    return $null
}
function Find-Gcc {
    foreach ($g in @((Join-Path $Repo 'tools\mingw\bin\gcc.exe'), "$($S.gcc)")) { if ($g -and (Test-Path -LiteralPath $g)) { return $g } }
    $w = @(Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\BrechtSanders.WinLibs*\mingw64\bin\gcc.exe') -ErrorAction SilentlyContinue)
    if ($w.Count) { return $w[0].FullName }
    $c = Get-Command gcc -ErrorAction SilentlyContinue; if ($c) { return $c.Source }
    if (Test-Path -LiteralPath 'C:\mingw64\bin\gcc.exe') { return 'C:\mingw64\bin\gcc.exe' }
    return $null
}

function Read-Settings {
    $s = @{ data_root = ''; roms = ''; sr3_game = ''; blender = ''; mame = ''; threads = 'all_but_one' }
    if (Test-Path -LiteralPath $SettingsFile) {
        try { $j = [IO.File]::ReadAllText($SettingsFile) | ConvertFrom-Json; foreach ($p in $j.PSObject.Properties) { $s[$p.Name] = $p.Value } } catch { }
    }
    return $s
}
function Write-Settings($s) {
    $o = [ordered]@{}; foreach ($k in @($s.Keys | Sort-Object)) { $o[$k] = $s[$k] }
    $t = (ConvertTo-Json $o) -replace "`r`n", "`n"
    [IO.File]::WriteAllText($SettingsFile, $t + "`n", (New-Object Text.UTF8Encoding($false)))      # UTF-8 without BOM, LF
}
$S = Read-Settings; $Py = Find-Py

# ---- the courses the stack can build: a recipe beside the course JSON ----
$GameNames = @{ src = 'SEGA Rally Championship'; sr2 = 'SEGA Rally 2'; daytona = 'Daytona USA' }
$Courses = @()
foreach ($r in @(Get-ChildItem -Path (Join-Path $Here '*\tracks\courses\*.recipe.json') -ErrorAction SilentlyContinue)) {
    if ($r.Name -match '^([a-z0-9]+)_(\d+)\.recipe\.json$') {
        $g = $Matches[1]; $n = $Matches[2]; $cj = Join-Path $r.DirectoryName "$($g)_$n.json"; $name = "course $n"
        try { $c = [IO.File]::ReadAllText($cj) | ConvertFrom-Json; if ($c.name) { $name = (Get-Culture).TextInfo.ToTitleCase("$($c.name)") } } catch { }
        $np = @(Get-ChildItem -Path (Join-Path $r.DirectoryName "$g.*.patch.*.json") -ErrorAction SilentlyContinue | Where-Object { $_.Name -match "^$g\.$([regex]::Escape($c.name))\.patch\.\d+\.json$" }).Count
        $Courses += [pscustomobject]@{ Game = $g; Course = $n; Label = "$($GameNames[$g]) - $name"; Name = "$($c.name)"; Patches = $np; Gameplay = "$($c.gameplay)" }
    }
}

# ---- window ----
$F = New-Object Windows.Forms.Form; $F.Text = 'SR3Lab - track import'; $F.Size = New-Object Drawing.Size(940, 820); $F.StartPosition = 'CenterScreen'
$F.Font = New-Object Drawing.Font('Segoe UI', 9); $F.MinimumSize = New-Object Drawing.Size(860, 700)
$tip = New-Object Windows.Forms.ToolTip
function Add-Ctl($parent, $c, $x, $y, $w, $h) { $c.Location = New-Object Drawing.Point($x, $y); $c.Size = New-Object Drawing.Size($w, $h); $parent.Controls.Add($c); return $c }
function New-Label($text) { $l = New-Object Windows.Forms.Label; $l.Text = $text; $l.TextAlign = 'MiddleLeft'; return $l }

# folders
$gF = Add-Ctl $F (New-Object Windows.Forms.GroupBox) 10 8 905 190; $gF.Text = 'Folders (saved in tools\import\settings.json)'
$Rows = @(
    @{ Key = 'data_root'; Label = 'Data folder'; Kind = 'dir'; Hint = 'Where extracts, builds and textures go (work\ and classic\). Empty = the repository''s data folder.' },
    @{ Key = 'roms'; Label = 'ROM sets'; Kind = 'dir'; Hint = 'The folder that holds your own srallyc.zip.' },
    @{ Key = 'sr3_game'; Label = 'SEGA Rally 3'; Kind = 'dir'; Hint = 'The game''s folder, the one with Rally.exe. Empty = the one PLAY.bat knows (setup.yaml).' },
    @{ Key = 'blender'; Label = 'Blender (optional)'; Kind = 'exe'; Hint = 'blender.exe, only for the .blend exports.' },
    @{ Key = 'mame'; Label = 'MAME (optional)'; Kind = 'exe'; Hint = 'mame.exe, only for recording the 1995 music.' })
$Boxes = @{}; $Marks = @{}; $y = 22
foreach ($r in $Rows) {
    $l = Add-Ctl $gF (New-Label $r.Label) 10 $y 130 23; $tip.SetToolTip($l, $r.Hint)
    $t = Add-Ctl $gF (New-Object Windows.Forms.TextBox) 140 $y 560 23; $t.Text = "$($S[$r.Key])"; $tip.SetToolTip($t, $r.Hint); $Boxes[$r.Key] = $t
    $b = Add-Ctl $gF (New-Object Windows.Forms.Button) 706 ($y - 1) 80 25; $b.Text = 'Browse...'; $b.Tag = $r
    $m = Add-Ctl $gF (New-Label '') 792 $y 108 23; $Marks[$r.Key] = $m
    $b.Add_Click({
        $r = $this.Tag
        if ($r.Kind -eq 'dir') { $d = New-Object Windows.Forms.FolderBrowserDialog; $d.SelectedPath = $Boxes[$r.Key].Text; if ($d.ShowDialog() -eq 'OK') { $Boxes[$r.Key].Text = $d.SelectedPath } }
        else { $d = New-Object Windows.Forms.OpenFileDialog; $d.Filter = 'Programs (*.exe)|*.exe'; if ($d.ShowDialog() -eq 'OK') { $Boxes[$r.Key].Text = $d.FileName } }
    })
    $t.Add_TextChanged({ Save-Folders; Update-Marks })
    $y += 28
}
$lT = Add-Ctl $gF (New-Label 'Worker threads') 10 $y 130 23
$cT = Add-Ctl $gF (New-Object Windows.Forms.ComboBox) 140 $y 260 23; $cT.DropDownStyle = 'DropDownList'
$nc = [Environment]::ProcessorCount
[void]$cT.Items.Add("All but one ($([Math]::Max(1, $nc - 1)) of $nc) - the PC stays usable"); [void]$cT.Items.Add("All ($nc) - fastest")
$cT.SelectedIndex = $(if ("$($S.threads)" -eq 'all') { 1 } else { 0 })
$cT.Add_SelectedIndexChanged({ Save-Folders })

function Save-Folders {
    foreach ($k in $Boxes.Keys) { $S[$k] = $Boxes[$k].Text.Trim() }
    $S.threads = $(if ($cT.SelectedIndex -eq 1) { 'all' } else { 'all_but_one' })
    Write-Settings $S
}
function Update-Marks {
    $ok = { param($c, $txt) $Marks[$c].Text = $txt; $Marks[$c].ForeColor = $(if ($txt -like 'ok*' -or $txt -like 'found*') { [Drawing.Color]::DarkGreen } else { [Drawing.Color]::DarkRed }) }
    $d = $Boxes.data_root.Text.Trim(); & $ok 'data_root' $(if (-not $d) { 'ok (default)' } elseif (Test-Path -LiteralPath $d) { 'ok' } else { 'will be made' })
    $r = $Boxes.roms.Text.Trim(); & $ok 'roms' $(if ($r -and (Test-Path -LiteralPath (Join-Path $r 'srallyc.zip'))) { 'found srallyc.zip' } else { 'no srallyc.zip' })
    $g = $Boxes.sr3_game.Text.Trim(); & $ok 'sr3_game' $(if (-not $g) { 'ok (setup.yaml)' } elseif (Test-Path -LiteralPath (Join-Path $g 'Rally.exe')) { 'found Rally.exe' } else { 'no Rally.exe' })
    foreach ($k in 'blender', 'mame') { $v = $Boxes[$k].Text.Trim(); & $ok $k $(if (-not $v) { 'not set' } elseif (Test-Path -LiteralPath $v) { 'found' } else { 'not found' }) }
}

# course
$gC = Add-Ctl $F (New-Object Windows.Forms.GroupBox) 10 204 905 56; $gC.Text = 'Course'
$cC = Add-Ctl $gC (New-Object Windows.Forms.ComboBox) 10 22 540 23; $cC.DropDownStyle = 'DropDownList'
foreach ($c in $Courses) { [void]$cC.Items.Add($c.Label) }
$lC = Add-Ctl $gC (New-Label '') 560 22 340 23

# steps
$gS = Add-Ctl $F (New-Object Windows.Forms.GroupBox) 10 266 905 250; $gS.Text = 'Steps (each one needs the ones before it to have run once)'
$StepRows = @(
    @{ Key = 'rom'; Text = '1. Import from the ROM set'; Blend = $true; Hint = 'The 1995 game''s geometry, textures, gameplay data and times, from your srallyc.zip, into the data folder.' },
    @{ Key = 'patch'; Text = '2. Patch chain'; Blend = $true; Hint = 'The course''s numbered patch files, applied in order (off = the course as the ROM gives it).' },
    @{ Key = 'round'; Text = '3. Rounding'; Blend = $true; Hint = 'Natural surfaces rounded outwards (R4 = the default; never inwards, never the road).' },
    @{ Key = 'light'; Text = '4. Light maps'; Blend = $false; Hint = 'The polygons to light, laid out on light-map pages. Off = the track is built flat-lit.' },
    @{ Key = 'rt'; Text = '5. Ray tracing'; Blend = $true; Hint = 'The light maps baked by ray tracing (every worker thread), then composed.' },
    @{ Key = 'build'; Text = '6. Game files'; Blend = $true; Hint = 'SEGA Rally 3''s track files, in <data>\work\out\<name>\Desert4.' },
    @{ Key = 'install'; Text = '7. Install in SEGA Rally 3'; Blend = $false; Hint = 'As a Classic mode alternative (SR3 Extras switches it in when PLAY.bat starts the game). The game must be closed.' })
$Chk = @{}; $BlendChk = @{}; $State = @{}; $y = 22
foreach ($r in $StepRows) {
    $c = Add-Ctl $gS (New-Object Windows.Forms.CheckBox) 10 $y 250 24; $c.Text = $r.Text; $c.Checked = ($r.Key -ne 'install'); $tip.SetToolTip($c, $r.Hint); $Chk[$r.Key] = $c
    if ($r.Blend) { $b = Add-Ctl $gS (New-Object Windows.Forms.CheckBox) 470 $y 70 24; $b.Text = '.blend'; $tip.SetToolTip($b, 'Also save what this step made as a .blend (Blender from the folders above), in <data>\work\blend\'); $BlendChk[$r.Key] = $b }
    $st = Add-Ctl $gS (New-Label '') 550 $y 345 24; $State[$r.Key] = $st
    $y += 30
}
$cR = Add-Ctl $gS (New-Object Windows.Forms.ComboBox) 270 (22 + 2 * 30) 120 23; $cR.DropDownStyle = 'DropDownList'; foreach ($v in 'R1', 'R2', 'R4') { [void]$cR.Items.Add($v) }; $cR.SelectedIndex = 2
$tTitle = Add-Ctl $gS (New-Object Windows.Forms.TextBox) 270 (22 + 6 * 30) 190 23; $tip.SetToolTip($tTitle, 'The name the game''s Classic list shows. The same name replaces its earlier copy.')
$Chk.light.Add_CheckedChanged({ if (-not $Chk.light.Checked) { $Chk.rt.Checked = $false }; $Chk.rt.Enabled = $Chk.light.Checked })
$Chk.round.Add_CheckedChanged({ $cR.Enabled = $Chk.round.Checked })
$Chk.install.Add_CheckedChanged({ $tTitle.Enabled = $Chk.install.Checked }); $tTitle.Enabled = $false

# HD textures + audio
$gH = Add-Ctl $F (New-Object Windows.Forms.GroupBox) 10 522 450 84; $gH.Text = 'HD textures (optional)'
$lH = Add-Ctl $gH (New-Label '') 10 20 430 22
$bHo = Add-Ctl $gH (New-Object Windows.Forms.Button) 10 48 130 27; $bHo.Text = 'Open the folder'
$bHv = Add-Ctl $gH (New-Object Windows.Forms.Button) 146 48 200 27; $bHv.Text = 'Fill it with the vanilla tiles'
$tip.SetToolTip($bHv, 'Copies the 1995 tiles into textures_hd to upscale or repaint. A tile that is left as it is builds exactly as before; files already there are kept.')
$gA = Add-Ctl $F (New-Object Windows.Forms.GroupBox) 466 522 449 84; $gA.Text = 'The 1995 audio (optional, for SR3 Extras)'
$bAc = Add-Ctl $gA (New-Object Windows.Forms.Button) 10 22 210 27; $bAc.Text = 'Co-driver clips from the ROM'
$bAm = Add-Ctl $gA (New-Object Windows.Forms.Button) 226 22 210 27; $bAm.Text = 'Record the music (MAME)'
$tip.SetToolTip($bAc, 'tools\audio\src_audio.py codriver: the co-driver''s calls, cut from your srallyc.zip, into the codriver\src folder SR3 Extras offers.')
$tip.SetToolTip($bAm, 'tools\audio\src_music.py all: the tunes recorded from the emulated sound board (MAME, no window, no sound), into music\src.')
$lA = Add-Ctl $gA (New-Label 'Then pick "SEGA Rally Championship (1995)" in SR3 Extras.') 10 54 430 22

# run
$bRun = Add-Ctl $F (New-Object Windows.Forms.Button) 10 614 120 32; $bRun.Text = 'Run'; $bRun.Font = New-Object Drawing.Font('Segoe UI', 10, [Drawing.FontStyle]::Bold)
$bStop = Add-Ctl $F (New-Object Windows.Forms.Button) 136 614 90 32; $bStop.Text = 'Stop'; $bStop.Enabled = $false
$lRun = Add-Ctl $F (New-Label '') 236 614 300 32
$lTools = Add-Ctl $F (New-Label '') 540 614 230 32
$bTools = Add-Ctl $F (New-Object Windows.Forms.Button) 775 614 140 32; $bTools.Text = 'Python and gcc...'
$tip.SetToolTip($bTools, 'SR3Lab''s own Python and C compiler come in the toolchain zip (no internet needed), or winget can fetch them.')
$Log = Add-Ctl $F (New-Object Windows.Forms.TextBox) 10 652 905 120; $Log.Multiline = $true; $Log.ScrollBars = 'Vertical'; $Log.ReadOnly = $true; $Log.Font = New-Object Drawing.Font('Consolas', 8.5)
$Log.Anchor = 'Top, Bottom, Left, Right'

function Add-Log([string]$s) { $Log.AppendText($s + "`r`n") }
function Current { if ($cC.SelectedIndex -ge 0) { return $Courses[$cC.SelectedIndex] } return $null }
function Hd-Dir { $c = Current; if (-not $c) { return '' }; $d = $Boxes.data_root.Text.Trim(); if (-not $d) { $d = Join-Path $Repo 'data' }; return (Join-Path $d "classic\courses\$($c.Game)\$($c.Gameplay)\textures_hd") }
function Update-Course {
    $c = Current; if (-not $c) { return }
    $lC.Text = "$($c.Patches) patch files; build name stack_$($c.Game)_$($c.Course)"
    $Chk.patch.Text = "2. Patch chain ($($c.Patches) files)"
    if (-not $tTitle.Text) { $tTitle.Text = "$($c.Name.Substring(0,1).ToUpper())$($c.Name.Substring(1)) (stack)" }
    $h = Hd-Dir; $n = @(Get-ChildItem -LiteralPath $h -Filter '*.png' -ErrorAction SilentlyContinue).Count
    $lH.Text = $(if (Test-Path -LiteralPath $h) { "$n tiles in textures_hd ($($c.Gameplay))" } else { 'textures_hd is made by step 1' })
}
$cC.Add_SelectedIndexChanged({ Update-Course })

# ---- running a Python tool, its output into the log (read on .NET's own threads: PowerShell events do not run inside ShowDialog) ----
Add-Type -TypeDefinition @'
public class StackPump {
    public System.Diagnostics.Process P;
    public System.Collections.Concurrent.ConcurrentQueue<string> Q = new System.Collections.Concurrent.ConcurrentQueue<string>();
    public StackPump(System.Diagnostics.ProcessStartInfo i) {
        P = new System.Diagnostics.Process(); P.StartInfo = i;
        P.OutputDataReceived += (s, e) => { if (e.Data != null) Q.Enqueue(e.Data); };
        P.ErrorDataReceived += (s, e) => { if (e.Data != null) Q.Enqueue(e.Data); };
        P.Start(); P.BeginOutputReadLine(); P.BeginErrorReadLine();
    }
}
'@
$Q = New-Object 'System.Collections.Concurrent.ConcurrentQueue[string]'; $script:Proc = $null; $script:T0 = $null; $script:OnDone = $null
function Start-Tool([string]$exe, [string[]]$argv, [string]$cwd, $onDone) {
    if ($script:Proc -and -not $script:Proc.HasExited) { return }
    $i = New-Object Diagnostics.ProcessStartInfo; $i.FileName = $exe; $i.WorkingDirectory = $cwd
    $i.Arguments = ($argv | ForEach-Object { if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ } }) -join ' '
    $i.UseShellExecute = $false; $i.RedirectStandardOutput = $true; $i.RedirectStandardError = $true; $i.CreateNoWindow = $true
    $pump = New-Object StackPump($i); $script:Q = $pump.Q; $script:Proc = $pump.P; $script:T0 = Get-Date; $script:OnDone = $onDone; $bRun.Enabled = $false; $bStop.Enabled = $true
    Add-Log ("> $(Split-Path -Leaf $exe) " + $i.Arguments)
}
function Update-Tools {
    $g = Find-Gcc; $script:Py = Find-Py
    $lTools.Text = "Python: $(if ($script:Py) { 'ok' } else { 'none' }); gcc: $(if ($g) { 'ok' } else { 'none' })"
    $lTools.ForeColor = $(if ($script:Py -and $g) { [Drawing.Color]::DarkGreen } else { [Drawing.Color]::DarkRed })
    $tip.SetToolTip($lTools, "Python: $($script:Py)`ngcc: $g")
}
function Start-Py([string[]]$argv, [string]$cwd, $onDone) {
    if (-not $Py) { [Windows.Forms.MessageBox]::Show('No Python yet: click "Python and gcc..." to unpack the toolchain zip (no internet needed) or fetch them with winget.') | Out-Null; return }
    if ($script:Proc -and -not $script:Proc.HasExited) { return }
    Save-Folders
    $i = New-Object Diagnostics.ProcessStartInfo; $i.FileName = $Py; $i.WorkingDirectory = $cwd
    $i.Arguments = (@('-u') + $argv | ForEach-Object { if ($_ -match '[\s"]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ } }) -join ' '
    $i.UseShellExecute = $false; $i.RedirectStandardOutput = $true; $i.RedirectStandardError = $true; $i.CreateNoWindow = $true
    $i.EnvironmentVariables['PYTHONIOENCODING'] = 'utf-8'; $i.StandardOutputEncoding = [Text.Encoding]::UTF8; $i.StandardErrorEncoding = [Text.Encoding]::UTF8
    $pump = New-Object StackPump($i); $script:Q = $pump.Q; $p = $pump.P
    $script:Proc = $p; $script:T0 = Get-Date; $script:OnDone = $onDone; $bRun.Enabled = $false; $bStop.Enabled = $true
    Add-Log ("> python " + $i.Arguments)
}
$Timer = New-Object Windows.Forms.Timer; $Timer.Interval = 250
$Timer.Add_Tick({
    $s = $null
    while ($script:Q.TryDequeue([ref]$s)) {
        if ($s -match '^@@ step (\S+) (start|done|fail)\s*(.*)$') {
            $keys = switch ($Matches[1]) { 'rom' { @('rom') } 'patch/round/light' { @('patch', 'round', 'light') } 'rt' { @('rt') } 'build' { @('build') } 'install' { @('install') } default { @() } }
            foreach ($k in $keys) { if (-not $Chk[$k].Checked -and $k -ne 'patch' -and $k -ne 'round') { continue }
                $State[$k].Text = switch ($Matches[2]) { 'start' { 'running...' } 'done' { "done ($($Matches[3]) s)" } 'fail' { "FAILED: $($Matches[3])" } }
                $State[$k].ForeColor = switch ($Matches[2]) { 'start' { [Drawing.Color]::DarkBlue } 'done' { [Drawing.Color]::DarkGreen } 'fail' { [Drawing.Color]::DarkRed } } }
        } elseif ($s -match '^@@ blend (\S+) (.*)$') { Add-Log ".blend of $($Matches[1]): $($Matches[2])" }
        elseif ($s -match '^@@ done (\S+)') { Add-Log "all done in $($Matches[1]) s" }
        else { Add-Log $s }
    }
    if ($script:Proc) {
        $lRun.Text = 'running for {0:mm\:ss}' -f ((Get-Date) - $script:T0)
        if ($script:Proc.HasExited) {
            $code = $script:Proc.ExitCode; $script:Proc = $null; $bRun.Enabled = $true; $bStop.Enabled = $false
            $lRun.Text = $(if ($code -eq 0) { 'finished' } else { "stopped (exit $code)" })
            if ($script:OnDone) { & $script:OnDone $code }; Update-Course
        }
    }
})
$Timer.Start()

$bRun.Add_Click({
    $c = Current; if (-not $c) { return }
    $steps = @($StepRows | Where-Object { $Chk[$_.Key].Checked } | ForEach-Object { $_.Key })
    if (-not $steps.Count) { return }
    if ($Chk.install.Checked -and (Get-Process -Name Rally -ErrorAction SilentlyContinue)) { [Windows.Forms.MessageBox]::Show('SEGA Rally 3 is running: close it before installing.') | Out-Null; return }
    $blend = @($BlendChk.Keys | Where-Object { $BlendChk[$_].Checked -and $Chk[$_].Checked })
    foreach ($k in $State.Keys) { $State[$k].Text = $(if ($steps -contains $k) { 'waiting' } else { '' }); $State[$k].ForeColor = [Drawing.Color]::Gray }
    $a = @((Join-Path $Here 'stack.py'), $c.Game, $c.Course, '--steps', ($steps -join ','), '--round', $cR.Text.Substring(1))
    if ($blend.Count) { $a += @('--blend', ($blend -join ',')) }
    if ($Chk.install.Checked) { $a += @('--title', $tTitle.Text) }
    Start-Py $a $Here $null
})
$bStop.Add_Click({ if ($script:Proc -and -not $script:Proc.HasExited) { & taskkill.exe /T /F /PID $script:Proc.Id | Out-Null; Add-Log 'stopped by you' } })
$bHo.Add_Click({ $h = Hd-Dir; if (Test-Path -LiteralPath $h) { Start-Process explorer.exe $h } else { [Windows.Forms.MessageBox]::Show('Run step 1 first: it makes the folder.') | Out-Null } })
$bHv.Add_Click({ $c = Current; if ($c) { Start-Py @((Join-Path $Here 'core\hd_textures.py'), $c.Game, $c.Course, 'vanilla') (Join-Path $Here 'core') $null } })
$bAc.Add_Click({ Start-Py @((Join-Path $Repo 'tools\audio\src_audio.py'), 'codriver') (Join-Path $Repo 'tools\audio') $null })
$bAm.Add_Click({ if (-not $Boxes.mame.Text.Trim()) { [Windows.Forms.MessageBox]::Show('Set MAME in the folders first.') | Out-Null; return }; Start-Py @((Join-Path $Repo 'tools\audio\src_music.py'), 'all') (Join-Path $Repo 'tools\audio') $null })
$bTools.Add_Click({
    $m = "SR3Lab's own Python and C compiler are in the toolchain zip that comes with it.`n`nYes: unpack them from the zip (recommended - nothing is downloaded or installed in Windows).`nNo: fetch them with winget instead (python.org's Python, WinLibs' gcc, numpy and Pillow from PyPI); the zip is not needed then.`nCancel: leave things as they are."
    $a = [Windows.Forms.MessageBox]::Show($m, 'Python and gcc', 'YesNoCancel', 'Question')
    if ($a -eq 'Cancel') { return }
    $ps = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
    $argv = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $Repo 'tools\setup_toolchain.ps1')) + $(if ($a -eq 'No') { @('-Winget') } else { @() })
    Start-Tool $ps $argv $Repo { param($code) $script:S = Read-Settings; Update-Tools }
})
$F.Add_FormClosing({ if ($script:Proc -and -not $script:Proc.HasExited) { & taskkill.exe /T /F /PID $script:Proc.Id | Out-Null } })

Update-Marks; Update-Tools; if ($cC.Items.Count) { $cC.SelectedIndex = 0 }
if (-not $Py) { Add-Log 'No Python yet: "Python and gcc..." sets it up from the toolchain zip, or with winget.' } else { Add-Log "Python: $Py"; Add-Log "gcc: $(Find-Gcc)" }
if ($env:SR3_WINDOW_SHOT) {                                           # (tests) the window drawn into a picture, never shown
    $F.Opacity = 0; $F.ShowInTaskbar = $false; $F.Show(); [Windows.Forms.Application]::DoEvents()
    $bmp = New-Object Drawing.Bitmap($F.Width, $F.Height); $F.DrawToBitmap($bmp, (New-Object Drawing.Rectangle(0, 0, $F.Width, $F.Height))); $bmp.Save($env:SR3_WINDOW_SHOT); $F.Close(); return
}
[void]$F.ShowDialog()

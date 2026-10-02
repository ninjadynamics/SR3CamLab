<#
  SR3CamLab setup: finds TeknoParrot, its SEGA Rally 3 game profile and Rally.exe, checks them,
  and remembers them in setup.yaml (next to this script, one per PC). patch.ps1 dot-sources it.
  PLAY.bat finds everything by itself when it can; the setup window opens when something is
  missing or wrong, and with "PLAY.bat -Setup".
#>

$SetupFile    = Join-Path $PSScriptRoot 'setup.yaml'
$SupportedMd5 = 'd7c0b475fe593a43e0a37b603a324454'                 # Rally.exe v3.8.4.1
$GameDlls     = @('d3dx9_41.dll', 'granny2.dll', 'fmodex.dll')     # shipped with the game, next to Rally.exe

# ---- setup.yaml ----
function Read-Setup {
    $s = @{ teknoparrot = ''; profile = ''; game = '' }
    if (Test-Path -LiteralPath $SetupFile) {
        foreach ($line in [IO.File]::ReadAllLines($SetupFile)) {
            if ($line.TrimStart().StartsWith('#') -or $line -notmatch '^\s*(\w+)\s*:\s*(.*?)\s*$') { continue }
            $k = $Matches[1].ToLower(); $v = $Matches[2]
            if ($v.Length -ge 2 -and $v[0] -eq "'" -and $v[-1] -eq "'") { $v = $v.Substring(1, $v.Length - 2).Replace("''", "'") }
            $s[$k] = $v
        }
    }
    return $s
}
function Write-Setup($s) {
    $q = { param($v) "'" + ("$v" -replace "'", "''") + "'" }
    $text = "# SR3CamLab setup: where TeknoParrot and SEGA Rally 3 are on this PC.`n" +
            "# Written by PLAY.bat. Run ""PLAY.bat -Setup"" to change it, or delete this file to start over.`n`n" +
            "teknoparrot: $(& $q $s.teknoparrot)`nprofile: $(& $q $s.profile)`ngame: $(& $q $s.game)`n"
    [IO.File]::WriteAllText($SetupFile, $text)
}

# ---- what is where ----
function Test-FilePath([string]$path) { return [bool]($path -and (Test-Path -LiteralPath $path -PathType Leaf)) }

# TeknoParrot's game profiles (UserProfiles\*.xml) whose game is Rally.exe: name, game path
function Get-TpProfiles([string]$tpExe) {
    $list = New-Object System.Collections.ArrayList
    if (-not $tpExe -or -not (Test-Path -LiteralPath $tpExe -PathType Leaf)) { return ,$list }
    $dir = Split-Path -Parent $tpExe
    $up = Join-Path $dir 'UserProfiles'
    if (-not (Test-Path -LiteralPath $up)) { return ,$list }
    foreach ($f in Get-ChildItem -LiteralPath $up -Filter '*.xml') {
        try { $x = [xml]([IO.File]::ReadAllText($f.FullName)) } catch { continue }
        $gp = "$($x.GameProfile.GamePath)".Trim()
        if (-not $gp -or [IO.Path]::GetFileName($gp) -ine 'Rally.exe') { continue }
        if (-not [IO.Path]::IsPathRooted($gp)) { $gp = Join-Path $dir $gp }
        try { $gp = [IO.Path]::GetFullPath($gp) } catch { }
        [void]$list.Add([pscustomobject]@{ Name = $f.BaseName; Game = $gp })
    }
    return ,$list
}

$script:Md5Cache = @{}
function Get-FileMd5([string]$path) {
    $fi = Get-Item -LiteralPath $path
    $key = "$($fi.FullName)|$($fi.Length)|$($fi.LastWriteTimeUtc.Ticks)"
    if (-not $script:Md5Cache.ContainsKey($key)) {
        $md5 = [Security.Cryptography.MD5]::Create()
        try { $script:Md5Cache[$key] = -join ($md5.ComputeHash([IO.File]::ReadAllBytes($fi.FullName)) | ForEach-Object { $_.ToString('x2') }) }
        finally { $md5.Dispose() }
    }
    return $script:Md5Cache[$key]
}

# Checks a setup: a list of (Level = ok / warn / error, Text). It can run if there is no error.
function Test-Setup($s) {
    $r = New-Object System.Collections.ArrayList
    $add = { param($level, $text) [void]$r.Add([pscustomobject]@{ Level = $level; Text = $text }) }
    $tpOk = $s.teknoparrot -and (Test-Path -LiteralPath $s.teknoparrot -PathType Leaf) -and ([IO.Path]::GetFileName($s.teknoparrot) -ieq 'TeknoParrotUi.exe')
    if ($tpOk) { & $add ok 'TeknoParrot found.' }
    else { & $add error 'TeknoParrotUi.exe not found: browse to it (it is in your TeknoParrot folder).' }

    $prof = $null
    if ($tpOk) {
        $profiles = Get-TpProfiles $s.teknoparrot
        $prof = $profiles | Where-Object { $_.Name -ieq $s.profile } | Select-Object -First 1
        if ($prof) { & $add ok "TeknoParrot's game profile '$($prof.Name)' starts Rally.exe." }
        elseif ($profiles.Count -eq 0) { & $add error 'TeknoParrot has no SEGA Rally 3 game yet. Add it in TeknoParrot (Add Game, then set its game path to Rally.exe), check that it runs, then come back here.' }
        else { & $add error 'Choose the TeknoParrot game profile for SEGA Rally 3.' }
    }

    $gameOk = $s.game -and (Test-Path -LiteralPath $s.game -PathType Leaf) -and ([IO.Path]::GetFileName($s.game) -ieq 'Rally.exe')
    if (-not $gameOk) { & $add error 'Rally.exe not found: browse to it (in the game folder, e.g. ...\Sega Rally 3\Rally\Rally.exe).' }
    else {
        if ($prof -and ([IO.Path]::GetFullPath($s.game) -ine $prof.Game)) {
            & $add warn "TeknoParrot's profile starts a different copy: $($prof.Game). That is the one that will run."
        }
        if ((Get-FileMd5 $s.game) -eq $SupportedMd5) { & $add ok 'Rally.exe is version 3.8.4.1, the one this mod supports.' }
        else { & $add error 'This Rally.exe is not version 3.8.4.1 (its checksum differs), so the camera patch would refuse to touch it.' }
        $dir = Split-Path -Parent $s.game
        $missing = @($GameDlls | Where-Object { -not (Test-Path -LiteralPath (Join-Path $dir $_)) })
        if ($missing.Count) { & $add error ("The game folder is incomplete, missing: " + ($missing -join ', ') + '.') }
        else { & $add ok 'The game folder has its files.' }
    }

    $wmv = Join-Path $env:WINDIR 'SysWOW64\wmvdecod.dll'
    if (-not (Test-Path -LiteralPath $wmv)) { $wmv = Join-Path $env:WINDIR 'System32\wmvdecod.dll' }
    if (Test-Path -LiteralPath $wmv) { & $add ok "Windows' video decoder is installed." }
    else { & $add warn "Windows' video decoder (wmvdecod.dll) is missing, so the game's videos won't play. On Windows 'N' editions, install the Media Feature Pack." }
    return ,$r
}
function Test-SetupOk($checks) { return -not ($checks | Where-Object { $_.Level -eq 'error' }) }

# Best guess: what setup.yaml says, else a running TeknoParrot or the game, else the folders above this one.
function Find-Setup {
    $s = Read-Setup
    $tps = New-Object System.Collections.ArrayList
    if ($s.teknoparrot) { [void]$tps.Add($s.teknoparrot) }
    foreach ($p in @(Get-Process -Name TeknoParrotUi -ErrorAction SilentlyContinue)) { try { if ($p.Path) { [void]$tps.Add($p.Path) } } catch { } }
    $d = $PSScriptRoot
    for ($i = 0; $i -lt 4; $i++) {
        $d = Split-Path -Parent $d
        if (-not $d) { break }
        [void]$tps.Add((Join-Path $d 'TeknoParrotUi.exe'))
    }
    $tp = $tps | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if ($tp) { $s.teknoparrot = [IO.Path]::GetFullPath($tp) }

    $profiles = Get-TpProfiles $s.teknoparrot
    $prof = $profiles | Where-Object { $_.Name -ieq $s.profile } | Select-Object -First 1
    if (-not $prof) { $prof = $profiles | Where-Object { $_.Name -ieq 'SR3' } | Select-Object -First 1 }
    if (-not $prof) { $prof = $profiles | Where-Object { Test-Path -LiteralPath $_.Game } | Select-Object -First 1 }
    if ($prof) {
        $s.profile = $prof.Name
        if (-not (Test-FilePath $s.game)) { $s.game = $prof.Game }
    }
    if (-not (Test-FilePath $s.game)) {
        $r = Get-Process -Name Rally -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($r) { try { if ($r.Path) { $s.game = $r.Path } } catch { } }
    }
    return $s
}

# ---- the setup window ----
function Show-SetupWindow($s) {
    Add-Type -AssemblyName System.Windows.Forms, System.Drawing
    try { Add-Type -Namespace SR3CamLab -Name Dpi -MemberDefinition '[DllImport("user32.dll")] public static extern bool SetProcessDPIAware();' -ErrorAction Stop } catch { }
    try { [void][SR3CamLab.Dpi]::SetProcessDPIAware() } catch { }
    [Windows.Forms.Application]::EnableVisualStyles()

    $ui = @{ S = @{ teknoparrot = $s.teknoparrot; profile = $s.profile; game = $s.game }; Busy = $false }
    $script:SetupUi = $ui
    $form = New-Object Windows.Forms.Form
    $form.Text = 'SR3CamLab setup'
    $form.Font = New-Object Drawing.Font('Segoe UI', 9)
    $form.AutoScaleMode = [Windows.Forms.AutoScaleMode]::Dpi
    $form.FormBorderStyle = 'FixedDialog'; $form.MaximizeBox = $false; $form.MinimizeBox = $false
    $form.StartPosition = 'CenterScreen'; $form.TopMost = $true
    $form.AutoSize = $true; $form.AutoSizeMode = 'GrowAndShrink'; $form.Padding = New-Object Windows.Forms.Padding(14)

    $grid = New-Object Windows.Forms.TableLayoutPanel
    $grid.ColumnCount = 3; $grid.AutoSize = $true; $grid.AutoSizeMode = 'GrowAndShrink'
    [void]$grid.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::AutoSize)))
    [void]$grid.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::AutoSize)))
    [void]$grid.ColumnStyles.Add((New-Object Windows.Forms.ColumnStyle([Windows.Forms.SizeType]::AutoSize)))
    $form.Controls.Add($grid)
    $wide = 640
    $label = { param($text, [int]$top = 0) $l = New-Object Windows.Forms.Label; $l.Text = $text; $l.AutoSize = $true
               $l.Margin = New-Object Windows.Forms.Padding(0, (6 + $top), 10, 4); $l }

    $intro = & $label ("Tell SR3CamLab where TeknoParrot and SEGA Rally 3 are on this PC. It remembers them in setup.yaml, " +
                       "next to PLAY.bat; run ""PLAY.bat -Setup"" to come back here.")
    $intro.MaximumSize = New-Object Drawing.Size($wide, 0); $intro.Margin = New-Object Windows.Forms.Padding(0, 0, 0, 12)
    $grid.Controls.Add($intro, 0, 0); $grid.SetColumnSpan($intro, 3)

    $grid.Controls.Add((& $label 'TeknoParrot'), 0, 1)
    $tpBox = New-Object Windows.Forms.TextBox; $tpBox.Width = 460; $tpBox.Text = $ui.S.teknoparrot
    $grid.Controls.Add($tpBox, 1, 1)
    $tpBrowse = New-Object Windows.Forms.Button; $tpBrowse.Text = 'Browse...'; $tpBrowse.AutoSize = $true
    $grid.Controls.Add($tpBrowse, 2, 1)

    $grid.Controls.Add((& $label 'Game profile'), 0, 2)
    $profBox = New-Object Windows.Forms.ComboBox; $profBox.DropDownStyle = 'DropDownList'; $profBox.Width = 220
    $grid.Controls.Add($profBox, 1, 2)

    $grid.Controls.Add((& $label 'Rally.exe'), 0, 3)
    $gameBox = New-Object Windows.Forms.TextBox; $gameBox.Width = 460; $gameBox.Text = $ui.S.game
    $grid.Controls.Add($gameBox, 1, 3)
    $gameBrowse = New-Object Windows.Forms.Button; $gameBrowse.Text = 'Browse...'; $gameBrowse.AutoSize = $true
    $grid.Controls.Add($gameBrowse, 2, 3)

    $checks = New-Object Windows.Forms.FlowLayoutPanel
    $checks.FlowDirection = 'TopDown'; $checks.WrapContents = $false; $checks.AutoSize = $true
    $checks.Margin = New-Object Windows.Forms.Padding(0, 14, 0, 8)
    $grid.Controls.Add($checks, 0, 4); $grid.SetColumnSpan($checks, 3)

    $buttons = New-Object Windows.Forms.FlowLayoutPanel
    $buttons.FlowDirection = 'RightToLeft'; $buttons.AutoSize = $true; $buttons.Dock = 'Fill'
    $cancel = New-Object Windows.Forms.Button; $cancel.Text = 'Cancel'; $cancel.AutoSize = $true; $cancel.DialogResult = 'Cancel'
    $save = New-Object Windows.Forms.Button; $save.Text = 'Save'; $save.AutoSize = $true; $save.DialogResult = 'OK'
    $buttons.Controls.Add($cancel); $buttons.Controls.Add($save)
    $grid.Controls.Add($buttons, 0, 5); $grid.SetColumnSpan($buttons, 3)
    $form.AcceptButton = $save; $form.CancelButton = $cancel

    $ui.Form = $form; $ui.Tp = $tpBox; $ui.Prof = $profBox; $ui.Game = $gameBox; $ui.Checks = $checks; $ui.Save = $save; $ui.Wide = $wide

    # re-check and redraw the list
    $ui.Refresh = {
        $u = $script:SetupUi
        $u.S.teknoparrot = $u.Tp.Text.Trim().Trim('"'); $u.S.game = $u.Game.Text.Trim().Trim('"')
        $u.S.profile = if ($u.Prof.SelectedItem) { "$($u.Prof.SelectedItem)" } else { '' }
        $results = Test-Setup $u.S
        $u.Checks.SuspendLayout(); $u.Checks.Controls.Clear()
        foreach ($c in $results) {
            $l = New-Object Windows.Forms.Label; $l.AutoSize = $true; $l.MaximumSize = New-Object Drawing.Size($u.Wide, 0)
            $l.Margin = New-Object Windows.Forms.Padding(0, 2, 0, 2)
            switch ($c.Level) {
                'ok'    { $l.Text = [string][char]0x2714 + '  ' + $c.Text; $l.ForeColor = [Drawing.Color]::FromArgb(30, 130, 60) }
                'warn'  { $l.Text = [string][char]0x26A0 + '  ' + $c.Text; $l.ForeColor = [Drawing.Color]::FromArgb(176, 112, 0) }
                default { $l.Text = [string][char]0x2716 + '  ' + $c.Text; $l.ForeColor = [Drawing.Color]::FromArgb(190, 30, 30) }
            }
            $u.Checks.Controls.Add($l)
        }
        $u.Checks.ResumeLayout()
        $u.Save.Enabled = Test-SetupOk $results
    }
    # TeknoParrot changed: list its SEGA Rally 3 profiles
    $ui.FillProfiles = {
        $u = $script:SetupUi
        $u.Busy = $true
        $profiles = Get-TpProfiles ($u.Tp.Text.Trim().Trim('"'))
        $u.Profiles = $profiles
        $u.Prof.Items.Clear()
        foreach ($p in $profiles) { [void]$u.Prof.Items.Add($p.Name) }
        $pick = $profiles | Where-Object { $_.Name -ieq $u.S.profile } | Select-Object -First 1
        if (-not $pick) { $pick = $profiles | Select-Object -First 1 }
        if ($pick) { $u.Prof.SelectedItem = $pick.Name }
        if ($pick -and -not (Test-FilePath $u.Game.Text.Trim().Trim('"'))) { $u.Game.Text = $pick.Game }
        $u.Busy = $false
    }
    $tpBox.Add_TextChanged({ $u = $script:SetupUi; & $u.FillProfiles; & $u.Refresh })
    $profBox.Add_SelectedIndexChanged({
        $u = $script:SetupUi
        if ($u.Busy) { return }
        $p = $u.Profiles | Where-Object { $_.Name -eq "$($u.Prof.SelectedItem)" } | Select-Object -First 1
        if ($p) { $u.Game.Text = $p.Game }
        & $u.Refresh
    })
    $gameBox.Add_TextChanged({ $u = $script:SetupUi; if (-not $u.Busy) { & $u.Refresh } })
    $tpBrowse.Add_Click({
        $u = $script:SetupUi
        $d = New-Object Windows.Forms.OpenFileDialog; $d.Title = 'Find TeknoParrotUi.exe'; $d.Filter = 'TeknoParrot|TeknoParrotUi.exe|Programs (*.exe)|*.exe'
        if (Test-FilePath $u.Tp.Text) { $d.InitialDirectory = Split-Path -Parent $u.Tp.Text }
        if ($d.ShowDialog($u.Form) -eq 'OK') { $u.Tp.Text = $d.FileName }
    })
    $gameBrowse.Add_Click({
        $u = $script:SetupUi
        $d = New-Object Windows.Forms.OpenFileDialog; $d.Title = 'Find Rally.exe'; $d.Filter = 'SEGA Rally 3|Rally.exe|Programs (*.exe)|*.exe'
        if (Test-FilePath $u.Game.Text) { $d.InitialDirectory = Split-Path -Parent $u.Game.Text }
        if ($d.ShowDialog($u.Form) -eq 'OK') { $u.Game.Text = $d.FileName }
    })

    & $ui.FillProfiles
    & $ui.Refresh
    $result = $form.ShowDialog()
    $form.Dispose()
    if ($result -ne 'OK') { return $null }
    return $ui.S
}

# What patch.ps1 calls before starting the game: the saved / detected setup when it checks out,
# else the setup window. Returns $null when the window was cancelled.
function Get-GameSetup([switch]$Force) {
    $s = Find-Setup
    $checks = Test-Setup $s
    if ((Test-SetupOk $checks) -and -not $Force) {
        $saved = Read-Setup
        if ($saved.teknoparrot -ne $s.teknoparrot -or $saved.profile -ne $s.profile -or $saved.game -ne $s.game) { Write-Setup $s }
        foreach ($c in $checks | Where-Object { $_.Level -eq 'warn' }) { Write-Host "  Note: $($c.Text)" }
        return $s
    }
    $s = Show-SetupWindow $s
    if ($s) { Write-Setup $s }
    return $s
}

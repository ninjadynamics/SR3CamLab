# Livery switching for the Daytona USA Hornet in SEGA Rally 3 (Windows PowerShell 5.1; dot-source this file).
#
#   . "<SR3CamLab>\scripts\importer\hornet_livery.ps1"
#   Get-HornetLiveries [-Store <folder>] [-Game <Rally folder>]     every livery of hornet_liveries.json: Key, Title, Kind,
#                                                                   Raced, Built (its set is in the store), Installed, Path
#   Get-HornetLivery   [-Store] [-Game]                             the key of the livery in the game ($null: the Hornet's
#                                                                   files are not one of the built sets)
#   Set-HornetLivery <Key> [-Store] [-Game] [-Force] [-WhatIf]      puts that livery's files in the game
#
# A livery set is a staging folder built by daytona_car.py (<store>\<key>\manifest.json + the files it lists). Every set is
# the same car ('Hornet', same record in the ArcadeDatabase and the same name in system_data.sbf), so switching only
# swaps the Hornet's own files (Main_release\cars\hornet*.sbf, Main_release\cars\bonnets\hornet_data.sbf); SEGA's files
# are never written. The first install of the car is the set's own install.ps1 (it also adds the record and the name).
# Set-HornetLivery:
#   - refuses while the game runs (-Proc names another process, for tests);
#   - refuses when the Hornet is not installed (the game's ArcadeDatabase / system_data.sbf are not the ones the set was
#     built for) - run <store>\<key>\install.ps1 first;
#   - refuses when one of the Hornet's files in the game is not from any built set (an older test build, a file changed by
#     hand): -Force replaces them anyway, keeping each first as <file>.before_livery;
#   - copies every changed file next to its target first and checks it, then swaps them in; files already right are left
#     alone, so a second call does nothing and a call after an interrupted one finishes the switch.
# The store: -Store, else $HornetLiveryStore, else the environment variable SR3_HORNET_LIVERIES.

$HornetLiveryTable = Join-Path $PSScriptRoot "hornet_liveries.json"
if (-not (Get-Variable -Name HornetLiveryStore -ErrorAction SilentlyContinue)) { $HornetLiveryStore = $env:SR3_HORNET_LIVERIES }
$HornetLiveryGame = "F:\Jogos\SEGA Rally 3\GAME\Sega Rally 3\Rally"

function Get-HornetLiverySha([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Resolve-HornetLiveryStore([string]$Store) {
    if (-not $Store) { $Store = $HornetLiveryStore }
    if (-not $Store) { throw "no livery store: pass -Store, or set `$HornetLiveryStore or SR3_HORNET_LIVERIES" }
    if (-not (Test-Path -LiteralPath $Store -PathType Container)) { throw "livery store not found: $Store" }
    $Store
}

function Get-HornetLiveryTable {
    $t = Get-Content -LiteralPath $HornetLiveryTable -Raw -Encoding UTF8 | ConvertFrom-Json
    @($t.liveries)
}

function Read-HornetLiveryManifest([string]$Store, [string]$Key) {
    $p = Join-Path (Join-Path $Store $Key) "manifest.json"
    if (-not (Test-Path -LiteralPath $p -PathType Leaf)) { return $null }
    $m = Get-Content -LiteralPath $p -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($f in $m.files) {          # only the Hornet's own files, never one of SEGA's
        if ($f.path -notmatch '^Main_release\\cars\\(bonnets\\)?hornet[a-z_]*\.sbf$') { throw "$p lists a file that is not the Hornet's: $($f.path)" }
    }
    $m
}

function Get-HornetLiveryInstalled([string]$Game, $Manifests) {
    # the game's copy of every file a set lists -> hash (or $null)
    $h = @{}
    foreach ($m in $Manifests) { foreach ($f in $m.files) { if (-not $h.ContainsKey($f.path)) { $h[$f.path] = Get-HornetLiverySha (Join-Path $Game $f.path) } } }
    $h
}

function Get-HornetLivery {
    [CmdletBinding()]
    param([string]$Store, [string]$Game = $HornetLiveryGame)
    $Store = Resolve-HornetLiveryStore $Store
    $sets = @()
    foreach ($l in Get-HornetLiveryTable) { $m = Read-HornetLiveryManifest $Store $l.key; if ($m) { $sets += , @($l.key, $m) } }
    $inst = Get-HornetLiveryInstalled $Game ($sets | ForEach-Object { $_[1] })
    foreach ($s in $sets) {
        $all = $true
        foreach ($f in $s[1].files) { if ($inst[$f.path] -ne $f.sha256) { $all = $false; break } }
        if ($all) { return $s[0] }
    }
    $null
}

function Get-HornetLiveries {
    [CmdletBinding()]
    param([string]$Store, [string]$Game = $HornetLiveryGame)
    $Store = Resolve-HornetLiveryStore $Store
    $cur = Get-HornetLivery -Store $Store -Game $Game
    foreach ($l in Get-HornetLiveryTable) {
        $dir = Join-Path $Store $l.key
        [pscustomobject]@{
            Key = $l.key; Title = $l.title; Kind = $l.kind; Raced = [bool]$l.raced
            Built = (Test-Path -LiteralPath (Join-Path $dir "manifest.json") -PathType Leaf)
            Installed = ($l.key -eq $cur); Path = $dir; Note = $l.note
        }
    }
}

function Set-HornetLivery {
    [CmdletBinding(SupportsShouldProcess = $true)]
    param([Parameter(Mandatory = $true, Position = 0)][string]$Key, [string]$Store, [string]$Game = $HornetLiveryGame,
          [switch]$Force, [string]$Proc = "Rally")
    $ErrorActionPreference = "Stop"
    $Store = Resolve-HornetLiveryStore $Store
    $table = Get-HornetLiveryTable
    $entry = $table | Where-Object { $_.key -eq $Key }
    if (-not $entry) { throw "unknown Hornet livery '$Key' (Get-HornetLiveries lists them)" }
    $m = Read-HornetLiveryManifest $Store $Key
    if (-not $m) { throw "livery '$Key' is not built: no $(Join-Path (Join-Path $Store $Key) 'manifest.json')" }
    if (Get-Process -Name $Proc -ErrorAction SilentlyContinue) { throw "$Proc.exe is running - close the game first" }
    if (-not (Test-Path -LiteralPath (Join-Path $Game "Rally.exe") -PathType Leaf)) { throw "no Rally.exe in $Game" }
    $src = Join-Path $Store $Key

    # the Hornet must be installed: the SEGA files it changes are the ones this set was built for
    foreach ($r in $m.replace) {
        if ((Get-HornetLiverySha (Join-Path $Game $r.path)) -ne $r.sha256) {
            throw "the Hornet is not installed ($($r.path) is not the Hornet's version): run $(Join-Path $src 'install.ps1') first"
        }
    }
    # every Hornet file in the game must come from one of the built sets (else -Force)
    $known = @{}
    $all = @($m)
    foreach ($l in $table) { $o = Read-HornetLiveryManifest $Store $l.key; if ($o) { $all += $o } }
    foreach ($o in $all) { foreach ($f in $o.files) { $known["$($f.path)|$($f.sha256)"] = $true } }
    $inst = Get-HornetLiveryInstalled $Game @($m)
    $foreign = @($m.files | Where-Object { $inst[$_.path] -and -not $known["$($_.path)|$($inst[$_.path])"] })
    if ($foreign.Count -and -not $Force) {
        throw "these Hornet files in the game are not from a built livery set (an older build?): $(($foreign | ForEach-Object { $_.path }) -join ', ') - uninstall that build, or -Force (keeps each as <file>.before_livery)"
    }

    $todo = @($m.files | Where-Object { $inst[$_.path] -ne $_.sha256 })
    if (-not $todo.Count) { Write-Verbose "livery '$Key' is already in the game"; return [pscustomobject]@{ Key = $Key; Changed = 0 } }
    if (-not $PSCmdlet.ShouldProcess($Game, "Hornet livery '$Key' ($($todo.Count) files)")) { return }

    # 1. every changed file copied next to its target and checked
    $tmp = @()
    try {
        foreach ($f in $todo) {
            $s = Join-Path $src $f.path; $d = Join-Path $Game $f.path; $t = "$d.livery_tmp"
            if ((Get-HornetLiverySha $s) -ne $f.sha256) { throw "the staged file changed since it was built: $s" }
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $d) | Out-Null
            Copy-Item -LiteralPath $s -Destination $t -Force; $tmp += $t
            if ((Get-HornetLiverySha $t) -ne $f.sha256) { throw "copy check failed: $t" }
        }
        # 2. swapped in
        foreach ($f in $todo) {
            $d = Join-Path $Game $f.path; $t = "$d.livery_tmp"
            if ($foreign | Where-Object { $_.path -eq $f.path }) {
                $keep = "$d.before_livery"
                if (-not (Test-Path -LiteralPath $keep)) { Copy-Item -LiteralPath $d -Destination $keep; Write-Verbose "kept $keep" }
            }
            if (Test-Path -LiteralPath $d -PathType Leaf) { [System.IO.File]::Replace($t, $d, [NullString]::Value) }
            else { [System.IO.File]::Move($t, $d) }
            if ((Get-HornetLiverySha $d) -ne $f.sha256) { throw "swap check failed: $d" }
            Write-Verbose "swapped $($f.path)"
        }
    }
    finally {
        foreach ($t in $tmp) { if (Test-Path -LiteralPath $t) { Remove-Item -LiteralPath $t -Force } }
    }
    [pscustomobject]@{ Key = $Key; Changed = $todo.Count }
}

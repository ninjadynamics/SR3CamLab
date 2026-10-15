# Installs a car staging folder (car_clone.py / daytona_car.py) into the game; copied into the staging folder as install.ps1.
#   powershell -ExecutionPolicy Bypass -File "<staging>\install.ps1" [-Game "<...\Rally>"] [-Force]
# - refuses while Rally.exe runs (-Force overrides; -Proc names another process, for tests);
# - SEGA files the car changes (manifest "replace": ArcadeDatabase, system\system_data.sbf; old manifests: "db"):
#   only replaced when the game's file is exactly the one the staging was built from (SHA-256), checked for ALL of them
#   before anything is copied; each is kept first as Main_release\tracks\_SR3Extras\original\<backup> (never over an
#   existing backup, never over the files already in that folder);
# - car files (manifest "files"): copied in; a file already there with other content is first kept as <file>.before_install.
param([string]$Game = (& python (Join-Path $PSScriptRoot 'common.py') --paths game), [switch]$Force, [string]$Proc = "Rally")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$m = Get-Content -LiteralPath (Join-Path $here "manifest.json") -Raw | ConvertFrom-Json
function Sha($p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash }
if ((Get-Process -Name $Proc -ErrorAction SilentlyContinue) -and -not $Force) { throw "Rally.exe is running - close the game first (or -Force)" }
if (-not (Test-Path -LiteralPath (Join-Path $Game "Rally.exe"))) { throw "no Rally.exe in $Game" }
$car = if ($m.car) { $m.car } else { $m.new }
$rep = @()
if ($m.replace) { $rep = @($m.replace) }
elseif ($m.db) { $rep = @([pscustomobject]@{ path = $m.db.path; source_sha256 = $m.db.source_sha256; sha256 = $m.db.sha256; backup = "arcadedatabase_xdata.before_" + $car.ToLower() + ".sbf" }) }
$bakDir = Join-Path $Game "Main_release\tracks\_SR3Extras\original"

# 1. every replaced SEGA file must be the expected one (or already ours) before anything is copied
$todo = @()
foreach ($r in $rep) {
    $dst = Join-Path $Game $r.path; $cur = Sha $dst
    if ($cur -eq $r.sha256) { Write-Host "already installed: $($r.path)" }
    elseif ($cur -ne $r.source_sha256) { throw "$($r.path) ($cur) is not the file this staging was built from ($($r.source_sha256)): uninstall the earlier car build first, or rebuild the staging" }
    else { $todo += $r }
}
# car files of another build (an earlier staging of the same car): uninstall that build first (-Force overwrites them,
# keeping each as <file>.before_install)
foreach ($f in $m.files) {
    $dst = Join-Path $Game $f.path
    if ((Test-Path -LiteralPath $dst) -and ((Sha $dst) -ne $f.sha256) -and -not $Force) { throw "$($f.path) is from another build: uninstall that build first (or -Force)" }
}

# 2. car files
foreach ($f in $m.files) {
    $src = Join-Path $here $f.path; $dst = Join-Path $Game $f.path
    if ((Sha $src) -ne $f.sha256) { throw "staged file changed since it was built: $src" }
    if (Test-Path -LiteralPath $dst) {
        if ((Sha $dst) -eq $f.sha256) { Write-Host "already installed: $($f.path)"; continue }
        $keep = "$dst.before_install"
        if (-not (Test-Path -LiteralPath $keep)) { Copy-Item -LiteralPath $dst -Destination $keep; Write-Host "kept $keep" }
    }
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
    Copy-Item -LiteralPath $src -Destination $dst -Force
    if ((Sha $dst) -ne $f.sha256) { throw "copy check failed: $dst" }
    Write-Host "installed $($f.path)"
}

# 3. replaced SEGA files, each kept first
New-Item -ItemType Directory -Force -Path $bakDir | Out-Null
foreach ($r in $todo) {
    $dst = Join-Path $Game $r.path; $bak = Join-Path $bakDir $r.backup
    if (-not (Test-Path -LiteralPath $bak)) { Copy-Item -LiteralPath $dst -Destination $bak; Write-Host "kept $bak" }
    elseif ((Sha $bak) -ne $r.source_sha256) { throw "$bak exists and is not the original of $($r.path); look at it before installing" }
    Copy-Item -LiteralPath (Join-Path $here $r.path) -Destination $dst -Force
    if ((Sha $dst) -ne $r.sha256) { throw "copy check failed: $dst" }
    Write-Host "installed $($r.path)"
}
Write-Host "done: '$car' installed"

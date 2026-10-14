# Installs a car staging folder made by car_clone.py into the game (copied into the staging folder as install.ps1).
#   powershell -ExecutionPolicy Bypass -File "<staging>\install.ps1" [-Game "<...\Rally>"] [-Force]
# - refuses while Rally.exe runs (-Force overrides);
# - car files: copied in; a file already there with other content is first kept as <file>.before_install;
# - ArcadeDatabase: only replaced when the game's file is exactly the one the staging was built from (SHA-256 in
#   manifest.json); the game's file is kept first as Main_release\tracks\_SR3Extras\original\arcadedatabase_xdata.before_<car>.sbf
#   (never over an existing backup, and never over _SR3Extras\original\arcadedatabase_xdata.sbf).
param([string]$Game = "F:\Jogos\SEGA Rally 3\GAME\Sega Rally 3\Rally", [switch]$Force, [string]$Proc = "Rally")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$m = Get-Content -LiteralPath (Join-Path $here "manifest.json") -Raw | ConvertFrom-Json
function Sha($p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash }
if ((Get-Process -Name $Proc -ErrorAction SilentlyContinue) -and -not $Force) { throw "Rally.exe is running - close the game first (or -Force)" }
if (-not (Test-Path -LiteralPath (Join-Path $Game "Rally.exe"))) { throw "no Rally.exe in $Game" }

# 1. ArcadeDatabase check before anything is copied
$db = Join-Path $Game $m.db.path
$cur = Sha $db
$dbDone = $false
if ($cur -eq $m.db.sha256) { Write-Host "ArcadeDatabase already lists the car"; $dbDone = $true }
elseif ($cur -ne $m.db.source_sha256) { throw "ArcadeDatabase ($cur) is not the file this staging was built from ($($m.db.source_sha256)); rebuild the staging with car_clone.py" }

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

# 3. ArcadeDatabase
if (-not $dbDone) {
    $bakDir = Join-Path $Game "Main_release\tracks\_SR3Extras\original"
    New-Item -ItemType Directory -Force -Path $bakDir | Out-Null
    $bak = Join-Path $bakDir ("arcadedatabase_xdata.before_" + $m.new.ToLower() + ".sbf")
    if (-not (Test-Path -LiteralPath $bak)) { Copy-Item -LiteralPath $db -Destination $bak; Write-Host "kept $bak" }
    elseif ((Sha $bak) -ne $m.db.source_sha256) { throw "$bak exists and is not the original ArcadeDatabase; look at it before installing" }
    Copy-Item -LiteralPath (Join-Path $here $m.db.path) -Destination $db -Force
    if ((Sha $db) -ne $m.db.sha256) { throw "copy check failed: $db" }
    Write-Host "installed $($m.db.path): car $($m.db.record.id) '$($m.db.record.folder)'"
}
Write-Host "done: '$($m.new)' (clone of $($m.donor)) installed"

# Removes a car installed by install.ps1 (copied into the staging folder as uninstall.ps1).
#   powershell -ExecutionPolicy Bypass -File "<staging>\uninstall.ps1" [-Game "<...\Rally>"] [-Force]
# - refuses while Rally.exe runs (-Force overrides);
# - car files: removed only when they are still the staged ones (-Force removes them anyway); a <file>.before_install
#   kept by the install is put back;
# - ArcadeDatabase: put back from Main_release\tracks\_SR3Extras\original\arcadedatabase_xdata.before_<car>.sbf (or, when
#   that is missing, read from _SR3Extras\original\arcadedatabase_xdata.sbf) - only when the game's file is still the
#   installed one and the backup is the file the staging was built from.
param([string]$Game = "F:\Jogos\SEGA Rally 3\GAME\Sega Rally 3\Rally", [switch]$Force, [string]$Proc = "Rally")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$m = Get-Content -LiteralPath (Join-Path $here "manifest.json") -Raw | ConvertFrom-Json
function Sha($p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash }
if ((Get-Process -Name $Proc -ErrorAction SilentlyContinue) -and -not $Force) { throw "Rally.exe is running - close the game first (or -Force)" }

# 1. ArcadeDatabase first: the game then no longer lists the car
$db = Join-Path $Game $m.db.path
$cur = Sha $db
$bakDir = Join-Path $Game "Main_release\tracks\_SR3Extras\original"
$bak = Join-Path $bakDir ("arcadedatabase_xdata.before_" + $m.new.ToLower() + ".sbf")
$orig = Join-Path $bakDir "arcadedatabase_xdata.sbf"
if ($cur -eq $m.db.source_sha256) { Write-Host "ArcadeDatabase is already the one without the car" }
elseif ($cur -ne $m.db.sha256) { Write-Warning "ArcadeDatabase changed since the install ($cur) - not touched" }
else {
    if ((Test-Path -LiteralPath $bak) -and ((Sha $bak) -eq $m.db.source_sha256)) { $from = $bak }
    elseif ((Test-Path -LiteralPath $orig) -and ((Sha $orig) -eq $m.db.source_sha256)) { $from = $orig }
    else { throw "no backup of the ArcadeDatabase with hash $($m.db.source_sha256) found" }
    Copy-Item -LiteralPath $from -Destination $db -Force
    if ((Sha $db) -ne $m.db.source_sha256) { throw "restore check failed: $db" }
    Write-Host "ArcadeDatabase restored from $from"
    if ($from -eq $bak) { Remove-Item -LiteralPath $bak; Write-Host "removed $bak" }
}

# 2. car files
foreach ($f in $m.files) {
    $dst = Join-Path $Game $f.path; $keep = "$dst.before_install"
    if (Test-Path -LiteralPath $dst) {
        if (((Sha $dst) -eq $f.sha256) -or $Force) { Remove-Item -LiteralPath $dst; Write-Host "removed $($f.path)" }
        else { Write-Warning "$($f.path) is not the installed file - left in place (-Force removes it)"; continue }
    }
    if (Test-Path -LiteralPath $keep) { Move-Item -LiteralPath $keep -Destination $dst; Write-Host "put back $dst" }
}
Write-Host "done: '$($m.new)' removed"

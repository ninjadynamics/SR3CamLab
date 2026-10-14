# Removes a car installed by install.ps1 (copied into the staging folder as uninstall.ps1).
#   powershell -ExecutionPolicy Bypass -File "<staging>\uninstall.ps1" [-Game "<...\Rally>"] [-Force]
# - refuses while Rally.exe runs (-Force overrides; -Proc names another process, for tests);
# - replaced SEGA files first (the game then no longer lists the car): put back from
#   Main_release\tracks\_SR3Extras\original\<backup> (or read from <fallback> there) - only when the game's file is still
#   the installed one and the backup is the file the staging was built from; the backup is removed after;
# - car files: removed only when they are still the staged ones (-Force removes them anyway); a <file>.before_install
#   kept by the install is put back.
param([string]$Game = "F:\Jogos\SEGA Rally 3\GAME\Sega Rally 3\Rally", [switch]$Force, [string]$Proc = "Rally")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$m = Get-Content -LiteralPath (Join-Path $here "manifest.json") -Raw | ConvertFrom-Json
function Sha($p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash }
if ((Get-Process -Name $Proc -ErrorAction SilentlyContinue) -and -not $Force) { throw "Rally.exe is running - close the game first (or -Force)" }
$car = if ($m.car) { $m.car } else { $m.new }
$rep = @()
if ($m.replace) { $rep = @($m.replace) }
elseif ($m.db) { $rep = @([pscustomobject]@{ path = $m.db.path; source_sha256 = $m.db.source_sha256; sha256 = $m.db.sha256; backup = "arcadedatabase_xdata.before_" + $car.ToLower() + ".sbf"; fallback = "arcadedatabase_xdata.sbf" }) }
$bakDir = Join-Path $Game "Main_release\tracks\_SR3Extras\original"

foreach ($r in $rep) {
    $dst = Join-Path $Game $r.path; $cur = Sha $dst
    $bak = Join-Path $bakDir $r.backup
    if ($cur -eq $r.source_sha256) { Write-Host "$($r.path) is already the original"; continue }
    if ($cur -ne $r.sha256) { Write-Warning "$($r.path) changed since the install ($cur) - not touched"; continue }
    $from = $null
    if ((Test-Path -LiteralPath $bak) -and ((Sha $bak) -eq $r.source_sha256)) { $from = $bak }
    elseif ($r.fallback) {
        $fb = Join-Path $bakDir $r.fallback
        if ((Test-Path -LiteralPath $fb) -and ((Sha $fb) -eq $r.source_sha256)) { $from = $fb }
    }
    if (-not $from) { throw "no copy of the original $($r.path) (hash $($r.source_sha256)) found" }
    Copy-Item -LiteralPath $from -Destination $dst -Force
    if ((Sha $dst) -ne $r.source_sha256) { throw "restore check failed: $dst" }
    Write-Host "$($r.path) restored from $from"
    if ($from -eq $bak) { Remove-Item -LiteralPath $bak; Write-Host "removed $bak" }
}
foreach ($f in $m.files) {
    $dst = Join-Path $Game $f.path; $keep = "$dst.before_install"
    if (Test-Path -LiteralPath $dst) {
        if (((Sha $dst) -eq $f.sha256) -or $Force) { Remove-Item -LiteralPath $dst; Write-Host "removed $($f.path)" }
        else { Write-Warning "$($f.path) is not the installed file - left in place (-Force removes it)"; continue }
    }
    if (Test-Path -LiteralPath $keep) { Move-Item -LiteralPath $keep -Destination $dst; Write-Host "put back $dst" }
}
Write-Host "done: '$car' removed"

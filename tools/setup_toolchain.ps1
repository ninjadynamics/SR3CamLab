# Python and the C compilers for SR3Lab's tools (gcc for the import stack's helpers, clang for 32-bit code), one of two ways:
#   (default)  from SR3Lab-<date>-toolchain.zip, which comes with SR3Lab: unpacked into tools\python and tools\mingw. Nothing is
#              downloaded, no internet needed, nothing is installed in Windows.
#   -Online    every part fetched from its own publisher: winget first, curl (built into Windows 10 and later) when winget is
#              missing or fails. Pinned versions, checked against their SHA-256:
#                Python 3.11.3       winget Python.Python.3.11 --version 3.11.3        | curl python.org's embeddable zip
#                numpy 1.24.3,       pip from that Python                              | curl the wheels from PyPI (their SHA-256
#                Pillow 10.0.1                                                         |   from PyPI's own metadata)
#                gcc + clang / lld   winget BrechtSanders.WinLibs.POSIX.UCRT.LLVM      | curl WinLibs' gcc 13.2.0 + LLVM 17.0.6 r5
#                                                                                      |   (the build SR3Lab is checked with)
#              The folders go into tools\import\settings.json ("python", "gcc"); the toolchain zip is not needed then.
#   powershell -ExecutionPolicy Bypass -File setup_toolchain.ps1 [-Online] [-NoWinget] [-Zip <toolchain zip>]
param([switch]$Online, [switch]$Winget, [switch]$NoWinget, [string]$Zip = '')
$ErrorActionPreference = 'Stop'; if ($Winget) { $Online = $true }      # (-Winget: the earlier name of -Online)
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path; $Settings = Join-Path $Repo 'tools\import\settings.json'
$Dl = Join-Path $Repo 'dist\downloads'
$PyVer = '3.11.3'; $Wheels = @(@('numpy', '1.24.3'), @('Pillow', '10.0.1'))
$PyZip = @{ url = "https://www.python.org/ftp/python/$PyVer/python-$PyVer-embed-amd64.zip"; sha256 = '' }
$GccZip = @{ url = 'https://github.com/brechtsanders/winlibs_mingw/releases/download/13.2.0posix-17.0.6-11.0.1-ucrt-r5/winlibs-x86_64-posix-seh-gcc-13.2.0-llvm-17.0.6-mingw-w64ucrt-11.0.1-r5.zip'; sha256 = '' }
$PathsPy = @'
"""SR3Lab's Python (tools\python, python311._pth): at start-up, after site, the running script's own folder goes first on
sys.path (the current folder for -c / -m), as a normal Python has it, and the user's own site-packages comes off it, so that
nothing installed elsewhere on the PC is imported instead of this Python's own numpy and Pillow."""
import os, sys, site
_user = os.path.normcase(os.path.abspath(site.getusersitepackages()))
for _p in list(sys.path):
    if os.path.normcase(os.path.abspath(_p)) == _user: sys.path.remove(_p)
_a = sys.argv[0] if sys.argv else ''
sys.path.insert(0, os.path.dirname(os.path.abspath(_a)) if _a and _a not in ('-c', '-m') else os.getcwd())
'@

function Set-Setting([string]$k, [string]$v) {
    $s = [ordered]@{}
    if (Test-Path -LiteralPath $Settings) { $j = [IO.File]::ReadAllText($Settings) | ConvertFrom-Json; foreach ($p in $j.PSObject.Properties) { $s[$p.Name] = $p.Value } }
    $s[$k] = $v; $t = (ConvertTo-Json $s) -replace "`r`n", "`n"
    [IO.File]::WriteAllText($Settings, $t + "`n", (New-Object Text.UTF8Encoding($false)))
}
function Write-Lf([string]$path, [string]$text) { [IO.File]::WriteAllText($path, ($text -replace "`r`n", "`n"), (New-Object Text.UTF8Encoding($false))) }
function Have-Winget { return (-not $NoWinget) -and [bool](Get-Command winget -ErrorAction SilentlyContinue) }
function Get-File([string]$url, [string]$sha256, [string]$name = '') {
    # curl.exe (Windows' own) into dist\downloads, kept for the next time; a pinned SHA-256 must match
    [void][IO.Directory]::CreateDirectory($Dl); if (-not $name) { $name = $url.Split('/')[-1] }; $p = Join-Path $Dl $name
    if (-not (Test-Path -LiteralPath $p)) {
        "curl: $url"
        & curl.exe -L --fail --retry 3 --silent --show-error -o "$p.part" $url
        if ($LASTEXITCODE) { throw "curl could not fetch $url" }
        Move-Item -LiteralPath "$p.part" -Destination $p -Force
    }
    $h = (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLower()
    if ($sha256 -and $h -ne $sha256.ToLower()) { Remove-Item -LiteralPath $p; throw "$name is not the file SR3Lab expects (SHA-256 $h)" }
    return $p
}
function Expand-Some([string]$zip, [string]$dst, [scriptblock]$keep, [int]$strip = 0) {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $z = [IO.Compression.ZipFile]::OpenRead($zip); $n = 0
    try {
        foreach ($e in $z.Entries) {
            $rel = $e.FullName -replace '/', '\'; for ($k = 0; $k -lt $strip; $k++) { $rel = $rel -replace '^[^\\]*\\', '' }
            if (-not $rel -or $rel.EndsWith('\') -or -not (& $keep $rel)) { continue }
            $p = Join-Path $dst $rel; [void][IO.Directory]::CreateDirectory((Split-Path -Parent $p))
            [IO.Compression.ZipFileExtensions]::ExtractToFile($e, $p, $true); $n++
        }
    } finally { $z.Dispose() }
    return $n
}

if (-not $Online) {
    if (-not $Zip) {
        $c = @(Get-ChildItem -Path (Join-Path $Repo '*-toolchain.zip'), (Join-Path (Split-Path -Parent $Repo) '*-toolchain.zip') -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
        if (-not $c.Count) { throw "No SR3Lab toolchain zip found next to SR3Lab ($Repo) or in its parent folder: give its place with -Zip, or use -Online." }
        $Zip = $c[0].FullName
    }
    $n = Expand-Some $Zip $Repo { param($r) $r -match '^tools\\(python|mingw)\\' -or $r -eq 'TOOLCHAIN-README.txt' } 1
    $py = Join-Path $Repo 'tools\python\python.exe'
    $v = & $py -c "import sys, numpy, PIL; print(sys.version.split()[0], numpy.__version__, PIL.__version__)"
    "Unpacked $n files from $(Split-Path -Leaf $Zip): Python, numpy, Pillow = $v; gcc and clang in tools\mingw."
    return
}

# ---- Python, numpy, Pillow ----
$py = $null
if (Have-Winget) {
    "winget: Python $PyVer (python.org) ..."
    & winget install --id Python.Python.3.11 --version $PyVer -e --scope user --silent --accept-package-agreements --accept-source-agreements
    $w = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'
    if (Test-Path -LiteralPath $w) {
        & $w -m pip install --disable-pip-version-check ($Wheels | ForEach-Object { "$($_[0])==$($_[1])" })
        if ($LASTEXITCODE -eq 0) { $py = $w } else { 'pip did not install numpy / Pillow: the embeddable Python and the wheels come by curl instead.' }
    } else { 'winget left no Python where expected: curl instead.' }
}
if (-not $py) {
    $t = Join-Path $Repo 'tools\python'; [void][IO.Directory]::CreateDirectory($t)
    $z = Get-File $PyZip.url $PyZip.sha256; [void](Expand-Some $z $t { param($r) $true })
    Write-Lf (Join-Path $t 'python311._pth') "python311.zip`n.`nLib\site-packages`nimport site`n"
    $sp = Join-Path $t 'Lib\site-packages'; [void][IO.Directory]::CreateDirectory($sp)
    Write-Lf (Join-Path $sp 'sr3lab_paths.py') $PathsPy; Write-Lf (Join-Path $sp 'sr3lab_paths.pth') "import sr3lab_paths`n"
    foreach ($w in $Wheels) {                                          # the wheel's address and SHA-256 from PyPI's own metadata
        $j = (& curl.exe -L --fail --silent "https://pypi.org/pypi/$($w[0])/$($w[1])/json") | ConvertFrom-Json
        $f = @($j.urls | Where-Object { $_.filename -like '*-cp311-cp311-win_amd64.whl' })[0]
        if (-not $f) { throw "PyPI has no Windows wheel of $($w[0]) $($w[1]) for Python 3.11" }
        $p = Get-File $f.url $f.digests.sha256 $f.filename; [void](Expand-Some $p $sp { param($r) $true })
    }
    $py = Join-Path $t 'python.exe'
}
Set-Setting 'python' $py
"Python: $py ($(& $py -c "import sys, numpy, PIL; print(sys.version.split()[0], numpy.__version__, PIL.__version__)"))"

# ---- gcc and clang (WinLibs) ----
$gcc = $null
if (Have-Winget) {
    "winget: gcc and clang (WinLibs, MinGW-w64 UCRT, LLVM) ..."
    & winget install --id BrechtSanders.WinLibs.POSIX.UCRT.LLVM -e --silent --accept-package-agreements --accept-source-agreements
    $g = @(Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT.LLVM*\mingw64\bin\gcc.exe') -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($g.Count) { $gcc = $g[0].FullName; 'Note: winget''s WinLibs is a newer gcc than the 13.2 SR3Lab''s builds are checked with.' } else { 'winget left no gcc where expected: curl instead.' }
}
if (-not $gcc) {
    $z = Get-File $GccZip.url $GccZip.sha256
    $n = Expand-Some $z (Join-Path $Repo 'tools') { param($r) $r -like 'mingw64\*' }        # -> tools\mingw64 (gcc, clang, lld, headers, libraries)
    $gcc = Join-Path $Repo 'tools\mingw64\bin\gcc.exe'; "WinLibs gcc 13.2.0 + LLVM 17.0.6 r5: $n files in tools\mingw64"
}
Set-Setting 'gcc' $gcc
"gcc: $gcc ; clang: $(Join-Path (Split-Path -Parent $gcc) 'clang.exe')"
"Done. tools\import\settings.json names them; the toolchain zip, tools\python and tools\mingw are not needed now."

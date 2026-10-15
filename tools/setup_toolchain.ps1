# Python and a C compiler for SR3Lab's tools, one of two ways:
#   (default)  from SR3Lab-<date>-toolchain.zip, which comes with SR3Lab: unpacked into tools\python and tools\mingw. Nothing is
#              downloaded, no internet needed, nothing is installed in Windows.
#   -Winget    winget fetches Python 3.11.3 (python.org's build) and WinLibs' gcc, then pip fetches numpy 1.24.3 and Pillow 10.0.1
#              (the versions SR3Lab's builds are checked with). Their folders go into tools\import\settings.json; the toolchain
#              zip is not needed then and can be deleted (and tools\python, tools\mingw with it).
#   powershell -ExecutionPolicy Bypass -File setup_toolchain.ps1 [-Winget] [-Zip <toolchain zip>]
param([switch]$Winget, [string]$Zip = '')
$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path; $Settings = Join-Path $Repo 'tools\import\settings.json'
function Set-Setting([string]$k, [string]$v) {
    $s = [ordered]@{}
    if (Test-Path -LiteralPath $Settings) { $j = [IO.File]::ReadAllText($Settings) | ConvertFrom-Json; foreach ($p in $j.PSObject.Properties) { $s[$p.Name] = $p.Value } }
    $s[$k] = $v; $t = (ConvertTo-Json $s) -replace "`r`n", "`n"
    [IO.File]::WriteAllText($Settings, $t + "`n", (New-Object Text.UTF8Encoding($false)))
}

if (-not $Winget) {
    if (-not $Zip) {
        $c = @(Get-ChildItem -Path (Join-Path $Repo '*-toolchain.zip'), (Join-Path (Split-Path -Parent $Repo) '*-toolchain.zip') -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending)
        if (-not $c.Count) { throw "No SR3Lab toolchain zip found next to SR3Lab ($Repo) or in its parent folder: give its place with -Zip, or use -Winget." }
        $Zip = $c[0].FullName
    }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $z = [IO.Compression.ZipFile]::OpenRead($Zip); $n = 0
    try {
        foreach ($e in $z.Entries) {
            $rel = ($e.FullName -replace '/', '\') -replace '^[^\\]+\\', ''          # the zip's first folder is the release's name
            if (-not $rel -or $rel.EndsWith('\')) { continue }
            if ($rel -notmatch '^tools\\(python|mingw)\\' -and $rel -ne 'TOOLCHAIN-README.txt') { continue }
            $dst = Join-Path $Repo $rel; [void][IO.Directory]::CreateDirectory((Split-Path -Parent $dst))
            [IO.Compression.ZipFileExtensions]::ExtractToFile($e, $dst, $true); $n++
        }
    } finally { $z.Dispose() }
    $py = Join-Path $Repo 'tools\python\python.exe'
    $v = & $py -c "import sys, numpy, PIL; print(sys.version.split()[0], numpy.__version__, PIL.__version__)"
    "Unpacked $n files from $(Split-Path -Leaf $Zip): Python, numpy, Pillow = $v; gcc in tools\mingw."
    return
}

# ---- winget ----
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'winget is not on this PC (Windows 10 1809+ / the App Installer from the Microsoft Store). Use the toolchain zip instead.' }
"winget: Python 3.11.3 (python.org) ..."
& winget install --id Python.Python.3.11 --version 3.11.3 -e --scope user --silent --accept-package-agreements --accept-source-agreements
$py = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'
if (-not (Test-Path -LiteralPath $py)) { throw "winget did not leave Python where it should be ($py)." }
"pip: numpy 1.24.3 and Pillow 10.0.1 ..."
& $py -m pip install --disable-pip-version-check numpy==1.24.3 pillow==10.0.1
if ($LASTEXITCODE) { throw 'pip did not install numpy / Pillow.' }
"winget: gcc (WinLibs, MinGW-w64, UCRT) ..."
& winget install --id BrechtSanders.WinLibs.POSIX.UCRT --version 14.2.0-12.0.0-r2 -e --silent --accept-package-agreements --accept-source-agreements
$gcc = @(Get-ChildItem -Path (Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT*\mingw64\bin\gcc.exe') -ErrorAction SilentlyContinue | Select-Object -First 1)
if (-not $gcc.Count) { throw 'winget did not leave gcc where it should be (WinGet\Packages\BrechtSanders.WinLibs.POSIX.UCRT*).' }
Set-Setting 'python' $py; Set-Setting 'gcc' $gcc[0].FullName
"Done: python = $py, gcc = $($gcc[0].FullName) (in tools\import\settings.json). The toolchain zip, tools\python and tools\mingw are not needed now."
"Note: the zip's gcc is 13.2 and the oldest winget has is 14.2; SR3Lab's checks so far were made with 13.2."

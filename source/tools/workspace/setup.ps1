param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Options)
$ErrorActionPreference='Stop'
$root=Split-Path (Split-Path (Split-Path $PSScriptRoot))
$python=Join-Path $root 'toolchain\python\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
 $cfg=Join-Path $root 'config\workspace.json'
 if (Test-Path -LiteralPath $cfg) { $python=(Get-Content -LiteralPath $cfg -Raw | ConvertFrom-Json).python }
}
if (-not $python -or -not (Test-Path -LiteralPath $python)) {
 $found=Get-Command python.exe -ErrorAction SilentlyContinue
 if ($found) { $python=$found.Source }
}
if (-not $python -or -not (Test-Path -LiteralPath $python)) { throw 'Python missing. Extract the bundled toolchain into toolchain\python, then rerun SETUP.bat.' }
if (-not $Options) {
 if (-not (Test-Path -LiteralPath (Join-Path $root 'game\Rally\Rally.exe'))) {
  $game=Read-Host 'Path to your unmodified SR3 Rally folder (containing Rally.exe)'
  $Options=@('--game-source',$game.Trim('"'))
 }
}
& $python (Join-Path $PSScriptRoot 'setup.py') @Options
exit $LASTEXITCODE

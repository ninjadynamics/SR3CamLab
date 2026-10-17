param([string]$Workspace='', [switch]$Check)
$ErrorActionPreference='Stop'
if (-not $Workspace) { $Workspace=Split-Path (Split-Path (Split-Path $PSScriptRoot)) }
$cfg=Get-Content -LiteralPath (Join-Path $Workspace 'config/workspace.json') -Raw | ConvertFrom-Json
$arguments=@((Join-Path $PSScriptRoot 'update_textures.py'),'--workspace',$Workspace)
if ($Check) { $arguments+='--check' }
& $cfg.python @arguments
if ($LASTEXITCODE -ne 0) { throw "Texture update failed ($LASTEXITCODE)." }

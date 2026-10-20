$ErrorActionPreference='Stop'
$workspace=Split-Path (Split-Path (Split-Path $PSScriptRoot))
$config=Get-Content -LiteralPath (Join-Path $workspace 'config/workspace.json') -Raw | ConvertFrom-Json
$script=Join-Path $workspace 'source/standalone/relief_page_server.py'
$launchArgs=@(('"'+$script+'"'),'--open')
Start-Process -FilePath $config.python -ArgumentList $launchArgs -WorkingDirectory $workspace -WindowStyle Hidden

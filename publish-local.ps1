param([ValidateRange(1,65535)][int]$Port = 8765)
$ErrorActionPreference = 'Stop'
$syncArgs = @((Join-Path $PSScriptRoot 'deploy/local_sync.py'), 'publish', '--root', $PSScriptRoot, '--port', "$Port")
$localPython = Join-Path $PSScriptRoot '.wxq-runtime/Scripts/python.exe'
if (Test-Path -LiteralPath $localPython) {
    & $localPython @syncArgs
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3.12 @syncArgs
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python @syncArgs
} else {
    throw 'Install Python 3.12 first.'
}
exit $LASTEXITCODE
